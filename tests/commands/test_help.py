"""Tests for /help: player commands are always listed; admin-only ones
(/grant, /revoke, /award_guess) only show up for admins. See issue #16.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from ley_shards_bot.commands import help as help_commands


def _make_update(*, user_id: int = 1) -> MagicMock:
    update = MagicMock()
    update.effective_user.id = user_id
    message = MagicMock()
    message.reply_text = AsyncMock()
    update.effective_message = message
    return update


def _make_context(*, admin_ids: frozenset[int] = frozenset()) -> MagicMock:
    context = MagicMock()
    context.bot_data = {"config": SimpleNamespace(admin_user_ids=admin_ids)}
    return context


class TestHelpCommand:
    async def test_lists_player_commands_for_everyone(self):
        update = _make_update(user_id=1)
        context = _make_context(admin_ids=frozenset())

        await help_commands.help_command(update, context)

        (text,), _ = update.effective_message.reply_text.call_args
        assert "/daily" in text
        assert "/pull" in text
        assert "/collection" in text

    async def test_hides_admin_commands_from_non_admins(self):
        update = _make_update(user_id=1)
        context = _make_context(admin_ids=frozenset())

        await help_commands.help_command(update, context)

        (text,), _ = update.effective_message.reply_text.call_args
        assert "/grant" not in text
        assert "/revoke" not in text
        assert "/award_guess" not in text

    async def test_shows_admin_commands_to_admins(self):
        update = _make_update(user_id=1)
        context = _make_context(admin_ids=frozenset({1}))

        await help_commands.help_command(update, context)

        (text,), _ = update.effective_message.reply_text.call_args
        assert "/grant" in text
        assert "/revoke" in text
        assert "/award_guess" in text

    async def test_non_admin_with_different_id_still_hidden(self):
        update = _make_update(user_id=2)
        context = _make_context(admin_ids=frozenset({1}))

        await help_commands.help_command(update, context)

        (text,), _ = update.effective_message.reply_text.call_args
        assert "/grant" not in text
