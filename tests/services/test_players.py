"""Tests for get_or_create_player's username capture (issue #12): should
opportunistically set/refresh players.username whenever a caller has one to
offer, and leave it alone otherwise.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ley_shards_bot.models import Base, Player
from ley_shards_bot.services.players import get_or_create_player


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


class TestGetOrCreatePlayer:
    def test_new_player_has_no_username_by_default(self, session):
        player = get_or_create_player(session, 1)

        assert player.username is None

    def test_new_player_captures_username_when_given(self, session):
        player = get_or_create_player(session, 1, username="aleksey")

        assert player.username == "aleksey"

    def test_existing_player_refreshes_username_on_change(self, session):
        get_or_create_player(session, 1, username="aleksey")
        session.commit()

        player = get_or_create_player(session, 1, username="new_handle")

        assert player.username == "new_handle"

    def test_existing_player_username_untouched_when_none_given(self, session):
        get_or_create_player(session, 1, username="aleksey")
        session.commit()

        player = get_or_create_player(session, 1)

        assert player.username == "aleksey"

    def test_existing_player_row_persists_directly(self, session):
        get_or_create_player(session, 1, username="aleksey")
        session.commit()

        stored = session.get(Player, 1)
        assert stored is not None
        assert stored.username == "aleksey"
