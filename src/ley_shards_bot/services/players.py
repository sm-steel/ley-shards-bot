"""Shared player lookup — used by economy.py and gacha.py alike, so it
lives in its own module rather than being owned by either. PlayerRef
follows the same reasoning: a player's Telegram identity (id + the
opportunistically captured @username) isn't gacha-specific, it just
started out defined in services/gacha.py because pull_single/pull_ten
were its first consumer — see issue #58.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import func, select

from ley_shards_bot.models import Player

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass(frozen=True)
class PlayerRef:
    """A player's Telegram identity: id plus the opportunistically
    captured @username (see #12) — bundled together because callers that
    need "who is this" treat it as one concept, not two independent
    parameters. See issue #49."""

    telegram_user_id: int
    username: str | None = None


def get_or_create_player(session: Session, player_ref: PlayerRef) -> Player:
    """Look up a player, creating one if this is their first time seen.

    Opportunistically captures/refreshes `player_ref.username` whenever
    the caller has one to offer (i.e. whenever a Telegram user object was
    actually available) — pass `PlayerRef(telegram_user_id)` (username
    defaults to `None`) when the caller doesn't know it, which leaves any
    already-stored username untouched rather than clobbering it.
    """
    player = session.get(Player, player_ref.telegram_user_id)
    if player is None:
        logger.info("New player: telegram_user_id={}", player_ref.telegram_user_id)
        player = Player(telegram_user_id=player_ref.telegram_user_id, username=player_ref.username)
        session.add(player)
        session.flush()
    elif player_ref.username is not None and player.username != player_ref.username:
        logger.debug(
            "Refreshing username for {}: {!r} -> {!r}",
            player_ref.telegram_user_id,
            player.username,
            player_ref.username,
        )
        player.username = player_ref.username
    return player


def find_player_by_username(session: Session, username: str) -> Player | None:
    """Look up a player by their captured @username, case-insensitively —
    Telegram usernames are unique case-insensitively, so `Aleksey` and
    `aleksey` must resolve to the same player. Returns `None` if no player
    has ever been seen with that username (see `get_or_create_player`'s
    opportunistic capture above — a player who's never used the bot won't
    be found even if the caller knows their real Telegram username).
    """
    return session.scalars(
        select(Player).where(func.lower(Player.username) == username.lower())
    ).first()
