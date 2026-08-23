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
