"""A generic per-player currency ledger — one row per (player,
currency_type). Deliberately separate from Ley Shards/Echoes (still
plain columns on Player): this exists so a new currency (e.g. Phase
1.2's weapon ticket) is a new CurrencyType member, not a new column and
a new migration everywhere balances are read. See services/currency.py
for the read/write primitives and services/tickets.py for the
ticket-specific rules built on top of them.
"""

from sqlalchemy import Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from ley_shards_bot.models.base import Base
from ley_shards_bot.models.enums import CurrencyType


class PlayerCurrency(Base):
    __tablename__ = "player_currencies"

    player_id: Mapped[int] = mapped_column(ForeignKey("players.telegram_user_id"), primary_key=True)
    currency_type: Mapped[CurrencyType] = mapped_column(Enum(CurrencyType), primary_key=True)
    amount: Mapped[int] = mapped_column(default=0, server_default="0")
