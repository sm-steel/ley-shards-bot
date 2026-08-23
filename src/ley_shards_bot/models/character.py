"""A pullable character, sourced from AniList by the roster ingestion command.

Primary key is the AniList character id itself, not a synthetic id — that
makes re-running ingestion a natural upsert instead of needing separate
dedup logic.
"""

from datetime import datetime

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from ley_shards_bot.models.base import Base
from ley_shards_bot.models.enums import Rarity
from ley_shards_bot.time_utils import utc_now


class Character(Base):
    __tablename__ = "characters"

    anilist_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    series: Mapped[str] = mapped_column(String(255))
    image_url: Mapped[str] = mapped_column(String(2048))
    rarity: Mapped[Rarity] = mapped_column(Enum(Rarity))

    # Placeholder base combat stats — not used by anything in Phase 1, but
    # stored now so a future combat system has roster data to build on
    # without re-deriving it. See ARCHITECTURE.md's Roadmap section.
    base_hp: Mapped[int]
    base_atk: Mapped[int]
    base_def: Mapped[int]
    base_spd: Mapped[int]

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
