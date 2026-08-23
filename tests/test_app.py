"""Tests for Application wiring: bot_data and handler registration.

Doesn't call run_polling or touch the network — ApplicationBuilder.build()
constructs the Application object without making any API calls itself.
"""

from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler

from ley_shards_bot.app import build_application
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
