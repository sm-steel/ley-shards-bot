"""A gacha banner — the permanent standard banner, or a rotating event one."""

from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ley_shards_bot.models.base import Base
from ley_shards_bot.models.enums import BannerType


class Banner(Base):
    __tablename__ = "banners"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[BannerType] = mapped_column(Enum(BannerType))
    name: Mapped[str] = mapped_column(String(255))

    # Event banners only. Standard banner is permanent (both null) and has
    # no rate-up character.
    starts_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    rate_up_character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.anilist_id"), default=None
    )
