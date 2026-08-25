"""Shared DM-scoping check for player-facing commands.

From Phase 1.1, player commands (`/daily`, `/pull`, `/pull10`,
`/collection`, and later `/banners`/`/banner_info`) work only in a
private 1-to-1 chat with the bot — this inverts Phase 1's group-topic
scoping rather than just relaxing it. See ARCHITECTURE.md's "Commands &
topics" section and issue #17.

Admin commands (`/grant`, `/revoke`, `/award_guess`) are untouched by
this — they keep working in both DM and the group, same as today.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

#: Reply text every DM-scoped command sends when used outside a private chat.
NOT_IN_DM_MESSAGE = "Use this in a DM with the bot, not the group."


def in_private_chat(update: Update) -> bool:
    chat = update.effective_chat
    return chat is not None and chat.type == "private"


def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    config = context.bot_data["config"]
    user = update.effective_user
    return user is not None and user.id in config.admin_user_ids
