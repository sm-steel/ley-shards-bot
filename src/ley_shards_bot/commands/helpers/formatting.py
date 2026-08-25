"""Shared Telegram-facing formatting constants, used by more than one
command module — kept here instead of re-literaled in each one (was
duplicated verbatim between gacha.py and collection.py, see issue #58).
"""

from __future__ import annotations

from ley_shards_bot.models import Rarity

RARITY_STARS = {
    Rarity.THREE_STAR: "★★★",
    Rarity.FOUR_STAR: "★★★★",
    Rarity.FIVE_STAR: "★★★★★",
}
