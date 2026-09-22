"""Target resolution for commands that act on another player:
@username-first, falling back to reply-to-message targeting.

Nothing here checks permissions — it only answers "which player is this
command about." It happens to only be used by admin commands today
(/grant, /revoke, /award_guess in commands/economy.py) but that's a fact
about today's callers, not about this module — see issue #58.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ley_shards_bot.services.players import PlayerRef, find_player_by_username

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from telegram import Update


@dataclass(frozen=True)
class ResolvedTarget:
    player: PlayerRef
    remaining_args: list[str]


def _replied_to_user_id(update: Update) -> int | None:
    """The user a reply-based command targets — whoever sent the message
    being replied to. None if this command wasn't used as a reply."""
    message = update.effective_message
    if message is None or message.reply_to_message is None:
        return None
    replied_user = message.reply_to_message.from_user
    return replied_user.id if replied_user is not None else None


def _replied_to_username(update: Update) -> str | None:
    """The @username (if any) of a reply-based command's target —
    captured the same way as the acting user's own, so a player can become
    @username-targetable just by being replied to, even if they've never
    used the bot themselves. See issue #12."""
    message = update.effective_message
    if message is None or message.reply_to_message is None:
        return None
    replied_user = message.reply_to_message.from_user
    return replied_user.username if replied_user is not None else None


def _username_from_args(args: list[str]) -> str | None:
    """The @username (without the @) a command was targeted at via its
    first argument, e.g. `/grant @aleksey 500` -> "aleksey". None if there
    are no args or the first one isn't an @username — in which case the
    caller falls back to reply-based targeting. See issue #13."""
    if not args or not args[0].startswith("@"):
        return None
    return args[0][1:]


async def resolve_target(
    update: Update,
    session: Session,
    args: list[str],
    *,
    reply_hint: str,
) -> ResolvedTarget | None:
    """Resolve a command's target player, trying `@username` (via the
    first arg) before falling back to reply-to-message targeting — see
    issue #13. On success, returns a `ResolvedTarget` whose
    `remaining_args` has the leading `@username` consumed if there was
    one (so callers parse e.g. an amount from it instead of from `args`
    directly). On failure, sends a friendly reply itself (unknown
    username, or no target at all) and returns None.

    Doesn't take `message` separately — every caller has already
    null-checked `update.effective_message` before calling this, so it's
    re-derived here rather than passed as a redundant parameter (see
    issue #48).
    """
    message = update.effective_message
    if message is None:
        return None

    target_username = _username_from_args(args)
    if target_username is not None:
        target_player = find_player_by_username(session, target_username)
        if target_player is None:
            await message.reply_text(f"Haven't seen @{target_username} use the bot yet.")
            return None
        return ResolvedTarget(
            PlayerRef(target_player.telegram_user_id, target_player.username), args[1:]
        )

    target_id = _replied_to_user_id(update)
    if target_id is None:
        await message.reply_text(reply_hint)
        return None
    return ResolvedTarget(PlayerRef(target_id, _replied_to_username(update)), args)
