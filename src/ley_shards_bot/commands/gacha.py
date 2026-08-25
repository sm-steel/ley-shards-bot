"""Telegram-facing handlers for gacha pulls: /pull and /pull10.

Thin by design (see CLAUDE.md): parse the Update, call services/gacha.py,
format the reply. No pity/rarity/economy rules live here.

DM-scoped, not group-topic-scoped — see ARCHITECTURE.md's "Commands &
topics" section and issue #17. A 4★+ pull also gets a best-effort public
announcement in the group's 🎰 Gacha topic (issue #18) on top of the DM
result — see `_announce_rare_pull`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from ley_shards_bot.commands.scoping import NOT_IN_DM_MESSAGE, in_private_chat
from ley_shards_bot.db import session_scope
from ley_shards_bot.models import Rarity
from ley_shards_bot.services import gacha

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session
    from telegram import Message, User

_PullResultT = TypeVar("_PullResultT")

_RARITY_STARS = {
    Rarity.THREE_STAR: "★★★",
    Rarity.FOUR_STAR: "★★★★",
    Rarity.FIVE_STAR: "★★★★★",
}

# 10-pull sends a text summary of everything, plus a photo card for these
# rarities only — every character in a highlight-only feed would be spam.
_HIGHLIGHT_RARITIES = frozenset({Rarity.FOUR_STAR, Rarity.FIVE_STAR})


def _rate_up_note(outcome: gacha.PullOutcome) -> str:
    if outcome.is_rate_up is True:
        return " 🌟 rate-up!"
    if outcome.is_rate_up is False:
        return " (lost the 50/50)"
    return ""


def _format_outcome_line(outcome: gacha.PullOutcome) -> str:
    stars = _RARITY_STARS[outcome.rarity]
    status = "NEW" if outcome.is_new else f"dupe, +{outcome.echoes_gained} Echoes"
    return (
        f"{stars} {outcome.character.name} — {outcome.character.series} "
        f"[{status}]{_rate_up_note(outcome)}"
    )


def _format_single_caption(outcome: gacha.PullOutcome) -> str:
    lines = [
        f"{_RARITY_STARS[outcome.rarity]} {outcome.character.name}",
        outcome.character.series,
        "✨ NEW!" if outcome.is_new else f"Duplicate — +{outcome.echoes_gained} Echoes",
    ]
    note = _rate_up_note(outcome)
    if note:
        lines.append(note.strip())
    return "\n".join(lines)


async def _announce_rare_pull(
    context: ContextTypes.DEFAULT_TYPE, user: User, outcome: gacha.PullOutcome
) -> None:
    """Post a celebratory public message into the group's 🎰 Gacha topic
    for a 4★+ pull, on top of — not instead of — the private DM result.
    Best-effort: a failure here (bot not in the group, topic gone, ...)
    must never take down the DM reply that already succeeded."""
    if outcome.rarity not in _HIGHLIGHT_RARITIES:
        return
    try:
        config = context.bot_data["config"]
        text = (
            f"🎉 {user.first_name} just pulled a "
            f"{_RARITY_STARS[outcome.rarity]} {outcome.character.name}!"
        )
        await context.bot.send_message(
            chat_id=config.group_chat_id, message_thread_id=config.gacha_topic_id, text=text
        )
    except Exception as exc:
        logger.warning(
            "Failed to post rare-pull announcement for player={} rarity={}: {}",
            user.id,
            outcome.rarity,
            exc,
        )


async def _attempt_pull(
    session: Session,
    message: Message,
    player: gacha.PlayerRef,
    pull_fn: Callable[..., _PullResultT],
) -> _PullResultT | None:
    """Shared `/pull`/`/pull10` flow: resolve the standard banner, attempt
    the pull via `pull_fn` (`gacha.pull_single`/`gacha.pull_ten` — both
    take `(session, player, banner)`), and reply with a friendly message
    on the two known failure modes. Returns `None` (having already
    replied) on failure, or the pull result on success — the caller still
    owns formatting/sending the success reply, since that differs between
    a single pull and a 10-pull."""
    banner = gacha.get_or_create_standard_banner(session)
    try:
        return pull_fn(session, player, banner)
    except gacha.InsufficientLeyShardsError as exc:
        await message.reply_text(
            f"Not enough Ley Shards \U0001f48e — need {exc.required}, have {exc.available}."
        )
        return None
    except gacha.EmptyRarityPoolError:
        await message.reply_text("The roster is empty — ask an admin to run the AniList ingestion.")
        return None


async def pull_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return
    logger.debug("/pull from {}", user.id)
    if not in_private_chat(update):
        logger.debug("/pull from {} rejected: not a DM", user.id)
        await message.reply_text(NOT_IN_DM_MESSAGE)
        return

    player = gacha.PlayerRef(user.id, username=user.username)
    with session_scope() as session:
        outcome = await _attempt_pull(session, message, player, gacha.pull_single)
        if outcome is None:
            return

    await message.reply_photo(
        photo=outcome.character.image_url, caption=_format_single_caption(outcome)
    )
    await _announce_rare_pull(context, user, outcome)


async def pull_ten_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return
    logger.debug("/pull10 from {}", user.id)
    if not in_private_chat(update):
        logger.debug("/pull10 from {} rejected: not a DM", user.id)
        await message.reply_text(NOT_IN_DM_MESSAGE)
        return

    player = gacha.PlayerRef(user.id, username=user.username)
    with session_scope() as session:
        outcomes = await _attempt_pull(session, message, player, gacha.pull_ten)
        if outcomes is None:
            return

    summary = "\n".join(_format_outcome_line(outcome) for outcome in outcomes)
    await message.reply_text(f"10-Pull results:\n{summary}")

    for outcome in outcomes:
        if outcome.rarity in _HIGHLIGHT_RARITIES:
            await message.reply_photo(
                photo=outcome.character.image_url, caption=_format_single_caption(outcome)
            )
            await _announce_rare_pull(context, user, outcome)
