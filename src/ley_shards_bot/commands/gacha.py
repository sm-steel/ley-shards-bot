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
from typing import TYPE_CHECKING, Literal, cast, overload

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.ext import ContextTypes

from ley_shards_bot.commands.helpers.formatting import RARITY_STARS
from ley_shards_bot.commands.helpers.scoping import NOT_IN_DM_MESSAGE, in_private_chat
from ley_shards_bot.db import session_scope
from ley_shards_bot.models import Rarity
from ley_shards_bot.services import gacha
from ley_shards_bot.services.players import PlayerRef

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from telegram import CallbackQuery, User

_CALLBACK_PREFIX = "pull"
# The only two valid pull_type tokens in a pull: callback_data string —
# checked here (parsing) and dispatched on by literal comparison in
# _attempt_pull/pull_confirmation_callback, so a typo in either place
# shows up as a real ConfirmationRequiredError/mismatch, not a silent
# drift between "the set of valid types" and "what actually runs".
_PULL_TYPES = frozenset({"single", "ten"})

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


def _callback_data(owner_id: int, pull_type: str, action: str) -> str:
    return f"{_CALLBACK_PREFIX}:{owner_id}:{pull_type}:{action}"


def _parse_callback_data(data: str) -> tuple[int, str, str] | None:
    parts = data.split(":")
    if len(parts) != 4 or parts[0] != _CALLBACK_PREFIX:
        return None
    if parts[2] not in _PULL_TYPES or parts[3] not in {"confirm", "cancel"}:
        return None
    try:
        return int(parts[1]), parts[2], parts[3]
    except ValueError:
        return None


def _build_confirmation_keyboard(owner_id: int, pull_type: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Confirm", callback_data=_callback_data(owner_id, pull_type, "confirm")
                ),
                InlineKeyboardButton(
                    "Cancel", callback_data=_callback_data(owner_id, pull_type, "cancel")
                ),
            ]
        ]
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
    session: Session, message: Message, player: PlayerRef, pull_type: Literal["single"]
) -> gacha.PullOutcome | None: ...


@overload
async def _attempt_pull(
    session: Session, message: Message, player: PlayerRef, pull_type: Literal["ten"]
) -> list[gacha.PullOutcome] | None: ...


async def _attempt_pull(
    session: Session,
    message: Message,
    player: PlayerRef,
    pull_type: str,
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
        if pull_type == "single":
            return gacha.pull_single(session, player, banner)
        return gacha.pull_ten(session, player, banner)
    except gacha.ConfirmationRequiredError as exc:
        noun = "pull" if pull_type == "single" else "10-pull"
        await message.reply_text(
            f"This {noun} needs {exc.ley_shards_required} Ley Shards \U0001f48e directly "
            f"({exc.tickets_to_spend} ticket(s) will also be used). Confirm?",
            reply_markup=_build_confirmation_keyboard(player.telegram_user_id, pull_type),
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
        outcome = await _attempt_pull(session, message, player, "single")
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
        outcomes = await _attempt_pull(session, message, player, "ten")
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

    query: CallbackQuery
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
            await ctx.query.edit_message_text(_pull_failure_reply(exc))
            return

    await ctx.query.edit_message_text("Confirmed ✅")
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
            await ctx.query.edit_message_text(_pull_failure_reply(exc))
            return

    await ctx.query.edit_message_text("Confirmed ✅")
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
    when a pull would draw on Ley Shards directly. Follows
    `collection.py`'s callback pattern exactly: prefix + owner_id +
    fields in the callback_data, `query.answer()` before the owner check
    (with `show_alert=True` and no edit for a non-owner click) and after
    it, and a silent `query.answer()` + no edit for malformed data.

    Confirm re-runs the pull with `confirmed_direct_spend=True` — the
    cost is recomputed fresh from the player's *current* balances, never
    trusted from the callback_data string, so a stale button tapped after
    a balance change is still re-validated. The prompt message is edited
    to a short ack (Telegram can't edit a text message into a photo
    message), and the real result is sent as a follow-up (see
    `_confirm_single_pull`/`_confirm_ten_pull`)."""
    query = update.callback_query
    clicking_user = update.effective_user
    if query is None or clicking_user is None or query.data is None or query.message is None:
        return
    # query.message is typed as MaybeInaccessibleMessage (Message |
    # InaccessibleMessage) because Bot API 7.0 added business-connection
    # messages that can go stale — this bot never uses business
    # connections, and this callback only ever fires against a message we
    # ourselves just sent moments earlier, so it's always a real, usable
    # Message here.
    message = cast(Message, query.message)

    parsed = _parse_callback_data(query.data)
    if parsed is None:
        await query.answer()
        return
    owner_id, pull_type, action = parsed

    if clicking_user.id != owner_id:
        logger.warning("{} tried to confirm {}'s pull", clicking_user.id, owner_id)
        await query.answer("This isn't your pull to confirm.", show_alert=True)
        return
    await query.answer()

    if action == "cancel":
        await query.edit_message_text("Cancelled — no Ley Shards spent.")
        return

    ctx = _ConfirmedPullContext(
        query=query,
        context=context,
        clicking_user=clicking_user,
        message=message,
        player=PlayerRef(owner_id),
    )
    if pull_type == "single":
        await _confirm_single_pull(ctx)
    else:
        await _confirm_ten_pull(ctx)
