"""Character collection viewing: owned-character lookup.

Framework-agnostic — no python-telegram-bot imports (see CLAUDE.md).
Generic pagination lives in services/pagination.py, not here — nothing
about paging a list is collection-specific (see issue #58).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import select

from ley_shards_bot.models import Character, PlayerCharacter, Rarity

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Highest rarity first, then alphabetical within a rarity tier.
_RARITY_SORT_ORDER = {Rarity.FIVE_STAR: 0, Rarity.FOUR_STAR: 1, Rarity.THREE_STAR: 2}


@dataclass(frozen=True)
class OwnedCharacter:
    character: Character
    copies_owned: int


def get_owned_characters(session: Session, player_id: int) -> list[OwnedCharacter]:
    rows = session.execute(
        select(PlayerCharacter, Character)
        .join(Character, PlayerCharacter.character_id == Character.anilist_id)
        .where(PlayerCharacter.player_id == player_id)
    ).all()
    owned = [
        OwnedCharacter(character=character, copies_owned=player_character.copies_owned)
        for player_character, character in rows
    ]
    owned.sort(key=lambda o: (_RARITY_SORT_ORDER[o.character.rarity], o.character.name))
    logger.debug("Collection lookup for {}: {} distinct characters", player_id, len(owned))
    return owned
