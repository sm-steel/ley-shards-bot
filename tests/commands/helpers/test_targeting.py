"""Tests for resolve_target: admin-style @username-or-reply targeting,
shared by any command that needs to resolve which player it's about (today
that's /grant, /revoke, /award_guess in commands/economy.py — nothing
about resolve_target itself is admin-specific, see issue #58).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ley_shards_bot.commands.helpers.targeting import resolve_target
from ley_shards_bot.models import Base, Player

REPLY_HINT = "Reply to the target player's message, or use @username."


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _make_update(
    *, replied_user_id: int | None = None, replied_username: str | None = None
) -> MagicMock:
    update = MagicMock()
    message = MagicMock()
    message.reply_text = AsyncMock()
    if replied_user_id is not None:
        message.reply_to_message.from_user.id = replied_user_id
        message.reply_to_message.from_user.username = replied_username
    else:
        message.reply_to_message = None
    update.effective_message = message
    return update


class TestResolveTarget:
    async def test_resolves_by_username_when_first_arg_is_an_at_mention(self, session):
        session.add(Player(telegram_user_id=5, username="aleksey"))
        session.commit()
        update = _make_update()

        result = await resolve_target(update, session, ["@aleksey", "100"], reply_hint=REPLY_HINT)

        assert result == (5, "aleksey", ["100"])

    async def test_unknown_username_replies_and_returns_none(self, session):
        update = _make_update()

        result = await resolve_target(update, session, ["@nobody", "100"], reply_hint=REPLY_HINT)

        assert result is None
        update.effective_message.reply_text.assert_awaited_once()
        (text,), _ = update.effective_message.reply_text.call_args
        assert "@nobody" in text

    async def test_falls_back_to_reply_target_when_no_username_arg(self, session):
        update = _make_update(replied_user_id=7, replied_username="mira")

        result = await resolve_target(update, session, ["100"], reply_hint=REPLY_HINT)

        assert result == (7, "mira", ["100"])

    async def test_no_username_and_no_reply_shows_the_hint(self, session):
        update = _make_update()

        result = await resolve_target(update, session, [], reply_hint=REPLY_HINT)

        assert result is None
        (text,), _ = update.effective_message.reply_text.call_args
        assert text == REPLY_HINT
