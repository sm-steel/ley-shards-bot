"""Application wiring: builds the python-telegram-bot Application and
registers every command handler. This is the one place that assembles the
pieces built in commands/ — see CLAUDE.md for the commands/services/models
boundary those follow.
"""

from __future__ import annotations

from loguru import logger
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
    trickle_message_handler,
)
from ley_shards_bot.commands.gacha import pull_command, pull_ten_command
from ley_shards_bot.config import Config
from ley_shards_bot.logging_config import setup_logging


def build_application(config: Config) -> Application:
    builder = ApplicationBuilder().token(config.bot_token)
    if config.telegram_proxy_url:
        builder = builder.proxy(config.telegram_proxy_url).get_updates_proxy(
            config.telegram_proxy_url
        )
    application = builder.build()
    application.bot_data["config"] = config

    application.add_handler(CommandHandler("daily", daily_command))
    application.add_handler(CommandHandler("award_guess", award_guess_command))
    application.add_handler(CommandHandler("grant", grant_command))
    application.add_handler(CommandHandler("pull", pull_command))
    application.add_handler(CommandHandler("pull10", pull_ten_command))
    application.add_handler(CommandHandler("collection", collection_command))
    application.add_handler(CallbackQueryHandler(collection_page_callback, pattern=r"^coll:"))

    # Own handler group (not the default group 0): PTB runs at most one
    # handler per group per update, so the trickle bonus needs its own
    # group to fire *alongside* whichever command handler also matches
    # (e.g. a player's first message of the day being /daily itself should
    # still grant both).
    application.add_handler(
        MessageHandler(filters.ChatType.GROUPS, trickle_message_handler), group=1
    )

    logger.info(
        "Registered {} command(s), 1 callback handler, 1 trickle handler",
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
