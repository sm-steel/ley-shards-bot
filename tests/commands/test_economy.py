"""Tests for the economy command handlers.

These verify the thin Telegram-facing layer: does it call the right
service function, check admin/reply requirements, and reply with the
right text? The game-rule behavior itself is covered by
tests/services/test_economy.py — not re-tested here.

Update/Context are stubbed with plain mocks (constructing real
telegram.Update objects is heavier than this needs); session_scope is
monkeypatched to a real in-memory-SQLite session per call, so handlers
exercise real persistence.
"""

from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ley_shards_bot.commands import economy as economy_commands
from ley_shards_bot.models import Base, Player
from ley_shards_bot.services.economy import AWARD_GUESS_DAILY_LIMIT


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

    monkeypatch.setattr(economy_commands, "session_scope", fake_session_scope)
    return engine


def _make_update(
    *,
    user_id: int = 1,
    username: str | None = None,
    replied_user_id: int | None = None,
    replied_username: str | None = None,
) -> MagicMock:
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.username = username
    message = MagicMock()
    message.reply_text = AsyncMock()
    if replied_user_id is not None:
        message.reply_to_message.from_user.id = replied_user_id
        message.reply_to_message.from_user.username = replied_username
    else:
        message.reply_to_message = None
    update.effective_message = message
    return update


def _seed_player(engine, telegram_user_id: int, username: str, *, ley_shards: int = 0) -> None:
    with Session(engine) as session:
        session.add(
            Player(telegram_user_id=telegram_user_id, username=username, ley_shards=ley_shards)
        )
        session.commit()


def _make_context(*, admin_ids: frozenset[int] = frozenset(), args: list[str] | None = None):
    context = MagicMock()
    context.bot_data = {"config": SimpleNamespace(admin_user_ids=admin_ids)}
    context.args = args or []
    return context


class TestDailyCommand:
    async def test_first_claim_grants_and_replies(self, engine):
        update = _make_update(user_id=1)
        context = _make_context()

        await economy_commands.daily_command(update, context)

        update.effective_message.reply_text.assert_awaited_once()
        (text,), _ = update.effective_message.reply_text.call_args
        assert "60" in text
        with Session(engine) as session:
            player = session.get(Player, 1)
            assert player is not None
            assert player.ley_shards == 60

    async def test_second_claim_same_day_is_rejected(self, engine):
        update = _make_update(user_id=1)
        context = _make_context()
        await economy_commands.daily_command(update, context)

        update2 = _make_update(user_id=1)
        await economy_commands.daily_command(update2, context)

        (text,), _ = update2.effective_message.reply_text.call_args
        assert "already" in text.lower()
        with Session(engine) as session:
            player = session.get(Player, 1)
            assert player is not None
            assert player.ley_shards == 60


class TestTrickleHandler:
    async def test_grants_silently_without_replying(self, engine):
        update = _make_update(user_id=2)
        context = _make_context()

        await economy_commands.trickle_message_handler(update, context)

        update.effective_message.reply_text.assert_not_called()
        with Session(engine) as session:
            player = session.get(Player, 2)
            assert player is not None
            assert player.ley_shards == 20

    async def test_uses_the_fixed_game_day_boundary_not_utc_midnight(self, engine, monkeypatch):
        # 01:30 UTC is before the 02:00 UTC game-day boundary, so it's
        # still "yesterday" for reset purposes (see issue #42) — a plain
        # utc_now().date() would wrongly treat it as the new calendar day.
        monkeypatch.setattr(
            economy_commands, "utc_now", lambda: datetime(2026, 1, 2, 1, 30, tzinfo=UTC)
        )
        update = _make_update(user_id=2)
        context = _make_context()
        await economy_commands.trickle_message_handler(update, context)

        # A second trickle at 02:30 UTC the *same* calendar day is a new
        # game day (crossed the 02:00 boundary) — should still grant.
        monkeypatch.setattr(
            economy_commands, "utc_now", lambda: datetime(2026, 1, 2, 2, 30, tzinfo=UTC)
        )
        await economy_commands.trickle_message_handler(_make_update(user_id=2), context)

        with Session(engine) as session:
            player = session.get(Player, 2)
            assert player is not None
            assert player.ley_shards == 40  # granted both times


