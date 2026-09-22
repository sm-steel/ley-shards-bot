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
from telegram import Message, User

from ley_shards_bot.commands import gacha as gacha_commands
from ley_shards_bot.models import (
    BannerType,
    Base,
    Character,
    CurrencyType,
    PityState,
    Player,
    Rarity,
)
from ley_shards_bot.services import currency
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


def _seed_tickets(engine, telegram_user_id: int, count: int) -> None:
    with Session(engine) as session:
        currency.add(session, telegram_user_id, CurrencyType.STANDARD_TICKET, count)
        session.commit()


def _seed_roster_and_rich_player(engine, telegram_user_id: int = 1) -> None:
    """Roster + a Ley-Shards-rich player, deliberately with NO ticket
    balance — used by the confirm/cancel tests, which want the
    ley-shards-direct-spend path to be reachable."""
    _seed_roster(engine)
    _seed_player(engine, telegram_user_id=telegram_user_id)


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


def _make_callback_update(*, clicking_user_id: int, data: str) -> MagicMock:
    update = MagicMock()
    update.effective_user.id = clicking_user_id
    query = MagicMock()
    query.data = data
    query.answer = AsyncMock()
    # spec=Message so isinstance(query.message, Message) — the real guard
    # commands.helpers.confirmation.resolve_confirmation uses to reject an
    # InaccessibleMessage — actually passes for these "normal" tests.
    query.message = MagicMock(spec=Message)
    query.message.edit_text = AsyncMock()
    query.message.reply_photo = AsyncMock()
    query.message.reply_text = AsyncMock()
    update.callback_query = query
    return update


def _make_callback_update_with_inaccessible_message(
    *, clicking_user_id: int, data: str
) -> MagicMock:
    """Like `_make_callback_update`, but `query.message` deliberately does
    NOT satisfy `isinstance(query.message, Message)` — simulating PTB's
    `InaccessibleMessage` stand-in for a deleted/expired message, without
    needing to construct a real one."""
    update = MagicMock()
    update.effective_user.id = clicking_user_id
    query = MagicMock()
    query.data = data
    query.answer = AsyncMock()
    query.message = MagicMock()  # no spec=Message -> isinstance check fails
    update.callback_query = query
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
        _seed_tickets(engine, 1, 1)
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
        _seed_tickets(engine, 1, 1)
        update = _make_update()
        context = _make_context()

        await gacha_commands.pull_command(update, context)

        update.effective_message.reply_photo.assert_not_called()
        (text,), _ = update.effective_message.reply_text.call_args
        assert "roster" in text.lower()
        # The failed pull must not have charged the ticket it would have
        # spent on success (see the currency-debit-before-pull bug this
        # regression guards against).
        with Session(engine) as session:
            assert currency.get_balance(session, 1, CurrencyType.STANDARD_TICKET) == 1


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
        _seed_tickets(engine, 1, 10)
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


def _make_outcome(
    rarity: Rarity,
    *,
    character_name: str = "Frieren",
    is_new: bool = True,
    constellation_level: int | None = None,
    echoes_gained: int = 0,
) -> gacha_service.PullOutcome:
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
        character=character,
        rarity=rarity,
        is_new=is_new,
        echoes_gained=echoes_gained,
        constellation_level=constellation_level,
        is_rate_up=None,
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
        _seed_tickets(engine, 1, 1)
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
        _seed_tickets(engine, 1, 10)
        _seed_hard_pity(engine, banner_type=BannerType.STANDARD)
        update = _make_update(first_name="Aleksey")
        context = _make_context(group_chat_id=-100999, gacha_topic_id=7)

        await gacha_commands.pull_ten_command(update, context)

        update.effective_message.reply_text.assert_awaited_once()  # DM summary still sent
        assert context.bot.send_message.await_count >= 1
        for _args, kwargs in context.bot.send_message.call_args_list:
            assert kwargs["chat_id"] == -100999
            assert kwargs["message_thread_id"] == 7


class TestPullRequiresConfirmationWithoutATicket:
    async def test_pull_shows_a_confirm_cancel_keyboard(self, engine):
        _seed_roster_and_rich_player(engine, 1)  # no ticket seeded
        update = _make_update(user_id=1)
        context = MagicMock()
        context.bot_data = {"config": MagicMock()}

        await gacha_commands.pull_command(update, context)

        update.effective_message.reply_text.assert_awaited_once()
        (_text,), kwargs = update.effective_message.reply_text.call_args
        markup = kwargs["reply_markup"]
        callback_datas = [btn.callback_data for row in markup.inline_keyboard for btn in row]
        assert any(cd.startswith("pull:1:single:confirm") for cd in callback_datas)
        assert any(cd.startswith("pull:1:single:cancel") for cd in callback_datas)

    async def test_pull_ten_shows_a_confirm_cancel_keyboard(self, engine):
        _seed_roster_and_rich_player(engine, 1)
        update = _make_update(user_id=1)
        context = MagicMock()
        context.bot_data = {"config": MagicMock()}

        await gacha_commands.pull_ten_command(update, context)

        (_text,), kwargs = update.effective_message.reply_text.call_args
        markup = kwargs["reply_markup"]
        callback_datas = [btn.callback_data for row in markup.inline_keyboard for btn in row]
        assert any(cd.startswith("pull:1:ten:confirm") for cd in callback_datas)


