"""Telegram-facing handlers for the economy: /daily, /award_guess, /grant,
and the first-message-of-day trickle.

Thin by design (see CLAUDE.md): parse the Update, call services/economy.py,
format the reply. No game rules live here.

Handlers expect `context.bot_data["config"]` to hold the running Config
(for admin_user_ids) — set once at Application startup.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from ley_shards_bot.db import session_scope
from ley_shards_bot.services import economy
from ley_shards_bot.time_utils import utc_now


def _is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    config = context.bot_data["config"]
    user = update.effective_user
    return user is not None and user.id in config.admin_user_ids


def _replied_to_user_id(update: Update) -> int | None:
    """The user a reply-based admin command targets — whoever sent the
    message being replied to. None if this command wasn't used as a
    reply."""
    message = update.effective_message
    if message is None or message.reply_to_message is None:
        return None
    replied_user = message.reply_to_message.from_user
    return replied_user.id if replied_user is not None else None


async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG001
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return

    with session_scope() as session:
        result = economy.claim_daily(session, user.id, now=utc_now())

    if result.granted:
        text = f"+{result.amount} Ley Shards \U0001f48e (balance: {result.new_balance})"
    else:
        text = (
            "Already claimed today — next claim available "
            f"{result.next_claim_at:%Y-%m-%d %H:%M} UTC."
        )
    await message.reply_text(text)


async def trickle_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG001
    """Registered on every non-command group message. Grants the small
    once-per-day activity bonus; silent (no reply) so it doesn't add noise
    to normal chat."""
    user = update.effective_user
    if user is None:
        return

    with session_scope() as session:
        economy.apply_trickle(session, user.id, today=utc_now().date())


async def award_guess_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    if not _is_admin(update, context):
        await message.reply_text("Admins only.")
        return

    target_id = _replied_to_user_id(update)
    if target_id is None:
        await message.reply_text("Reply to the correct guess with /award_guess.")
        return

    with session_scope() as session:
        result = economy.award_guess(session, target_id, today=utc_now().date())

    if result.granted:
        text = f"+{result.amount} Ley Shards awarded ({result.awards_remaining_today} more today)."
    else:
        text = "This player already hit today's award limit."
    await message.reply_text(text)


async def grant_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    if not _is_admin(update, context):
        await message.reply_text("Admins only.")
        return

    target_id = _replied_to_user_id(update)
    if target_id is None:
        await message.reply_text("Reply to the target player's message with /grant <amount>.")
        return

    args = context.args or []
    if not args or not args[0].lstrip("-").isdigit():
        await message.reply_text("Usage: reply to the player with /grant <amount>")
        return

    amount = int(args[0])
    with session_scope() as session:
        try:
            new_balance = economy.grant(session, target_id, amount)
        except ValueError as exc:
            await message.reply_text(str(exc))
            return

    await message.reply_text(f"Granted {amount} Ley Shards (new balance: {new_balance}).")
