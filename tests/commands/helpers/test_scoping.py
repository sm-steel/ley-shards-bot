"""Tests for the shared DM-scoping check used by player commands
(/daily, /pull, /pull10, /collection — see issue #17).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from ley_shards_bot.commands.helpers.scoping import in_private_chat, is_admin


def _make_update(*, chat_type: str | None) -> MagicMock:
    update = MagicMock()
    update.effective_chat = None if chat_type is None else SimpleNamespace(type=chat_type)
    return update


class TestInPrivateChat:
    def test_true_for_a_private_chat(self):
        assert in_private_chat(_make_update(chat_type="private")) is True

    def test_false_for_a_group_chat(self):
        assert in_private_chat(_make_update(chat_type="group")) is False

    def test_false_for_a_supergroup(self):
        assert in_private_chat(_make_update(chat_type="supergroup")) is False

    def test_false_when_theres_no_chat_at_all(self):
        assert in_private_chat(_make_update(chat_type=None)) is False


def _make_admin_check_update(*, user_id: int = 1) -> MagicMock:
    update = MagicMock()
    update.effective_user.id = user_id
    return update


def _make_admin_check_context(*, admin_ids: frozenset[int]) -> MagicMock:
    context = MagicMock()
    context.bot_data = {"config": SimpleNamespace(admin_user_ids=admin_ids)}
    return context


class TestIsAdmin:
    def test_true_for_a_configured_admin(self):
        update = _make_admin_check_update(user_id=1)
        context = _make_admin_check_context(admin_ids=frozenset({1}))

        assert is_admin(update, context) is True

    def test_false_for_a_non_admin(self):
        update = _make_admin_check_update(user_id=2)
        context = _make_admin_check_context(admin_ids=frozenset({1}))

        assert is_admin(update, context) is False

    def test_false_when_theres_no_user(self):
        update = _make_admin_check_update(user_id=1)
        update.effective_user = None
        context = _make_admin_check_context(admin_ids=frozenset({1}))

        assert is_admin(update, context) is False
