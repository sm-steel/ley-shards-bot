"""A player — one row per Telegram user who has interacted with the bot."""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from ley_shards_bot.models.base import Base
from ley_shards_bot.time_utils import utc_now


class Player(Base):
    __tablename__ = "players"

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # Telegram @username, without the @. Nullable — not everyone has one, and
    # even players who do aren't guaranteed to have been seen by the bot yet.
    # Opportunistically captured/refreshed by get_or_create_player() below —
    # not authoritative if a player hasn't used the bot since changing it.
    username: Mapped[str | None] = mapped_column(String(32), default=None)
    ley_shards: Mapped[int] = mapped_column(default=0)
    echoes: Mapped[int] = mapped_column(default=0)
    last_daily_claimed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    last_trickle_date: Mapped[date | None] = mapped_column(Date, default=None)

    # /award_guess rate limiting — how many awards this player has received
    # today, and which day that count is for (reset when the date changes).
    guess_awards_today: Mapped[int] = mapped_column(default=0)
    guess_awards_date: Mapped[date | None] = mapped_column(Date, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
