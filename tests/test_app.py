"""Tests for Application wiring: bot_data and handler registration.

Doesn't call run_polling or touch the network — ApplicationBuilder.build()
constructs the Application object without making any API calls itself.
"""

from unittest.mock import AsyncMock, MagicMock

from telegram import BotCommandScopeChat, BotCommandScopeDefault
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler

from ley_shards_bot.app import _command_registrations, build_application, register_commands
from ley_shards_bot.config import Config


def _fake_config() -> Config:
    return Config(
        bot_token="123456:fake-token-for-testing",  # noqa: S106 (test fixture, not a real secret)
        gacha_topic_id=1,
        admin_user_ids=frozenset({1}),
        telegram_proxy_url=None,
        database_url="sqlite:///:memory:",
        log_level="DEBUG",
    )


def test_stores_config_in_bot_data():
    config = _fake_config()

    application = build_application(config)

    assert application.bot_data["config"] is config


def test_registers_every_command():
    application = build_application(_fake_config())

    command_handlers = [h for h in application.handlers[0] if isinstance(h, CommandHandler)]
    registered = {cmd for handler in command_handlers for cmd in handler.commands}

    assert {"daily", "award_guess", "grant", "pull", "pull10", "collection"} <= registered


def test_registers_the_collection_pagination_callback():
    application = build_application(_fake_config())

    assert any(isinstance(h, CallbackQueryHandler) for h in application.handlers[0])


def test_registers_the_trickle_handler_in_its_own_group():
    # A separate group so it fires alongside command handlers, not instead
    # of them — see app.py's comment on why.
    application = build_application(_fake_config())

    assert 1 in application.handlers
    assert any(isinstance(h, MessageHandler) for h in application.handlers[1])


def test_registers_a_post_init_hook_to_publish_commands():
    # setMyCommands is an API call — actually invoking it belongs to
    # post_init (see register_commands' own test coverage below), not
    # something build_application should do itself.
    application = build_application(_fake_config())

    assert application.post_init is not None


class TestCommandRegistrations:
    """_command_registrations() is pure — no network call, no Application —
    so the scope/command-list shape it builds is tested directly rather
    than through a real setMyCommands call."""

    def test_default_scope_lists_only_player_commands(self):
        registrations = _command_registrations(admin_user_ids=frozenset({1}))

        default = next(
            commands
            for scope, commands in registrations
            if isinstance(scope, BotCommandScopeDefault)
        )
        default_names = {c.command for c in default}
        assert {"daily", "pull", "pull10", "collection"} <= default_names
        assert "grant" not in default_names
        assert "revoke" not in default_names
        assert "award_guess" not in default_names

    def test_each_admin_gets_a_per_chat_scope_with_admin_commands(self):
        registrations = _command_registrations(admin_user_ids=frozenset({7, 8}))

        admin_scopes = {
            scope.chat_id: commands
            for scope, commands in registrations
            if isinstance(scope, BotCommandScopeChat)
        }
        assert set(admin_scopes) == {7, 8}
        for commands in admin_scopes.values():
            names = {c.command for c in commands}
            assert {"grant", "revoke", "award_guess"} <= names
            # Admins are players too — they should still see player commands.
            assert {"daily", "pull", "pull10", "collection"} <= names

    def test_no_admins_means_no_per_chat_scopes(self):
        registrations = _command_registrations(admin_user_ids=frozenset())

        assert not any(isinstance(scope, BotCommandScopeChat) for scope, _ in registrations)


async def test_register_commands_calls_set_my_commands_per_scope():
    application = MagicMock()
    application.bot.set_my_commands = AsyncMock()
    application.bot_data = {"config": _fake_config()}

    await register_commands(application)

    # Default scope + one admin's per-chat scope (admin_user_ids={1} in
    # _fake_config()), per _command_registrations.
    assert application.bot.set_my_commands.await_count == 2
