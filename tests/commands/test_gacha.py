"""Tests for the gacha command handlers.

Thin-layer tests: topic scoping, error-to-reply mapping, and that a
successful pull results in a reply_photo call. Pity/rarity/economy math
is covered by tests/services/test_gacha.py, not repeated here.
"""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ley_shards_bot.commands import gacha as gacha_commands
from ley_shards_bot.models import Base, Character, Player, Rarity

GACHA_TOPIC_ID = 42


@pytest.fixture
def engine(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    @contextmanager
    def fake_session_scope():
        session = Session(engine, expire_on_commit=False)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(gacha_commands, "session_scope", fake_session_scope)
    return engine


def _seed_roster(engine) -> None:
    # One character per rarity — a roll can land on any of the three, and
    # an empty pool for whichever one gets rolled is a real (tested
    # separately) error path, not something these tests want to hit by
    # accident.
    with Session(engine) as session:
        session.add_all(
            [
                Character(
                    anilist_id=1,
                    name="Three Star",
                    series="Test Series",
                    image_url="https://example.invalid/3.png",
                    rarity=Rarity.THREE_STAR,
                    base_hp=50,
                    base_atk=20,
                    base_def=15,
                    base_spd=30,
                ),
                Character(
                    anilist_id=2,
                    name="Four Star",
                    series="Test Series",
                    image_url="https://example.invalid/4.png",
                    rarity=Rarity.FOUR_STAR,
                    base_hp=65,
                    base_atk=35,
                    base_def=25,
                    base_spd=45,
                ),
                Character(
                    anilist_id=3,
                    name="Five Star",
                    series="Test Series",
                    image_url="https://example.invalid/5.png",
                    rarity=Rarity.FIVE_STAR,
                    base_hp=90,
                    base_atk=50,
                    base_def=35,
                    base_spd=60,
                ),
            ]
        )
        session.commit()


def _seed_player(engine, telegram_user_id: int = 1, ley_shards: int = 100_000) -> None:
    with Session(engine) as session:
        session.add(Player(telegram_user_id=telegram_user_id, ley_shards=ley_shards))
        session.commit()


def _make_update(
    *, user_id: int = 1, thread_id: int | None = GACHA_TOPIC_ID, username: str | None = None
) -> MagicMock:
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.username = username
    message = MagicMock()
    message.reply_text = AsyncMock()
    message.reply_photo = AsyncMock()
    message.message_thread_id = thread_id
    update.effective_message = message
    return update


def _make_context() -> MagicMock:
    context = MagicMock()
    context.bot_data = {"config": SimpleNamespace(gacha_topic_id=GACHA_TOPIC_ID)}
    return context


class TestPullCommand:
    async def test_rejects_outside_gacha_topic(self, engine):
        _seed_roster(engine)
        _seed_player(engine)
        update = _make_update(thread_id=999)
        context = _make_context()

        await gacha_commands.pull_command(update, context)

        update.effective_message.reply_text.assert_awaited_once()
        update.effective_message.reply_photo.assert_not_called()
        (text,), _ = update.effective_message.reply_text.call_args
        assert "gacha" in text.lower()

    async def test_successful_pull_replies_with_a_photo_card(self, engine):
        _seed_roster(engine)
        _seed_player(engine)
        update = _make_update()
        context = _make_context()

        await gacha_commands.pull_command(update, context)

        update.effective_message.reply_photo.assert_awaited_once()
        _args, kwargs = update.effective_message.reply_photo.call_args
        assert kwargs["photo"] in {
            "https://example.invalid/3.png",
            "https://example.invalid/4.png",
            "https://example.invalid/5.png",
        }
        assert "Star" in kwargs["caption"]  # one of the three seeded character names

    async def test_insufficient_balance_replies_without_a_photo(self, engine):
        _seed_roster(engine)
        _seed_player(engine, ley_shards=10)
        update = _make_update()
        context = _make_context()

        await gacha_commands.pull_command(update, context)

        update.effective_message.reply_photo.assert_not_called()
        (text,), _ = update.effective_message.reply_text.call_args
        assert "ley shards" in text.lower()

    async def test_empty_roster_replies_with_a_helpful_message(self, engine):
        _seed_player(engine)
        update = _make_update()
        context = _make_context()

        await gacha_commands.pull_command(update, context)

        update.effective_message.reply_photo.assert_not_called()
        (text,), _ = update.effective_message.reply_text.call_args
        assert "roster" in text.lower()


class TestPullTenCommand:
    async def test_rejects_outside_gacha_topic(self, engine):
        _seed_roster(engine)
        _seed_player(engine)
        update = _make_update(thread_id=None)
        context = _make_context()

        await gacha_commands.pull_ten_command(update, context)

        update.effective_message.reply_photo.assert_not_called()

    async def test_successful_pull_ten_sends_a_summary(self, engine):
        _seed_roster(engine)
        _seed_player(engine)
        update = _make_update()
        context = _make_context()

        await gacha_commands.pull_ten_command(update, context)

        update.effective_message.reply_text.assert_awaited_once()
        (text,), _ = update.effective_message.reply_text.call_args
        assert text.startswith("10-Pull results:")
        # One result line per pull, plus the header.
        assert len(text.splitlines()) == 1 + 10

    async def test_insufficient_balance_sends_no_summary(self, engine):
        _seed_roster(engine)
        _seed_player(engine, ley_shards=10)
        update = _make_update()
        context = _make_context()

        await gacha_commands.pull_ten_command(update, context)

        (text,), _ = update.effective_message.reply_text.call_args
        assert "ley shards" in text.lower()
        assert "10-pull" not in text.lower()
