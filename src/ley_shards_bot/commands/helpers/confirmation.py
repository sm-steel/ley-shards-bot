"""Generic Telegram confirm/cancel inline-keyboard flow, shared by any
command that needs an explicit "are you sure" gate before an
irreversible action — `/pull`'s direct-Ley-Shards-spend prompt today
(see `GACHA.md`'s "Pull costs"), and whatever other confirmation the
bot needs next; this exists precisely so the next one is a few lines
of glue, not a second hand-rolled copy of the same callback plumbing.

Owns the callback_data encoding, the Confirm/Cancel keyboard, and the
owner-check/malformed-data/expired-message boilerplate every such flow
shares. Does NOT own what actually happens on confirm/cancel — that
stays with the calling command module, since it differs per caller
(what to charge, what to reply with).

`subject` is an opaque string slot for whatever a specific confirmation
needs to remember about what's being confirmed (gacha's "single"/"ten",
say). This module never interprets it — callers encode their own
`StrEnum` into it and validate it back out themselves; that keeps this
module ignorant of any one caller's domain, which is the whole point.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message

if TYPE_CHECKING:
    from telegram import Update


class ConfirmAction(StrEnum):
    CONFIRM = "confirm"
    CANCEL = "cancel"


@dataclass(frozen=True)
class ConfirmationRef:
    """Everything `resolve_confirmation` hands back once a callback click
    has been validated: who owns it, the message to reply/edit on, and
    what was being confirmed. `subject` is the caller's opaque token —
    see the module docstring."""

    owner_id: int
    message: Message
    subject: str
    action: ConfirmAction


@dataclass(frozen=True)
class _ParsedCallbackData:
    owner_id: int
    subject: str
    action: ConfirmAction


def callback_data(prefix: str, owner_id: int, subject: str, action: ConfirmAction) -> str:
    return f"{prefix}:{owner_id}:{subject}:{action}"


def _parse_callback_data(prefix: str, data: str) -> _ParsedCallbackData | None:
    parts = data.split(":")
    if len(parts) != 4 or parts[0] != prefix:
        return None
    try:
        return _ParsedCallbackData(int(parts[1]), parts[2], ConfirmAction(parts[3]))
    except ValueError:
        return None


def build_keyboard(prefix: str, owner_id: int, subject: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Confirm",
                    callback_data=callback_data(prefix, owner_id, subject, ConfirmAction.CONFIRM),
                ),
                InlineKeyboardButton(
                    "Cancel",
                    callback_data=callback_data(prefix, owner_id, subject, ConfirmAction.CANCEL),
                ),
            ]
        ]
    )


async def resolve_confirmation(update: Update, *, prefix: str) -> ConfirmationRef | None:
    """Validate and parse a confirm/cancel callback click for the given
    `prefix`: rejects a non-owner click (`show_alert=True`, no edit),
    silently ignores malformed callback_data (bare `query.answer()`, no
    edit), and bails safely (a "this has expired" alert) if the prompt
    message itself has gone inaccessible since it was sent — deleted, or
    the bot restarted in between.

    On success, returns a `ConfirmationRef` — `message` is the
    now-`isinstance`-narrowed prompt message, safe to
    `.edit_text()`/`.reply_text()`/`.reply_photo()` on; `subject` is
    whatever opaque token the caller encoded via `callback_data()` (not
    validated against any caller-specific enum here — callers convert
    it back to their own `StrEnum` and handle a bad value themselves).
    On failure, has already answered/replied as appropriate — the
    caller should just return.
    """
    query = update.callback_query
    clicking_user = update.effective_user
    if query is None or clicking_user is None or query.data is None:
        return None
    if not isinstance(query.message, Message):
        # query.message is typed as MaybeInaccessibleMessage (Message |
        # InaccessibleMessage) — PTB's stand-in for a message that's
        # since been deleted or otherwise gone inaccessible (its own
        # docstring: "messages that are e.g. deleted"). Realistically
        # narrow (a confirm/cancel prompt is normally clicked within
        # seconds), but not impossible, and an InaccessibleMessage has
        # no reply_photo/reply_text/edit_text to call, so bail out
        # safely rather than risking an AttributeError downstream.
        await query.answer("This confirmation has expired.", show_alert=True)
        return None
    message = query.message

    parsed = _parse_callback_data(prefix, query.data)
    if parsed is None:
        await query.answer()
        return None

    if clicking_user.id != parsed.owner_id:
        logger.warning(
            "{} tried to respond to {}'s confirmation (prefix={})",
            clicking_user.id,
            parsed.owner_id,
            prefix,
        )
        await query.answer("This isn't yours to confirm.", show_alert=True)
        return None
    await query.answer()

    return ConfirmationRef(
        owner_id=parsed.owner_id, message=message, subject=parsed.subject, action=parsed.action
    )
