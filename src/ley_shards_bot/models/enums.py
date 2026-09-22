"""Enums shared across models and services.

Plain Python enums, stored via SQLAlchemy's generic Enum type — portable
between the SQLite used in tests and the MariaDB used in production.
"""

from enum import IntEnum, StrEnum


class Rarity(IntEnum):
    """Character pull rarity. Values double as star counts (3/4/5)."""

    THREE_STAR = 3
    FOUR_STAR = 4
    FIVE_STAR = 5


class BannerType(StrEnum):
    STANDARD = "standard"
    EVENT = "event"


class CurrencyType(StrEnum):
    """Keys into player_currencies — a generic per-player balance ledger
    (see services/currency.py). Ley Shards and Echoes are NOT here; they
    stay as columns on Player for now (# TODO: migrating them onto this
    same ledger is a reasonable future cleanup, not part of issue #20).
    """

    STANDARD_TICKET = "standard_ticket"
    EVENT_TICKET = "event_ticket"
