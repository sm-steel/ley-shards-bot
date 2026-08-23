"""A player — one row per Telegram user who has interacted with the bot."""

from datetime import UTC, date, datetime

from sqlalchemy import BigInteger, Date, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from ley_shards_bot.models.base import Base


class Player(Base):
    __tablename__ = "players"

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ley_shards: Mapped[int] = mapped_column(default=0)
    echoes: Mapped[int] = mapped_column(default=0)
    last_daily_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    last_trickle_date: Mapped[date | None] = mapped_column(Date, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