class TestPullConfirmationCallback:
    async def test_owner_confirms_a_single_pull(self, engine):
        _seed_roster_and_rich_player(engine, 1)
        update = _make_callback_update(clicking_user_id=1, data="pull:1:single:confirm")
        context = MagicMock()
        context.bot_data = {"config": MagicMock()}

        await gacha_commands.pull_confirmation_callback(update, context)

        update.callback_query.message.edit_text.assert_awaited_once()
        update.callback_query.message.reply_photo.assert_awaited_once()

    async def test_owner_cancels(self, engine):
        _seed_roster_and_rich_player(engine, 1)
        update = _make_callback_update(clicking_user_id=1, data="pull:1:single:cancel")
        context = MagicMock()

        await gacha_commands.pull_confirmation_callback(update, context)

        update.callback_query.message.edit_text.assert_awaited_once()
        (text,), _ = update.callback_query.message.edit_text.call_args
        assert "cancel" in text.lower()
        update.callback_query.message.reply_photo.assert_not_called()

    async def test_rejects_a_different_user_clicking_confirm(self, engine):
        _seed_roster_and_rich_player(engine, 1)
        update = _make_callback_update(clicking_user_id=2, data="pull:1:single:confirm")
        context = MagicMock()

        await gacha_commands.pull_confirmation_callback(update, context)

        update.callback_query.message.edit_text.assert_not_called()
        _args, kwargs = update.callback_query.answer.call_args
        assert kwargs.get("show_alert") is True

    async def test_ignores_malformed_callback_data(self, engine):
        update = _make_callback_update(clicking_user_id=1, data="not-a-real-payload")
        context = MagicMock()

        await gacha_commands.pull_confirmation_callback(update, context)

        update.callback_query.message.edit_text.assert_not_called()

    async def test_confirm_with_now_insufficient_ley_shards(self, engine):
        # seed a player with 0 ley_shards and no tickets
        with Session(engine) as session:
            session.add(Player(telegram_user_id=1, ley_shards=0))
            session.commit()
        update = _make_callback_update(clicking_user_id=1, data="pull:1:single:confirm")
        context = MagicMock()

        await gacha_commands.pull_confirmation_callback(update, context)

        (text,), _ = update.callback_query.message.edit_text.call_args
        assert "Not enough Ley Shards" in text

    async def test_expired_message_replies_with_a_safe_fallback(self, engine):
        """query.message can be an InaccessibleMessage (PTB's stand-in for
        a deleted/expired message) rather than a real Message — no
        reply_photo/reply_text to call in that case, so the callback must
        bail out with a show_alert answer instead of attempting a pull or
        touching query.message at all."""
        _seed_roster_and_rich_player(engine, 1)
        update = _make_callback_update_with_inaccessible_message(
            clicking_user_id=1, data="pull:1:single:confirm"
        )
        context = MagicMock()

        await gacha_commands.pull_confirmation_callback(update, context)

        update.callback_query.message.edit_text.assert_not_called()
        update.callback_query.answer.assert_awaited_once()
        _args, kwargs = update.callback_query.answer.call_args
        assert kwargs.get("show_alert") is True


class TestFormatOutcomeLine:
    def test_new_character(self):
        outcome = _make_outcome(Rarity.THREE_STAR, is_new=True)

        assert "[NEW]" in gacha_commands._format_outcome_line(outcome)

    def test_constellation_level_up(self):
        outcome = _make_outcome(Rarity.THREE_STAR, is_new=False, constellation_level=3)

        assert "[Constellation 3!]" in gacha_commands._format_outcome_line(outcome)

    def test_echoes_conversion(self):
        outcome = _make_outcome(Rarity.FIVE_STAR, is_new=False, echoes_gained=50)

        assert "[dupe, +50 Echoes]" in gacha_commands._format_outcome_line(outcome)


class TestFormatSingleCaption:
    def test_new_character(self):
        outcome = _make_outcome(Rarity.THREE_STAR, is_new=True)

        assert "✨ NEW!" in gacha_commands._format_single_caption(outcome)

    def test_constellation_level_up(self):
        outcome = _make_outcome(Rarity.THREE_STAR, is_new=False, constellation_level=6)

        assert "⭐ Constellation 6!" in gacha_commands._format_single_caption(outcome)

    def test_echoes_conversion(self):
        outcome = _make_outcome(Rarity.FOUR_STAR, is_new=False, echoes_gained=15)

        assert "Duplicate — +15 Echoes" in gacha_commands._format_single_caption(outcome)
