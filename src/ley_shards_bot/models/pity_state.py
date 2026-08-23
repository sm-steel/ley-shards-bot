"""Per-player, per-banner-type pity counters.

Tracked by banner *type* (standard vs. event), not by individual banner —
event pity persists across event banner rotations, matching the classic
gacha convention. See ARCHITECTURE.md's Gacha pulls section.
"""

from sqlalchemy import Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from ley_shards_bot.models.base import Base
from ley_shards_bot.models.enums import BannerType


class PityState(Base):
    __tablename__ = "pity_state"

    player_id: Mapped[int] = mapped_column(ForeignKey("players.telegram_user_id"), primary_key=True)
    banner_type: Mapped[BannerType] = mapped_column(Enum(BannerType), primary_key=True)
    pulls_since_last_5star: Mapped[int] = mapped_column(default=0)
    pulls_since_last_4star: Mapped[int] = mapped_column(default=0)
    # Event banners only: set when a 50/50 was lost, guaranteeing the
    # rate-up character on the next 5-star pull on this banner type.
    guaranteed_rate_up: Mapped[bool] = mapped_column(default=False)
