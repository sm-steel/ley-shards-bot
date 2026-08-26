"""Telegram-facing handlers for the economy: /daily, /award_guess, /grant,
/revoke, and the first-message-of-day trickle.

Thin by design (see CLAUDE.md): parse the Update, call services/economy.py,
format the reply. No game rules live here.

Handlers expect `context.bot_data["config"]` to hold the running Config
(for admin_user_ids) — set once at Application startup.

`/daily` is DM-scoped (see `commands/helpers/scoping.py` and issue #17); the
admin commands and trickle are not — see ARCHITECTURE.md's "Commands &
topics" section for why.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from ley_shards_bot.commands.helpers.scoping import NOT_IN_DM_MESSAGE, in_private_chat, is_admin
from ley_shards_bot.commands.helpers.targeting import resolve_target
from ley_shards_bot.db import session_scope
from ley_shards_bot.services import economy
from ley_shards_bot.services.players import PlayerRef
from ley_shards_bot.time_utils import game_day, utc_now

if TYPE_CHECKING:
    from collections.abc import Callable


async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG001
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    logger.debug("/daily from {}", user.id)
    if not in_private_chat(update):
        logger.debug("/daily from {} rejected: not a DM", user.id)
        await message.reply_text(NOT_IN_DM_MESSAGE)
        return

    with session_scope() as session:
        result = economy.claim_daily(
            session, PlayerRef(user.id, username=user.username), now=utc_now()
        )

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
    logger.trace("Trickle check for {}", user.id)

    with session_scope() as session:
        economy.apply_trickle(
            session, PlayerRef(user.id, username=user.username), today=game_day(utc_now())
        )


async def award_guess_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    logger.debug(
        "/award_guess from {}", update.effective_user.id if update.effective_user else None
    )
    if not is_admin(update, context):
        if update.effective_user is not None:
            logger.warning("Non-admin {} attempted an admin-only command", update.effective_user.id)
        await message.reply_text("Admins only.")
        return

    with session_scope() as session:
        resolved = await resolve_target(
            update,
            session,
            context.args or [],
            reply_hint=(
                "Reply to the correct guess with /award_guess, or use /award_guess @username."
            ),
        )
        if resolved is None:
            return
        target_id, capture_username, _remaining_args = resolved

        result = economy.award_guess(
            session, PlayerRef(target_id, username=capture_username), today=game_day(utc_now())
        )

    if result.granted:
        text = f"+{result.amount} Ley Shards awarded ({result.awards_remaining_today} more today)."
    else:
        text = "This player already hit today's award limit."
    await message.reply_text(text)


@dataclass(frozen=True)
class _AmountCommandSpec:
    """The three things that differ between `/grant` and `/revoke` —
    bundled into one value (rather than three separate parameters) since
    they're one cohesive concept: how this particular command variant
    behaves. See issue #47."""

    command: str  # "/grant" or "/revoke"
    apply: Callable[..., int]  # economy.grant or economy.revoke
    verb: str  # "Granted" or "Revoked", for the success reply


async def _execute_amount_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE, spec: _AmountCommandSpec
) -> None:
    """Shared implementation behind `/grant` and `/revoke` — an admin
    command that resolves a target (#13), parses a Ley Shards amount, and
    applies it via `spec.apply`."""
    message = update.effective_message
    if message is None:
        return
    logger.debug(
        "{} from {}", spec.command, update.effective_user.id if update.effective_user else None
    )
    if not is_admin(update, context):
        if update.effective_user is not None:
            logger.warning("Non-admin {} attempted an admin-only command", update.effective_user.id)
        await message.reply_text("Admins only.")
        return

    with session_scope() as session:
        resolved = await resolve_target(
            update,
            session,
            context.args or [],
            reply_hint=(
                f"Reply to the target player's message with {spec.command} <amount>, "
                f"or use {spec.command} @username <amount>."
            ),
        )
        if resolved is None:
            return
        target_id, capture_username, amount_args = resolved

        if not amount_args or not amount_args[0].lstrip("-").isdigit():
            await message.reply_text(
                f"Usage: reply to the player with {spec.command} <amount>, "
                f"or {spec.command} @username <amount>"
            )
            return
        amount = int(amount_args[0])

        try:
            new_balance = spec.apply(
                session, PlayerRef(target_id, username=capture_username), amount
            )
        except ValueError as exc:
            logger.debug("{} rejected: {}", spec.command, exc)
            await message.reply_text(str(exc))
            return

    await message.reply_text(f"{spec.verb} {amount} Ley Shards (new balance: {new_balance}).")


_GRANT_SPEC = _AmountCommandSpec(command="/grant", apply=economy.grant, verb="Granted")
_REVOKE_SPEC = _AmountCommandSpec(command="/revoke", apply=economy.revoke, verb="Revoked")


async def grant_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _execute_amount_command(update, context, _GRANT_SPEC)


async def revoke_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _execute_amount_command(update, context, _REVOKE_SPEC)
