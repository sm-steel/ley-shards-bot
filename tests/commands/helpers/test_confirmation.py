"""Tests for the generic confirm/cancel callback plumbing: callback_data
encoding/parsing, keyboard construction, and resolve_confirmation's
owner-check/malformed-data/expired-message handling. Nothing here is
gacha-specific — see tests/commands/test_gacha.py's
TestPullConfirmationCallback for a real caller exercising this end to
end.
"""

from unittest.mock import AsyncMock, MagicMock

from telegram import Message

from ley_shards_bot.commands.helpers.confirmation import (
    ConfirmAction,
    build_keyboard,
    callback_data,
    resolve_confirmation,
)

_PREFIX = "test"


def _make_update(
    *,
    clicking_user_id: int | None = 1,
    data: str | None = "test:1:widget:confirm",
    message_is_accessible: bool = True,
) -> MagicMock:
    update = MagicMock()
    update.effective_user.id = clicking_user_id
    if clicking_user_id is None:
        update.effective_user = None
    query = MagicMock()
    query.data = data
    query.answer = AsyncMock()
    if message_is_accessible:
        query.message = MagicMock(spec=Message)
    else:
        query.message = MagicMock()  # no spec=Message -> isinstance check fails
    update.callback_query = query
    return update


class TestCallbackData:
    def test_encodes_prefix_owner_subject_action(self):
        confirm = callback_data(_PREFIX, 42, "widget", ConfirmAction.CONFIRM)
        cancel = callback_data(_PREFIX, 42, "widget", ConfirmAction.CANCEL)

        assert confirm == "test:42:widget:confirm"
        assert cancel == "test:42:widget:cancel"


class TestBuildKeyboard:
    def test_builds_a_confirm_and_a_cancel_button(self):
        markup = build_keyboard(_PREFIX, 42, "widget")

        (row,) = markup.inline_keyboard
        confirm, cancel = row
        assert confirm.text == "Confirm"
        assert confirm.callback_data == "test:42:widget:confirm"
        assert cancel.text == "Cancel"
        assert cancel.callback_data == "test:42:widget:cancel"


class TestResolveConfirmation:
    async def test_returns_none_if_query_is_missing(self):
        update = MagicMock()
        update.callback_query = None

        result = await resolve_confirmation(update, prefix=_PREFIX)

        assert result is None

    async def test_returns_none_if_clicking_user_is_missing(self):
        update = _make_update(clicking_user_id=None)

        result = await resolve_confirmation(update, prefix=_PREFIX)

        assert result is None

    async def test_returns_none_if_query_data_is_missing(self):
        update = _make_update(data=None)

        result = await resolve_confirmation(update, prefix=_PREFIX)

        assert result is None

    async def test_answers_with_expired_alert_when_message_is_inaccessible(self):
        update = _make_update(message_is_accessible=False)

        result = await resolve_confirmation(update, prefix=_PREFIX)

        assert result is None
        update.callback_query.answer.assert_awaited_once()
        _args, kwargs = update.callback_query.answer.call_args
        assert kwargs.get("show_alert") is True
        (text,), _ = update.callback_query.answer.call_args
        assert "expired" in text.lower()

    async def test_ignores_malformed_callback_data(self):
        update = _make_update(data="not-a-real-payload")

        result = await resolve_confirmation(update, prefix=_PREFIX)

        assert result is None
        update.callback_query.answer.assert_awaited_once_with()

    async def test_ignores_data_for_a_different_prefix(self):
        update = _make_update(data="other:1:widget:confirm")

        result = await resolve_confirmation(update, prefix=_PREFIX)

        assert result is None

    async def test_rejects_a_non_owner_click(self):
        update = _make_update(clicking_user_id=2, data="test:1:widget:confirm")

        result = await resolve_confirmation(update, prefix=_PREFIX)

        assert result is None
        _args, kwargs = update.callback_query.answer.call_args
        assert kwargs.get("show_alert") is True

    async def test_owner_click_resolves_to_owner_id_message_subject_action(self):
        update = _make_update(clicking_user_id=1, data="test:1:widget:confirm")

        result = await resolve_confirmation(update, prefix=_PREFIX)

        assert result is not None
        owner_id, message, subject, action = result
        assert owner_id == 1
        assert message is update.callback_query.message
        assert subject == "widget"
        assert action == ConfirmAction.CONFIRM
        update.callback_query.answer.assert_awaited_once_with()

    async def test_cancel_action_resolves_correctly(self):
        update = _make_update(clicking_user_id=1, data="test:1:widget:cancel")

        result = await resolve_confirmation(update, prefix=_PREFIX)

        assert result is not None
        _owner_id, _message, _subject, action = result
        assert action == ConfirmAction.CANCEL
