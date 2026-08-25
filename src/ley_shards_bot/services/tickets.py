"""Banner ticket purchase: converting Ley Shards into pre-bought pull
currency. See GACHA.md's "Banner tickets" section for the rule this
encodes (same price as a direct pull, ticket spend is instant/no
confirmation once bought).

Framework-agnostic — no python-telegram-bot imports (see CLAUDE.md).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from ley_shards_bot.models import BannerType, CurrencyType
from ley_shards_bot.services import currency
from ley_shards_bot.services.gacha import PULL_COST_LEY_SHARDS, InsufficientLeyShardsError
from ley_shards_bot.services.players import get_or_create_player

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_TICKET_TYPE_BY_BANNER: dict[BannerType, CurrencyType] = {
    BannerType.STANDARD: CurrencyType.STANDARD_TICKET,
    BannerType.EVENT: CurrencyType.EVENT_TICKET,
}


def buy_tickets(
    session: Session,
    telegram_user_id: int,
    ticket_type: BannerType,
    count: int,
    *,
    username: str | None = None,
) -> int:
    """/buy_ticket: pre-buy `count` tickets of `ticket_type` at
    PULL_COST_LEY_SHARDS each. Returns the new balance of that ticket
    type."""
    if count <= 0:
        msg = "Ticket count must be positive"
        raise ValueError(msg)

    cost = PULL_COST_LEY_SHARDS * count
    player = get_or_create_player(session, telegram_user_id, username=username)
    if player.ley_shards < cost:
        raise InsufficientLeyShardsError(cost, player.ley_shards)

    player.ley_shards -= cost
    ticket_currency = _TICKET_TYPE_BY_BANNER[ticket_type]
    new_balance = currency.add(session, telegram_user_id, ticket_currency, count)
    session.commit()
    logger.info(
        "Bought {} {} ticket(s) for {} (balance={})",
        count,
        ticket_type,
        telegram_user_id,
        new_balance,
    )
    return new_balance
