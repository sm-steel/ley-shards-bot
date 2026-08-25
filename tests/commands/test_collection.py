"""Tests for the /collection command and its pagination callback."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ley_shards_bot.commands import collection as collection_commands
from ley_shards_bot.models import Base, Character, Player, PlayerCharacter, Rarity
from ley_shards_bot.services.pagination import PAGE_SIZE


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

    monkeypatch.setattr(collection_commands, "session_scope", fake_session_scope)
    return engine


def _seed_owned_characters(engine, player_id: int, count: int) -> None:
    with Session(engine) as session:
        session.add(Player(telegram_user_id=player_id))
        for i in range(count):
            session.add(
                Character(
                    anilist_id=i,
                    name=f"Character {i}",
                    series="Test Series",
                    image_url=f"https://example.invalid/{i}.png",
                    rarity=Rarity.THREE_STAR,
                    base_hp=50,
                    base_atk=20,
                    base_def=15,
                    base_spd=30,
                )
            )
            session.add(PlayerCharacter(player_id=player_id, character_id=i))
        session.commit()


def _seed_owned_character_with_copies(engine, player_id: int, copies_owned: int) -> None:
    with Session(engine) as session:
        session.add(Player(telegram_user_id=player_id))
        session.add(
            Character(
                anilist_id=1,
                name="Alpha",
                series="Test Series",
                image_url="https://example.invalid/1.png",
                rarity=Rarity.THREE_STAR,
                base_hp=50,
                base_atk=20,
                base_def=15,
                base_spd=30,
            )
        )
        session.add(PlayerCharacter(player_id=player_id, character_id=1, copies_owned=copies_owned))
        session.commit()


def _make_update(*, user_id: int = 1, chat_type: str = "private") -> MagicMock:
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_chat = SimpleNamespace(type=chat_type)
    message = MagicMock()
    message.reply_text = AsyncMock()
    update.effective_message = message
    update.callback_query = None
    return update


def _make_callback_update(*, clicking_user_id: int, data: str) -> MagicMock:
    update = MagicMock()
    update.effective_user.id = clicking_user_id
    query = MagicMock()
    query.data = data
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query
    return update


class TestCollectionCommand:
    async def test_empty_collection_message(self, engine):
        with Session(engine) as session:
            session.add(Player(telegram_user_id=1))
            session.commit()
        update = _make_update(user_id=1)
        context = MagicMock()

        await collection_commands.collection_command(update, context)

        (text,), kwargs = update.effective_message.reply_text.call_args
        assert "pull" in text.lower()
        assert kwargs.get("reply_markup") is None

    async def test_single_page_has_no_keyboard(self, engine):
        _seed_owned_characters(engine, 1, count=3)
        update = _make_update(user_id=1)
        context = MagicMock()

        await collection_commands.collection_command(update, context)

        _args, kwargs = update.effective_message.reply_text.call_args
        assert kwargs.get("reply_markup") is None

    async def test_multi_page_shows_a_next_button(self, engine):
        _seed_owned_characters(engine, 1, count=PAGE_SIZE + 1)
        update = _make_update(user_id=1)
        context = MagicMock()

        await collection_commands.collection_command(update, context)

        _args, kwargs = update.effective_message.reply_text.call_args
        markup = kwargs["reply_markup"]
        buttons = [b for row in markup.inline_keyboard for b in row]
        assert any("Next" in b.text for b in buttons)
        assert not any("Prev" in b.text for b in buttons)

    async def test_shows_no_constellation_suffix_for_a_single_copy(self, engine):
        _seed_owned_character_with_copies(engine, 1, copies_owned=1)
        update = _make_update(user_id=1)
        context = MagicMock()

        await collection_commands.collection_command(update, context)

        (text,), _kwargs = update.effective_message.reply_text.call_args
        assert " C" not in text.split("\n")[1]

    async def test_shows_constellation_level_for_a_leveled_character(self, engine):
        _seed_owned_character_with_copies(engine, 1, copies_owned=4)
        update = _make_update(user_id=1)
        context = MagicMock()

        await collection_commands.collection_command(update, context)

        (text,), _kwargs = update.effective_message.reply_text.call_args
        assert "C3" in text

    async def test_a_maxed_character_shows_c6_never_c7(self, engine):
        """Boundary test: 7 copies (CONSTELLATION_MAX_COPIES, fully
        maxed) must display "C6" — the highest valid level — never
        "C7"."""
        _seed_owned_character_with_copies(engine, 1, copies_owned=7)
        update = _make_update(user_id=1)
        context = MagicMock()

        await collection_commands.collection_command(update, context)

        (text,), _kwargs = update.effective_message.reply_text.call_args
        assert "C6" in text
        assert "C7" not in text

    async def test_legacy_data_above_the_cap_still_shows_c6_never_higher(self, engine):
        """Phase 1's old duplicate-handling code had no cap, so a
        pre-existing row could already have copies_owned above
        CONSTELLATION_MAX_COPIES. The display must clamp regardless —
        this must never render as "C7", "C11", etc."""
        _seed_owned_character_with_copies(engine, 1, copies_owned=12)
        update = _make_update(user_id=1)
        context = MagicMock()

        await collection_commands.collection_command(update, context)

        (text,), _kwargs = update.effective_message.reply_text.call_args
        assert "C6" in text
        assert "C7" not in text
        assert "C11" not in text

    async def test_rejects_outside_dm(self, engine):
        _seed_owned_characters(engine, 1, count=3)
        update = _make_update(user_id=1, chat_type="group")
        context = MagicMock()

        await collection_commands.collection_command(update, context)

        (text,), kwargs = update.effective_message.reply_text.call_args
        assert "dm" in text.lower()
        assert kwargs.get("reply_markup") is None


class TestCollectionPageCallback:
    async def test_owner_can_page_forward(self, engine):
        _seed_owned_characters(engine, 1, count=PAGE_SIZE + 1)
        update = _make_callback_update(clicking_user_id=1, data="coll:1:1")
        context = MagicMock()

        await collection_commands.collection_page_callback(update, context)

        update.callback_query.answer.assert_awaited_once_with()
        update.callback_query.edit_message_text.assert_awaited_once()
        (text,), _kwargs = update.callback_query.edit_message_text.call_args
        assert "page 2" in text.lower()

    async def test_rejects_a_different_user_clicking_the_button(self, engine):
        _seed_owned_characters(engine, 1, count=PAGE_SIZE + 1)
        update = _make_callback_update(clicking_user_id=2, data="coll:1:1")
        context = MagicMock()

        await collection_commands.collection_page_callback(update, context)

        update.callback_query.edit_message_text.assert_not_called()
        update.callback_query.answer.assert_awaited_once()
        _args, kwargs = update.callback_query.answer.call_args
        assert kwargs.get("show_alert") is True

    async def test_ignores_malformed_callback_data(self, engine):
        update = _make_callback_update(clicking_user_id=1, data="not-a-real-payload")
        context = MagicMock()

        await collection_commands.collection_page_callback(update, context)

        update.callback_query.edit_message_text.assert_not_called()
