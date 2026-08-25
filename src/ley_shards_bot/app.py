"""Application wiring: builds the python-telegram-bot Application and
registers every command handler. This is the one place that assembles the
pieces built in commands/ — see CLAUDE.md for the commands/services/models
boundary those follow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger
from telegram import BotCommand, BotCommandScopeChat, BotCommandScopeDefault
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from ley_shards_bot.commands.collection import collection_command, collection_page_callback
from ley_shards_bot.commands.economy import (
    award_guess_command,
    daily_command,
    grant_command,
    revoke_command,
    trickle_message_handler,
)
from ley_shards_bot.commands.gacha import (
    pull_command,
    pull_confirmation_callback,
    pull_ten_command,
)
from ley_shards_bot.commands.help import help_command
from ley_shards_bot.commands.helpers.menu import ADMIN_COMMANDS, PLAYER_COMMANDS
from ley_shards_bot.commands.tickets import buy_ticket_command
from ley_shards_bot.config import Config
from ley_shards_bot.logging_config import setup_logging

if TYPE_CHECKING:
    from telegram import BotCommandScope


def _command_registrations(
    admin_user_ids: frozenset[int],
) -> list[tuple[BotCommandScope, list[BotCommand]]]:
    """The (scope, commands) pairs to hand to `Bot.set_my_commands`, one
    call per scope — see issue #15. Admins get PLAYER_COMMANDS too (they're
    players as well), scoped to their own chat with the bot rather than
    polluting the default menu everyone else sees."""
    registrations: list[tuple[BotCommandScope, list[BotCommand]]] = [
        (BotCommandScopeDefault(), PLAYER_COMMANDS)
    ]
    registrations.extend(
        (BotCommandScopeChat(chat_id=admin_id), [*PLAYER_COMMANDS, *ADMIN_COMMANDS])
        for admin_id in admin_user_ids
    )
    return registrations


async def register_commands(application: Application) -> None:
    """`post_init` hook: publishes the / autocomplete menu once at startup.
    Runs after `Application.initialize()`, before polling starts."""
    config: Config = application.bot_data["config"]
    for scope, commands in _command_registrations(config.admin_user_ids):
        await application.bot.set_my_commands(commands, scope=scope)
    logger.info("Registered / autocomplete commands ({} scope(s))", len(config.admin_user_ids) + 1)


def build_application(config: Config) -> Application:
    builder = ApplicationBuilder().token(config.bot_token).post_init(register_commands)
    if config.telegram_proxy_url:
        builder = builder.proxy(config.telegram_proxy_url).get_updates_proxy(
            config.telegram_proxy_url
        )
    application = builder.build()
    application.bot_data["config"] = config

    application.add_handler(CommandHandler("daily", daily_command))
    application.add_handler(CommandHandler("award_guess", award_guess_command))
    application.add_handler(CommandHandler("grant", grant_command))
    application.add_handler(CommandHandler("revoke", revoke_command))
    application.add_handler(CommandHandler("pull", pull_command))
    application.add_handler(CommandHandler("pull10", pull_ten_command))
    application.add_handler(CommandHandler("collection", collection_command))
    application.add_handler(CommandHandler("buy_ticket", buy_ticket_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(collection_page_callback, pattern=r"^coll:"))
    application.add_handler(CallbackQueryHandler(pull_confirmation_callback, pattern=r"^pull:"))

    # Own handler group (not the default group 0): PTB runs at most one
    # handler per group per update, so the trickle bonus needs its own
    # group to fire *alongside* whichever command handler also matches
    # (e.g. a player's first message of the day being /daily itself should
    # still grant both).
    application.add_handler(
        MessageHandler(filters.ChatType.GROUPS, trickle_message_handler), group=1
    )

    logger.info(
        "Registered {} command(s), 2 callback handlers, 1 trickle handler",
        len(application.handlers[0]) - 1,
    )
    return application


def main() -> None:
    config = Config.from_env()
    setup_logging(config.log_level)
    logger.info("Starting ley-shards-bot (log level={})", config.log_level)
    application = build_application(config)
    application.run_polling()
    logger.info("Bot stopped")


if __name__ == "__main__":
    main()