class TestAwardGuessCommand:
    async def test_non_admin_is_rejected(self, engine):
        update = _make_update(user_id=1, replied_user_id=5)
        context = _make_context(admin_ids=frozenset())

        await economy_commands.award_guess_command(update, context)

        (text,), _ = update.effective_message.reply_text.call_args
        assert "admin" in text.lower()
        with Session(engine) as session:
            assert session.get(Player, 5) is None

    async def test_requires_a_reply(self, engine):
        update = _make_update(user_id=1, replied_user_id=None)
        context = _make_context(admin_ids=frozenset({1}))

        await economy_commands.award_guess_command(update, context)

        (text,), _ = update.effective_message.reply_text.call_args
        assert "reply" in text.lower()

    async def test_admin_awards_the_replied_to_user(self, engine):
        update = _make_update(user_id=1, replied_user_id=5)
        context = _make_context(admin_ids=frozenset({1}))

        await economy_commands.award_guess_command(update, context)

        with Session(engine) as session:
            player = session.get(Player, 5)
            assert player is not None
            assert player.ley_shards == 15

    async def test_reports_limit_reached(self, engine):
        context = _make_context(admin_ids=frozenset({1}))
        for _ in range(AWARD_GUESS_DAILY_LIMIT):
            await economy_commands.award_guess_command(
                _make_update(user_id=1, replied_user_id=5), context
            )

        final = _make_update(user_id=1, replied_user_id=5)
        await economy_commands.award_guess_command(final, context)

        (text,), _ = final.effective_message.reply_text.call_args
        assert "limit" in text.lower()

    async def test_uses_the_fixed_game_day_boundary_not_utc_midnight(self, engine, monkeypatch):
        # Exhaust the daily limit just before the 02:00 UTC boundary...
        monkeypatch.setattr(
            economy_commands, "utc_now", lambda: datetime(2026, 1, 2, 1, 30, tzinfo=UTC)
        )
        context = _make_context(admin_ids=frozenset({1}))
        for _ in range(AWARD_GUESS_DAILY_LIMIT):
            await economy_commands.award_guess_command(
                _make_update(user_id=1, replied_user_id=5), context
            )

        # ...then try again just after it, same calendar day. A plain
        # utc_now().date() would still call this "today" and reject it;
        # the fixed game-day boundary (issue #42) treats it as reset.
        monkeypatch.setattr(
            economy_commands, "utc_now", lambda: datetime(2026, 1, 2, 2, 30, tzinfo=UTC)
        )
        final = _make_update(user_id=1, replied_user_id=5)
        await economy_commands.award_guess_command(final, context)

        with Session(engine) as session:
            player = session.get(Player, 5)
            assert player is not None
            assert player.ley_shards == 15 * (AWARD_GUESS_DAILY_LIMIT + 1)

    async def test_admin_awards_by_username(self, engine):
        _seed_player(engine, telegram_user_id=5, username="aleksey")
        update = _make_update(user_id=1)
        context = _make_context(admin_ids=frozenset({1}), args=["@aleksey"])

        await economy_commands.award_guess_command(update, context)

        with Session(engine) as session:
            player = session.get(Player, 5)
            assert player is not None
            assert player.ley_shards == 15

    async def test_unknown_username_reports_friendly_error(self, engine):
        update = _make_update(user_id=1)
        context = _make_context(admin_ids=frozenset({1}), args=["@nobody"])

        await economy_commands.award_guess_command(update, context)

        (text,), _ = update.effective_message.reply_text.call_args
        assert "haven't seen" in text.lower()
        assert "@nobody" in text


