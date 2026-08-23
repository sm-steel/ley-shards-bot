"""History log of individual pulls — for auditing pity/RNG correctness.

Not shown to players directly (that's what player_characters/pity_state
are for); this table exists so pity math can be debugged after the fact.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from ley_shards_bot.models.base import Base


class Pull(Base):
    __tablename__ = "pulls"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.telegram_user_id"))
    banner_id: Mapped[int] = mapped_column(ForeignKey("banners.id"))
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.anilist_id"))
    pulled_at: Mapped[datetime] = mapped_column(DateTime)
