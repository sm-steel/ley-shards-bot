"""Telegram-facing handlers for gacha pulls: /pull and /pull10.

Thin by design (see CLAUDE.md): parse the Update, call services/gacha.py,
format the reply. No pity/rarity/economy rules live here.

Scoped to the "🎰 Gacha" topic (config.gacha_topic_id) — see
ARCHITECTURE.md's Commands & topics section. Expects
`context.bot_data["config"]` to hold the running Config.
"""

from __future__ import annotations

from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from ley_shards_bot.db import session_scope
from ley_shards_bot.models import Rarity
from ley_shards_bot.services import gacha

_RARITY_STARS = {
    Rarity.THREE_STAR: "★★★",
    Rarity.FOUR_STAR: "★★★★",
    Rarity.FIVE_STAR: "★★★★★",
}

# 10-pull sends a text summary of everything, plus a photo card for these
# rarities only — every character in a highlight-only feed would be spam.
_HIGHLIGHT_RARITIES = frozenset({Rarity.FOUR_STAR, Rarity.FIVE_STAR})


def _in_gacha_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    config = context.bot_data["config"]
    message = update.effective_message
    return message is not None and message.message_thread_id == config.gacha_topic_id


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


async def pull_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return
    logger.debug("/pull from {}", user.id)
    if not _in_gacha_topic(update, context):
        logger.debug("/pull from {} rejected: wrong topic", user.id)
        await message.reply_text("Use this in the 🎰 Gacha topic.")
        return

    with session_scope() as session:
        banner = gacha.get_or_create_standard_banner(session)
        try:
            outcome = gacha.pull_single(session, user.id, banner)
        except gacha.InsufficientLeyShardsError as exc:
            await message.reply_text(
                f"Not enough Ley Shards \U0001f48e — need {exc.required}, have {exc.available}."
            )
            return
        except gacha.EmptyRarityPoolError:
            await message.reply_text(
                "The roster is empty — ask an admin to run the AniList ingestion."
            )
            return

    await message.reply_photo(
        photo=outcome.character.image_url, caption=_format_single_caption(outcome)
    )


async def pull_ten_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return
    logger.debug("/pull10 from {}", user.id)
    if not _in_gacha_topic(update, context):
        logger.debug("/pull10 from {} rejected: wrong topic", user.id)
        await message.reply_text("Use this in the 🎰 Gacha topic.")
        return

    with session_scope() as session:
        banner = gacha.get_or_create_standard_banner(session)
        try:
            outcomes = gacha.pull_ten(session, user.id, banner)
        except gacha.InsufficientLeyShardsError as exc:
            await message.reply_text(
                f"Not enough Ley Shards \U0001f48e — need {exc.required}, have {exc.available}."
            )
            return
        except gacha.EmptyRarityPoolError:
            await message.reply_text(
                "The roster is empty — ask an admin to run the AniList ingestion."
            )
            return

    summary = "\n".join(_format_outcome_line(outcome) for outcome in outcomes)
    await message.reply_text(f"10-Pull results:\n{summary}")

    for outcome in outcomes:
        if outcome.rarity in _HIGHLIGHT_RARITIES:
            await message.reply_photo(
                photo=outcome.character.image_url, caption=_format_single_caption(outcome)
            )
