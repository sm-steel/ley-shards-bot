"""Telegram-facing handler for /buy_ticket.

Thin by design (see CLAUDE.md): parse the Update, call
services/tickets.py, format the reply. No currency/economy rules live
here.
"""

from __future__ import annotations

from loguru import logger
from telegram import Message, Update
from telegram.ext import ContextTypes

from ley_shards_bot.commands.helpers.scoping import NOT_IN_DM_MESSAGE, in_private_chat
from ley_shards_bot.db import session_scope
from ley_shards_bot.models import BannerType
from ley_shards_bot.services import tickets
from ley_shards_bot.services.gacha import InsufficientLeyShardsError
from ley_shards_bot.services.players import PlayerRef

_USAGE = "Usage: /buy_ticket <standard|event> <count>"


async def _parse_ticket_request(message: Message, args: list[str]) -> tuple[BannerType, int] | None:
    """Validates `/buy_ticket`'s args, replying (and returning None) on the
    first problem found — mirrors `commands/helpers/targeting.resolve_target`'s
    reply-then-None-sentinel shape so the caller just checks for None."""
    if len(args) != 2 or not args[1].isdecimal():
        await message.reply_text(_USAGE)
        return None
    try:
        ticket_type = BannerType(args[0].lower())
    except ValueError:
        await message.reply_text("Ticket type must be 'standard' or 'event'.")
        return None
    return ticket_type, int(args[1])


async def buy_ticket_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    logger.debug("/buy_ticket from {}", user.id)
    if not in_private_chat(update):
        logger.debug("/buy_ticket from {} rejected: not a DM", user.id)
        await message.reply_text(NOT_IN_DM_MESSAGE)
        return

    parsed = await _parse_ticket_request(message, context.args or [])
    if parsed is None:
        return
    ticket_type, count = parsed

    with session_scope() as session:
        try:
            new_balance = tickets.buy_tickets(
                session, PlayerRef(user.id, username=user.username), ticket_type, count
            )
        except InsufficientLeyShardsError as exc:
            await message.reply_text(
                f"Not enough Ley Shards \U0001f48e — need {exc.required}, have {exc.available}."
            )
            return
        except ValueError as exc:
            await message.reply_text(str(exc))
            return

    reply = f"Bought {count} {ticket_type.value} ticket(s) (balance: {new_balance})."
    if ticket_type is BannerType.EVENT:
        reply += (
            " Heads up: event tickets can't be spent yet — banner selection for "
            "/pull is coming later."
        )
    await message.reply_text(reply)
