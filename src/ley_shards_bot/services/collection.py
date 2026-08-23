"""Character collection viewing: owned-character lookup + pagination.

Framework-agnostic — no python-telegram-bot imports (see CLAUDE.md).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, TypeVar

from sqlalchemy import select

from ley_shards_bot.models import Character, PlayerCharacter, Rarity

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm import Session

PAGE_SIZE = 10

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
    return owned


T = TypeVar("T")


@dataclass(frozen=True)
class Page(Generic[T]):
    items: list[T]
    page_number: int
    total_pages: int
    has_previous: bool
    has_next: bool


def paginate(items: Sequence[T], page_number: int, page_size: int = PAGE_SIZE) -> Page[T]:
    total_pages = max(1, math.ceil(len(items) / page_size))
    page_number = max(0, min(page_number, total_pages - 1))
    start = page_number * page_size
    end = start + page_size
    return Page(
        items=list(items[start:end]),
        page_number=page_number,
        total_pages=total_pages,
        has_previous=page_number > 0,
        has_next=page_number < total_pages - 1,
    )
