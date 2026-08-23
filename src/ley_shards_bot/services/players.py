"""Shared player lookup — used by economy.py and gacha.py alike, so it
lives in its own module rather than being owned by either.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ley_shards_bot.models import Player

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def get_or_create_player(session: Session, telegram_user_id: int) -> Player:
    player = session.get(Player, telegram_user_id)
    if player is None:
        player = Player(telegram_user_id=telegram_user_id)
        session.add(player)
        session.flush()
    return player
