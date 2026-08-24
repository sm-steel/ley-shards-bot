"""Tests for the shared DM-scoping check used by player commands
(/daily, /pull, /pull10, /collection — see issue #17).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from ley_shards_bot.commands.scoping import in_private_chat


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
