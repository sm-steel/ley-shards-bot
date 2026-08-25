"""Tests for the collection service: owned-character lookup."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ley_shards_bot.models import Base, Character, Player, PlayerCharacter, Rarity
from ley_shards_bot.services.collection import get_owned_characters


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _add_character(session, anilist_id: int, rarity: Rarity, name: str) -> None:
    session.add(
        Character(
            anilist_id=anilist_id,
            name=name,
            series="Test Series",
            image_url=f"https://example.invalid/{anilist_id}.png",
            rarity=rarity,
            base_hp=50,
            base_atk=20,
            base_def=15,
            base_spd=30,
        )
    )


class TestGetOwnedCharacters:
    def test_empty_for_a_player_with_no_pulls(self, session):
        session.add(Player(telegram_user_id=1))
        session.commit()

        assert get_owned_characters(session, 1) == []

    def test_includes_copies_owned(self, session):
        session.add(Player(telegram_user_id=1))
        _add_character(session, 1, Rarity.THREE_STAR, "Alpha")
        session.commit()
        session.add(PlayerCharacter(player_id=1, character_id=1, copies_owned=3))
        session.commit()

        (owned,) = get_owned_characters(session, 1)

        assert owned.character.name == "Alpha"
        assert owned.copies_owned == 3

    def test_sorted_highest_rarity_first_then_name(self, session):
        session.add(Player(telegram_user_id=1))
        _add_character(session, 1, Rarity.THREE_STAR, "Zed")
        _add_character(session, 2, Rarity.FIVE_STAR, "Bravo")
        _add_character(session, 3, Rarity.FOUR_STAR, "Charlie")
        _add_character(session, 4, Rarity.THREE_STAR, "Alpha")
        session.commit()
        session.add_all(
            [
                PlayerCharacter(player_id=1, character_id=1),
                PlayerCharacter(player_id=1, character_id=2),
                PlayerCharacter(player_id=1, character_id=3),
                PlayerCharacter(player_id=1, character_id=4),
            ]
        )
        session.commit()

        owned = get_owned_characters(session, 1)

        assert [o.character.name for o in owned] == ["Bravo", "Charlie", "Alpha", "Zed"]

    def test_only_returns_this_players_characters(self, session):
        session.add_all([Player(telegram_user_id=1), Player(telegram_user_id=2)])
        _add_character(session, 1, Rarity.THREE_STAR, "Alpha")
        session.commit()
        session.add(PlayerCharacter(player_id=2, character_id=1))
        session.commit()

        assert get_owned_characters(session, 1) == []
        assert len(get_owned_characters(session, 2)) == 1
