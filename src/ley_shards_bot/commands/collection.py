"""Telegram-facing handler for /collection: a paginated view of a player's
owned characters via inline-keyboard paging.

Thin by design (see CLAUDE.md): parse the Update, call
services/collection.py, format the reply. The callback_data for paging
buttons embeds the *owner's* user id (not just the page number) so that
another player clicking the button in a shared group chat can't page
through — or silently swap the message into showing — someone else's
collection.
"""

from __future__ import annotations

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ley_shards_bot.commands.helpers.formatting import RARITY_STARS
from ley_shards_bot.commands.helpers.scoping import NOT_IN_DM_MESSAGE, in_private_chat
from ley_shards_bot.db import session_scope
from ley_shards_bot.services.collection import get_owned_characters
from ley_shards_bot.services.pagination import PAGE_SIZE, Page, paginate

# Registered elsewhere (task #8's Application wiring) with a
# CallbackQueryHandler(pattern=f"^{_CALLBACK_PREFIX}:").
_CALLBACK_PREFIX = "coll"


def _callback_data(owner_id: int, page_number: int) -> str:
    return f"{_CALLBACK_PREFIX}:{owner_id}:{page_number}"


def _parse_callback_data(data: str) -> tuple[int, int] | None:
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != _CALLBACK_PREFIX:
        return None
    try:
        return int(parts[1]), int(parts[2])
    except ValueError:
        return None


def _format_page_text(page: Page, total_owned: int) -> str:
    if total_owned == 0:
        return "You haven't pulled any characters yet — try /pull!"
    lines = [
        f"Your collection ({total_owned} characters) — page "
        f"{page.page_number + 1}/{page.total_pages}:"
    ]
    for owned in page.items:
        stars = RARITY_STARS[owned.character.rarity]
        copies = f" x{owned.copies_owned}" if owned.copies_owned > 1 else ""
        lines.append(f"{stars} {owned.character.name}{copies}")
    return "\n".join(lines)


def _build_keyboard(page: Page, owner_id: int) -> InlineKeyboardMarkup | None:
    if not page.has_previous and not page.has_next:
        return None
    buttons = []
    if page.has_previous:
        buttons.append(
            InlineKeyboardButton(
                "◀ Prev", callback_data=_callback_data(owner_id, page.page_number - 1)
            )
        )
    if page.has_next:
        buttons.append(
            InlineKeyboardButton(
                "Next ▶", callback_data=_callback_data(owner_id, page.page_number + 1)
            )
        )
    return InlineKeyboardMarkup([buttons])


async def collection_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG001
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    logger.debug("/collection from {}", user.id)
    if not in_private_chat(update):
        logger.debug("/collection from {} rejected: not a DM", user.id)
        await message.reply_text(NOT_IN_DM_MESSAGE)
        return

    with session_scope() as session:
        owned = get_owned_characters(session, user.id)

    page = paginate(owned, 0, PAGE_SIZE)
    await message.reply_text(
        _format_page_text(page, len(owned)), reply_markup=_build_keyboard(page, user.id)
    )


async def collection_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG001
    query = update.callback_query
    clicking_user = update.effective_user
    if query is None or clicking_user is None or query.data is None:
        return

    parsed = _parse_callback_data(query.data)
    if parsed is None:
        await query.answer()
        return
    owner_id, requested_page = parsed

    if clicking_user.id != owner_id:
        logger.warning("{} tried to page through {}'s collection", clicking_user.id, owner_id)
        await query.answer("This isn't your collection.", show_alert=True)
        return
    await query.answer()

    with session_scope() as session:
        owned = get_owned_characters(session, owner_id)

    page = paginate(owned, requested_page, PAGE_SIZE)
    await query.edit_message_text(
        _format_page_text(page, len(owned)), reply_markup=_build_keyboard(page, owner_id)
    )
