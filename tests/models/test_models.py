"""Schema-level tests: tables can be created and round-trip real rows.

Uses an in-memory SQLite engine — fast, no Docker needed for unit tests.
The Alembic migration (tested at deploy time against real MariaDB) is the
thing that actually creates the production schema; this test exists so a
broken model definition fails fast, locally, in CI.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ley_shards_bot.models import (
    Banner,
    BannerType,
    Base,
    Character,
    PityState,
    Player,
    PlayerCharacter,
    Pull,
    Rarity,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_player_defaults_to_zero_balances(session):
    player = Player(telegram_user_id=111)
    session.add(player)
    session.commit()

    stored = session.get(Player, 111)
    assert stored.ley_shards == 0
    assert stored.echoes == 0
    assert stored.last_daily_claimed_at is None


def test_character_stores_roster_data(session):
    character = Character(
        anilist_id=1,
        name="Frieren",
        series="Frieren: Beyond Journey's End",
        image_url="https://example.invalid/frieren.png",
        rarity=Rarity.FIVE_STAR,
        base_hp=100,
        base_atk=50,
        base_def=40,
        base_spd=60,
    )
    session.add(character)
    session.commit()

    stored = session.get(Character, 1)
    assert stored.rarity == Rarity.FIVE_STAR


def test_standard_banner_has_no_rate_up(session):
    banner = Banner(type=BannerType.STANDARD, name="Standard Wish")
    session.add(banner)
    session.commit()

    assert banner.id is not None
    assert banner.rate_up_character_id is None


def test_event_banner_references_rate_up_character(session):
    character = Character(
        anilist_id=2,
        name="Himmel",
        series="Frieren: Beyond Journey's End",
        image_url="https://example.invalid/himmel.png",
        rarity=Rarity.FIVE_STAR,
        base_hp=90,
        base_atk=55,
        base_def=35,
        base_spd=50,
    )
    session.add(character)
    session.commit()

    banner = Banner(
        type=BannerType.EVENT,
        name="Hero's Return",
        rate_up_character_id=character.anilist_id,
    )
    session.add(banner)
    session.commit()

    assert banner.rate_up_character_id == 2


def test_player_character_tracks_copies_owned(session):
    session.add(Player(telegram_user_id=222))
    session.add(
        Character(
            anilist_id=3,
            name="Fern",
            series="Frieren: Beyond Journey's End",
            image_url="https://example.invalid/fern.png",
            rarity=Rarity.FOUR_STAR,
            base_hp=70,
            base_atk=45,
            base_def=30,
            base_spd=55,
        )
    )
    session.commit()

    ownership = PlayerCharacter(player_id=222, character_id=3, copies_owned=2)
    session.add(ownership)
    session.commit()

    stored = session.get(PlayerCharacter, (222, 3))
    assert stored.copies_owned == 2


def test_pity_state_is_tracked_per_player_and_banner_type(session):
    session.add(Player(telegram_user_id=333))
    session.commit()

    pity = PityState(player_id=333, banner_type=BannerType.EVENT, pulls_since_last_5star=42)
    session.add(pity)
    session.commit()

    stored = session.get(PityState, (333, BannerType.EVENT))
    assert stored.pulls_since_last_5star == 42
    assert stored.pulls_since_last_4star == 0
    assert stored.guaranteed_rate_up is False


def test_pull_logs_a_single_history_row(session):
    session.add(Player(telegram_user_id=444))
    session.add(
        Character(
            anilist_id=4,
            name="Stark",
            series="Frieren: Beyond Journey's End",
            image_url="https://example.invalid/stark.png",
            rarity=Rarity.THREE_STAR,
            base_hp=60,
            base_atk=40,
            base_def=25,
            base_spd=45,
        )
    )
    banner = Banner(type=BannerType.STANDARD, name="Standard Wish")
    session.add(banner)
    session.commit()

    pull = Pull(
        player_id=444,
        banner_id=banner.id,
        character_id=4,
        pulled_at=datetime.now(UTC),
    )
    session.add(pull)
    session.commit()

    stored = session.get(Pull, pull.id)
    assert stored.character_id == 4
    assert stored.banner_id == banner.id
