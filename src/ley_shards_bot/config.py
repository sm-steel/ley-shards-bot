"""Loads bot configuration from environment / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _parse_admin_ids(raw: str) -> frozenset[int]:
    return frozenset(int(part) for part in raw.split(",") if part.strip())


def database_url() -> str:
    """Just the DB URL, independent of the rest of Config.

    Used by Alembic (migrations/env.py), which needs to connect to the
    database without requiring the bot's other settings (BOT_TOKEN etc.)
    to be present.
    """
    return _require("DATABASE_URL")


@dataclass(frozen=True)
class Config:
    bot_token: str
    gacha_topic_id: int
    group_chat_id: int
    admin_user_ids: frozenset[int]
    telegram_proxy_url: str | None
    database_url: str
    log_level: str

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            bot_token=_require("BOT_TOKEN"),
            gacha_topic_id=int(_require("GACHA_TOPIC_ID")),
            group_chat_id=int(_require("GROUP_CHAT_ID")),
            admin_user_ids=_parse_admin_ids(os.environ.get("ADMIN_USER_IDS", "")),
            telegram_proxy_url=os.environ.get("TELEGRAM_PROXY_URL") or None,
            database_url=database_url(),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )
