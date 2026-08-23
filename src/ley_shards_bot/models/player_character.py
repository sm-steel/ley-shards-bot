"""Ownership: which characters a player has, and how many copies."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from ley_shards_bot.models.base import Base
from ley_shards_bot.time_utils import utc_now


class PlayerCharacter(Base):
    __tablename__ = "player_characters"

    player_id: Mapped[int] = mapped_column(ForeignKey("players.telegram_user_id"), primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.anilist_id"), primary_key=True)
    copies_owned: Mapped[int] = mapped_column(default=1)
    first_obtained_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