class TestGrantCommand:
    async def test_non_admin_is_rejected(self, engine):
        update = _make_update(user_id=1, replied_user_id=5)
        context = _make_context(admin_ids=frozenset(), args=["100"])

        await economy_commands.grant_command(update, context)

        (text,), _ = update.effective_message.reply_text.call_args
        assert "admin" in text.lower()

    async def test_missing_amount_reports_usage(self, engine):
        update = _make_update(user_id=1, replied_user_id=5)
        context = _make_context(admin_ids=frozenset({1}), args=[])

        await economy_commands.grant_command(update, context)

        (text,), _ = update.effective_message.reply_text.call_args
        assert "usage" in text.lower()

    async def test_admin_grants_arbitrary_amount(self, engine):
        update = _make_update(user_id=1, replied_user_id=5)
        context = _make_context(admin_ids=frozenset({1}), args=["250"])

        await economy_commands.grant_command(update, context)

        with Session(engine) as session:
            player = session.get(Player, 5)
            assert player is not None
            assert player.ley_shards == 250

    async def test_admin_grants_by_username(self, engine):
        _seed_player(engine, telegram_user_id=5, username="aleksey")
        update = _make_update(user_id=1)
        context = _make_context(admin_ids=frozenset({1}), args=["@aleksey", "250"])

        await economy_commands.grant_command(update, context)

        with Session(engine) as session:
            player = session.get(Player, 5)
            assert player is not None
            assert player.ley_shards == 250

    async def test_unknown_username_reports_friendly_error(self, engine):
        update = _make_update(user_id=1)
        context = _make_context(admin_ids=frozenset({1}), args=["@nobody", "250"])

        await economy_commands.grant_command(update, context)

        (text,), _ = update.effective_message.reply_text.call_args
        assert "haven't seen" in text.lower()
        assert "@nobody" in text

    async def test_username_targeting_missing_amount_reports_usage(self, engine):
        _seed_player(engine, telegram_user_id=5, username="aleksey")
        update = _make_update(user_id=1)
        context = _make_context(admin_ids=frozenset({1}), args=["@aleksey"])

        await economy_commands.grant_command(update, context)

        (text,), _ = update.effective_message.reply_text.call_args
        assert "usage" in text.lower()


class TestRevokeCommand:
    async def test_non_admin_is_rejected(self, engine):
        update = _make_update(user_id=1, replied_user_id=5)
        context = _make_context(admin_ids=frozenset(), args=["100"])

        await economy_commands.revoke_command(update, context)

        (text,), _ = update.effective_message.reply_text.call_args
        assert "admin" in text.lower()

    async def test_missing_amount_reports_usage(self, engine):
        update = _make_update(user_id=1, replied_user_id=5)
        context = _make_context(admin_ids=frozenset({1}), args=[])

        await economy_commands.revoke_command(update, context)

        (text,), _ = update.effective_message.reply_text.call_args
        assert "usage" in text.lower()

    async def test_admin_revokes_arbitrary_amount(self, engine):
        _seed_player(engine, telegram_user_id=5, username="aleksey", ley_shards=250)
        update = _make_update(user_id=1, replied_user_id=5)
        context = _make_context(admin_ids=frozenset({1}), args=["100"])

        await economy_commands.revoke_command(update, context)

        with Session(engine) as session:
            player = session.get(Player, 5)
            assert player is not None
            assert player.ley_shards == 150

    async def test_admin_revokes_by_username(self, engine):
        _seed_player(engine, telegram_user_id=5, username="aleksey", ley_shards=250)
        update = _make_update(user_id=1)
        context = _make_context(admin_ids=frozenset({1}), args=["@aleksey", "100"])

        await economy_commands.revoke_command(update, context)

        with Session(engine) as session:
            player = session.get(Player, 5)
            assert player is not None
            assert player.ley_shards == 150

    async def test_unknown_username_reports_friendly_error(self, engine):
        update = _make_update(user_id=1)
        context = _make_context(admin_ids=frozenset({1}), args=["@nobody", "100"])

        await economy_commands.revoke_command(update, context)

        (text,), _ = update.effective_message.reply_text.call_args
        assert "haven't seen" in text.lower()
        assert "@nobody" in text

    async def test_clamps_at_zero_rather_than_going_negative(self, engine):
        _seed_player(engine, telegram_user_id=5, username="aleksey", ley_shards=50)
        update = _make_update(user_id=1, replied_user_id=5)
        context = _make_context(admin_ids=frozenset({1}), args=["100"])

        await economy_commands.revoke_command(update, context)

        with Session(engine) as session:
            player = session.get(Player, 5)
            assert player is not None
            assert player.ley_shards == 0
