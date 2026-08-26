"""Telegram-facing handlers for gacha pulls: /pull and /pull10.

Thin by design (see CLAUDE.md): parse the Update, call services/gacha.py,
format the reply. No pity/rarity/economy rules live here.

DM-scoped, not group-topic-scoped — see ARCHITECTURE.md's "Commands &
topics" section and issue #17. A 4★+ pull also gets a best-effort public
announcement in the group's 🎰 Gacha topic (issue #18) on top of the DM
result — see `_announce_rare_pull`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, overload

from loguru import logger
from telegram import Update

from ley_shards_bot.commands.helpers import confirmation
from ley_shards_bot.commands.helpers.formatting import RARITY_STARS
from ley_shards_bot.commands.helpers.scoping import NOT_IN_DM_MESSAGE, in_private_chat
from ley_shards_bot.db import session_scope
from ley_shards_bot.models import Rarity
from ley_shards_bot.services import gacha
from ley_shards_bot.services.players import PlayerRef

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from telegram import Message, User
    from telegram.ext import ContextTypes

_CALLBACK_PREFIX = "pull"


class _PullType(StrEnum):
    """The two pull shapes a confirm/cancel prompt can be for — the
    `subject` this module hands to `commands.helpers.confirmation`'s
    callback_data encoding, and dispatched on throughout this module. A
    `StrEnum`, not a bare string, so a typo anywhere it's compared or
    constructed is a `ValueError`/type-checker error, not a silent drift
    between "the set of valid types" and "what actually runs"."""

    SINGLE = "single"
    TEN = "ten"


# 10-pull sends a text summary of everything, plus a photo card for these
# rarities only — every character in a highlight-only feed would be spam.
_HIGHLIGHT_RARITIES = frozenset({Rarity.FOUR_STAR, Rarity.FIVE_STAR})


def _rate_up_note(outcome: gacha.PullOutcome) -> str:
    if outcome.is_rate_up is True:
        return " 🌟 rate-up!"
    if outcome.is_rate_up is False:
        return " (lost the 50/50)"
    return ""


def _outcome_status_line(outcome: gacha.PullOutcome) -> str:
    if outcome.is_new:
        return "NEW"
    if outcome.constellation_level is not None:
        return f"Constellation {outcome.constellation_level}!"
    return f"dupe, +{outcome.echoes_gained} Echoes"


def _format_outcome_line(outcome: gacha.PullOutcome) -> str:
    stars = RARITY_STARS[outcome.rarity]
    return (
        f"{stars} {outcome.character.name} — {outcome.character.series} "
        f"[{_outcome_status_line(outcome)}]{_rate_up_note(outcome)}"
    )


def _outcome_status_caption(outcome: gacha.PullOutcome) -> str:
    if outcome.is_new:
        return "✨ NEW!"
    if outcome.constellation_level is not None:
        return f"⭐ Constellation {outcome.constellation_level}!"
    return f"Duplicate — +{outcome.echoes_gained} Echoes"


def _format_single_caption(outcome: gacha.PullOutcome) -> str:
    lines = [
        f"{RARITY_STARS[outcome.rarity]} {outcome.character.name}",
        outcome.character.series,
        _outcome_status_caption(outcome),
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
            f"{RARITY_STARS[outcome.rarity]} {outcome.character.name}!"
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


def _pull_failure_reply(
    exc: gacha.InsufficientLeyShardsError | gacha.EmptyRarityPoolError,
) -> str:
    """Shared failure text for the two known non-confirmation pull
    failures — surfaced identically whether the pull happened via
    `/pull`/`/pull10` or via the confirm callback."""
    if isinstance(exc, gacha.InsufficientLeyShardsError):
        return f"Not enough Ley Shards \U0001f48e — need {exc.required}, have {exc.available}."
    return "The roster is empty — ask an admin to run the AniList ingestion."


@overload
async def _attempt_pull(
    session: Session, message: Message, player: PlayerRef, pull_type: Literal[_PullType.SINGLE]
) -> gacha.PullOutcome | None: ...


@overload
async def _attempt_pull(
    session: Session, message: Message, player: PlayerRef, pull_type: Literal[_PullType.TEN]
) -> list[gacha.PullOutcome] | None: ...


async def _attempt_pull(
    session: Session,
    message: Message,
    player: PlayerRef,
    pull_type: _PullType,
) -> gacha.PullOutcome | list[gacha.PullOutcome] | None:
    """Shared `/pull`/`/pull10` flow: resolve the standard banner, attempt
    the pull (`gacha.pull_single`/`gacha.pull_ten`, dispatched on
    `pull_type`), and reply with a friendly message on the known failure
    modes. Returns `None` (having already replied) on failure, or the
    pull result on success — the caller still owns formatting/sending the
    success reply, since that differs between a single pull and a
    10-pull.

    A `ConfirmationRequiredError` (the pull would draw on Ley Shards
    directly, with no confirmation on file yet) is not a failure: it
    shows a Confirm/Cancel keyboard and returns `None`, same as the other
    two — the caller can't distinguish and doesn't need to."""
    banner = gacha.get_or_create_standard_banner(session)
    try:
        if pull_type == _PullType.SINGLE:
            return gacha.pull_single(session, player, banner)
        return gacha.pull_ten(session, player, banner)
    except gacha.ConfirmationRequiredError as exc:
        noun = "pull" if pull_type == _PullType.SINGLE else "10-pull"
        await message.reply_text(
            f"This {noun} needs {exc.ley_shards_required} Ley Shards \U0001f48e directly "
            f"({exc.tickets_to_spend} ticket(s) will also be used). Confirm?",
            reply_markup=confirmation.build_keyboard(
                _CALLBACK_PREFIX, player.telegram_user_id, pull_type
            ),
        )
        return None
    except (gacha.InsufficientLeyShardsError, gacha.EmptyRarityPoolError) as exc:
        await message.reply_text(_pull_failure_reply(exc))
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

    player = PlayerRef(user.id, username=user.username)
    with session_scope() as session:
        outcome = await _attempt_pull(session, message, player, _PullType.SINGLE)
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

    player = PlayerRef(user.id, username=user.username)
    with session_scope() as session:
        outcomes = await _attempt_pull(session, message, player, _PullType.TEN)
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


@dataclass(frozen=True)
class _ConfirmedPullContext:
    """Everything a confirmed pull needs to reply and announce with,
    bundled so the two per-pull-type helpers below stay under the
    parameter-count qlty checks (see CLAUDE.md's qlty guidance —
    genuinely restructuring, not loosening the check)."""

    context: ContextTypes.DEFAULT_TYPE
    clicking_user: User
    message: Message
    player: PlayerRef


async def _confirm_single_pull(ctx: _ConfirmedPullContext) -> None:
    with session_scope() as session:
        banner = gacha.get_or_create_standard_banner(session)
        try:
            outcome = gacha.pull_single(session, ctx.player, banner, confirmed_direct_spend=True)
        except (gacha.InsufficientLeyShardsError, gacha.EmptyRarityPoolError) as exc:
            await ctx.message.edit_text(_pull_failure_reply(exc))
            return

    await ctx.message.edit_text("Confirmed ✅")
    await ctx.message.reply_photo(
        photo=outcome.character.image_url, caption=_format_single_caption(outcome)
    )
    await _announce_rare_pull(ctx.context, ctx.clicking_user, outcome)


async def _confirm_ten_pull(ctx: _ConfirmedPullContext) -> None:
    with session_scope() as session:
        banner = gacha.get_or_create_standard_banner(session)
        try:
            outcomes = gacha.pull_ten(session, ctx.player, banner, confirmed_direct_spend=True)
        except (gacha.InsufficientLeyShardsError, gacha.EmptyRarityPoolError) as exc:
            await ctx.message.edit_text(_pull_failure_reply(exc))
            return

    await ctx.message.edit_text("Confirmed ✅")
    summary = "\n".join(_format_outcome_line(outcome) for outcome in outcomes)
    await ctx.message.reply_text(f"10-Pull results:\n{summary}")
    for outcome in outcomes:
        if outcome.rarity in _HIGHLIGHT_RARITIES:
            await ctx.message.reply_photo(
                photo=outcome.character.image_url, caption=_format_single_caption(outcome)
            )
            await _announce_rare_pull(ctx.context, ctx.clicking_user, outcome)


async def pull_confirmation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles a tap on the Confirm/Cancel keyboard `_attempt_pull` shows
    when a pull would draw on Ley Shards directly. All the generic
    callback plumbing — owner check, malformed-data/expired-message
    handling, following `collection.py`'s callback pattern — lives in
    `commands.helpers.confirmation.resolve_confirmation`, shared with
    any other confirm/cancel flow the bot grows later; this function
    only handles what's actually gacha-specific: turning the resolved
    `subject` back into a `_PullType` and running the pull.

    Confirm re-runs the pull with `confirmed_direct_spend=True` — the
    cost is recomputed fresh from the player's *current* balances, never
    trusted from the callback_data string, so a stale button tapped after
    a balance change is still re-validated. The prompt message is edited
    to a short ack (Telegram can't edit a text message into a photo
    message), and the real result is sent as a follow-up (see
    `_confirm_single_pull`/`_confirm_ten_pull`)."""
    resolved = await confirmation.resolve_confirmation(update, prefix=_CALLBACK_PREFIX)
    if resolved is None:
        return
    owner_id, message, subject, action = resolved

    try:
        pull_type = _PullType(subject)
    except ValueError:
        # Can't happen from a button this module itself built, but the
        # subject is an opaque string as far as resolve_confirmation is
        # concerned — validate it back out defensively rather than trust
        # it.
        logger.warning("pull confirmation carried an unknown pull_type {!r}", subject)
        return

    if action == confirmation.ConfirmAction.CANCEL:
        await message.edit_text("Cancelled — no Ley Shards spent.")
        return

    clicking_user = update.effective_user
    if clicking_user is None:
        return
    ctx = _ConfirmedPullContext(
        context=context,
        clicking_user=clicking_user,
        message=message,
        player=PlayerRef(owner_id),
    )
    if pull_type == _PullType.SINGLE:
        await _confirm_single_pull(ctx)
    else:
        await _confirm_ten_pull(ctx)
