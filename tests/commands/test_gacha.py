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
from telegram import User

from ley_shards_bot.commands import gacha as gacha_commands
from ley_shards_bot.models import BannerType, Base, Character, PityState, Player, Rarity
from ley_shards_bot.services import gacha as gacha_service
from ley_shards_bot.services.gacha import FIVE_STAR_HARD_PITY


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
    *,
    user_id: int = 1,
    chat_type: str = "private",
    username: str | None = None,
    first_name: str = "Aleksey",
) -> MagicMock:
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.username = username
    update.effective_user.first_name = first_name
    update.effective_chat = SimpleNamespace(type=chat_type)
    message = MagicMock()
    message.reply_text = AsyncMock()
    message.reply_photo = AsyncMock()
    update.effective_message = message
    return update


def _make_context(*, group_chat_id: int = -1001, gacha_topic_id: int = 5) -> MagicMock:
    context = MagicMock()
    context.bot_data = {
        "config": SimpleNamespace(group_chat_id=group_chat_id, gacha_topic_id=gacha_topic_id)
    }
    context.bot.send_message = AsyncMock()
    return context


class TestPullCommand:
    async def test_rejects_outside_dm(self, engine):
        _seed_roster(engine)
        _seed_player(engine)
        update = _make_update(chat_type="group")
        context = _make_context()

        await gacha_commands.pull_command(update, context)

        update.effective_message.reply_text.assert_awaited_once()
        update.effective_message.reply_photo.assert_not_called()
        (text,), _ = update.effective_message.reply_text.call_args
        assert "dm" in text.lower()

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
    async def test_rejects_outside_dm(self, engine):
        _seed_roster(engine)
        _seed_player(engine)
        update = _make_update(chat_type="group")
        context = _make_context()

        await gacha_commands.pull_ten_command(update, context)

        update.effective_message.reply_photo.assert_not_called()
        (text,), _ = update.effective_message.reply_text.call_args
        assert "dm" in text.lower()

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


def _make_outcome(rarity: Rarity, *, character_name: str = "Frieren") -> gacha_service.PullOutcome:
    character = Character(
        anilist_id=99,
        name=character_name,
        series="Frieren: Beyond Journey's End",
        image_url="https://example.invalid/frieren.png",
        rarity=rarity,
        base_hp=1,
        base_atk=1,
        base_def=1,
        base_spd=1,
    )
    return gacha_service.PullOutcome(
        character=character, rarity=rarity, is_new=True, echoes_gained=0, is_rate_up=None
    )


class TestAnnounceRarePull:
    async def test_posts_to_the_group_gacha_topic_for_a_five_star(self):
        context = _make_context(group_chat_id=-100999, gacha_topic_id=42)
        user = User(id=1, first_name="Aleksey", is_bot=False)
        outcome = _make_outcome(Rarity.FIVE_STAR)

        await gacha_commands._announce_rare_pull(context, user, outcome)

        context.bot.send_message.assert_awaited_once()
        _args, kwargs = context.bot.send_message.call_args
        assert kwargs["chat_id"] == -100999
        assert kwargs["message_thread_id"] == 42
        assert kwargs["text"] == "🎉 Aleksey just pulled a ★★★★★ Frieren!"

    async def test_posts_for_a_four_star_too(self):
        context = _make_context()
        user = User(id=1, first_name="Aleksey", is_bot=False)
        outcome = _make_outcome(Rarity.FOUR_STAR)

        await gacha_commands._announce_rare_pull(context, user, outcome)

        context.bot.send_message.assert_awaited_once()

    async def test_does_not_post_for_a_three_star(self):
        context = _make_context()
        user = User(id=1, first_name="Aleksey", is_bot=False)
        outcome = _make_outcome(Rarity.THREE_STAR)

        await gacha_commands._announce_rare_pull(context, user, outcome)

        context.bot.send_message.assert_not_called()

    async def test_a_failed_announcement_does_not_raise(self):
        context = _make_context()
        context.bot.send_message.side_effect = RuntimeError("Telegram is down")
        user = User(id=1, first_name="Aleksey", is_bot=False)
        outcome = _make_outcome(Rarity.FIVE_STAR)

        await gacha_commands._announce_rare_pull(context, user, outcome)  # must not raise

    async def test_a_missing_config_does_not_raise(self):
        context = _make_context()
        context.bot_data = {}  # config missing from bot_data entirely
        user = User(id=1, first_name="Aleksey", is_bot=False)
        outcome = _make_outcome(Rarity.FIVE_STAR)

        await gacha_commands._announce_rare_pull(context, user, outcome)  # must not raise

        context.bot.send_message.assert_not_called()


def _seed_hard_pity(engine, *, banner_type: BannerType, telegram_user_id: int = 1) -> None:
    with Session(engine) as session:
        session.add(
            PityState(
                player_id=telegram_user_id,
                banner_type=banner_type,
                pulls_since_last_5star=FIVE_STAR_HARD_PITY - 1,
            )
        )
        session.commit()


class TestRarePullGroupAnnouncement:
    async def test_pull_command_announces_a_guaranteed_five_star(self, engine):
        _seed_roster(engine)
        _seed_player(engine)
        _seed_hard_pity(engine, banner_type=BannerType.STANDARD)
        update = _make_update(first_name="Aleksey")
        context = _make_context(group_chat_id=-100999, gacha_topic_id=7)

        await gacha_commands.pull_command(update, context)

        update.effective_message.reply_photo.assert_awaited_once()  # DM result still sent
        context.bot.send_message.assert_awaited_once()
        _args, kwargs = context.bot.send_message.call_args
        assert kwargs["chat_id"] == -100999
        assert kwargs["message_thread_id"] == 7
        assert kwargs["text"] == "🎉 Aleksey just pulled a ★★★★★ Five Star!"

    async def test_pull_ten_command_announces_the_guaranteed_five_star(self, engine):
        _seed_roster(engine)
        _seed_player(engine)
        _seed_hard_pity(engine, banner_type=BannerType.STANDARD)
        update = _make_update(first_name="Aleksey")
        context = _make_context(group_chat_id=-100999, gacha_topic_id=7)

        await gacha_commands.pull_ten_command(update, context)

        update.effective_message.reply_text.assert_awaited_once()  # DM summary still sent
        assert context.bot.send_message.await_count >= 1
        for _args, kwargs in context.bot.send_message.call_args_list:
            assert kwargs["chat_id"] == -100999
            assert kwargs["message_thread_id"] == 7
