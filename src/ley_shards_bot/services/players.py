"""Shared player lookup — used by economy.py and gacha.py alike, so it
lives in its own module rather than being owned by either.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import func, select

from ley_shards_bot.models import Player

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def get_or_create_player(
    session: Session, telegram_user_id: int, username: str | None = None
) -> Player:
    """Look up a player, creating one if this is their first time seen.

    Opportunistically captures/refreshes `username` whenever the caller has
    one to offer (i.e. whenever a Telegram user object was actually
    available) — pass `None` (the default) when the caller doesn't know it,
    which leaves any already-stored username untouched rather than
    clobbering it.
    """
    player = session.get(Player, telegram_user_id)
    if player is None:
        logger.info("New player: telegram_user_id={}", telegram_user_id)
        player = Player(telegram_user_id=telegram_user_id, username=username)
        session.add(player)
        session.flush()
    elif username is not None and player.username != username:
        logger.debug(
            "Refreshing username for {}: {!r} -> {!r}",
            telegram_user_id,
            player.username,
            username,
        )
        player.username = username
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
