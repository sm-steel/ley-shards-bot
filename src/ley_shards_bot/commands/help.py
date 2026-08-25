"""/help — lists available commands with a one-line description each.
Admin-only commands only appear for admins. See issue #16.

Descriptions come from commands/helpers/menu.py, the same list used to register
Telegram's / autocomplete (issue #15) — one source of truth, not two
copies that can drift apart.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import ContextTypes

from ley_shards_bot.commands.helpers.menu import ADMIN_COMMANDS, PLAYER_COMMANDS
from ley_shards_bot.commands.helpers.scoping import is_admin

if TYPE_CHECKING:
    from telegram import BotCommand


def _format_commands(commands: list[BotCommand]) -> str:
    return "\n".join(f"/{c.command} — {c.description}" for c in commands)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return

    sections = [_format_commands(PLAYER_COMMANDS)]
    if is_admin(update, context):
        sections.append(_format_commands(ADMIN_COMMANDS))
    await message.reply_text("\n\n".join(sections))
