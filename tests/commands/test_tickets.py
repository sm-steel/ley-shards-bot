"""Tests for the /buy_ticket command handler.

Thin-layer tests: DM scoping, usage/argument validation, and
error-to-reply mapping. Ticket-purchase math itself is covered by
tests/services/test_tickets.py, not repeated here.
"""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ley_shards_bot.commands import tickets as tickets_commands
from ley_shards_bot.models import Base, Player
from ley_shards_bot.services.gacha import PULL_COST_LEY_SHARDS


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

    monkeypatch.setattr(tickets_commands, "session_scope", fake_session_scope)
    return engine


def _seed_player(engine, telegram_user_id: int = 1, ley_shards: int = 100_000) -> None:
    with Session(engine) as session:
        session.add(Player(telegram_user_id=telegram_user_id, ley_shards=ley_shards))
        session.commit()


def _make_update(
    *,
    user_id: int = 1,
    chat_type: str = "private",
    username: str | None = None,
) -> MagicMock:
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.username = username
    update.effective_chat = SimpleNamespace(type=chat_type)
    message = MagicMock()
    message.reply_text = AsyncMock()
    update.effective_message = message
    return update


def _make_context(args: list[str]) -> MagicMock:
    context = MagicMock()
    context.args = args
    return context


class TestBuyTicketCommand:
    async def test_rejects_outside_a_dm(self, engine):
        _seed_player(engine)
        update = _make_update(chat_type="group")
        context = _make_context(["standard", "1"])

        await tickets_commands.buy_ticket_command(update, context)

        (text,), _ = update.effective_message.reply_text.call_args
        assert "dm" in text.lower()

    async def test_buys_standard_tickets(self, engine):
        _seed_player(engine)
        update = _make_update()
        context = _make_context(["standard", "2"])

        await tickets_commands.buy_ticket_command(update, context)

        (text,), _ = update.effective_message.reply_text.call_args
        assert "2" in text
        assert "standard" in text.lower()

    async def test_rejects_an_invalid_ticket_type(self, engine):
        _seed_player(engine)
        update = _make_update()
        context = _make_context(["weapon", "1"])

        await tickets_commands.buy_ticket_command(update, context)

        (text,), _ = update.effective_message.reply_text.call_args
        assert "standard" in text.lower() or "event" in text.lower()

    async def test_reports_insufficient_ley_shards(self, engine):
        _seed_player(engine, ley_shards=10)
        update = _make_update()
        context = _make_context(["standard", "1"])

        await tickets_commands.buy_ticket_command(update, context)

        (text,), _ = update.effective_message.reply_text.call_args
        assert str(PULL_COST_LEY_SHARDS) in text

    async def test_rejects_a_malformed_count(self, engine):
        _seed_player(engine)
        update = _make_update()
        context = _make_context(["standard", "nope"])

        await tickets_commands.buy_ticket_command(update, context)

        (text,), _ = update.effective_message.reply_text.call_args
        assert "Usage" in text
