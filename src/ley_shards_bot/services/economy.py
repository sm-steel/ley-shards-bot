"""Ley Shards economy: /daily, first-message-of-day trickle, /award_guess,
/grant. See ARCHITECTURE.md's Economy section for the rules this encodes.

Framework-agnostic — no python-telegram-bot imports (see CLAUDE.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from loguru import logger

from ley_shards_bot.services.players import get_or_create_player
from ley_shards_bot.time_utils import to_utc_naive

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

DAILY_AMOUNT = 60
DAILY_COOLDOWN = timedelta(hours=24)

TRICKLE_AMOUNT = 20

AWARD_GUESS_AMOUNT = 15
AWARD_GUESS_DAILY_LIMIT = 3


@dataclass(frozen=True)
class DailyClaimResult:
    granted: bool
    amount: int
    new_balance: int
    next_claim_at: datetime


def claim_daily(session: Session, telegram_user_id: int, *, now: datetime) -> DailyClaimResult:
    now = to_utc_naive(now)
    player = get_or_create_player(session, telegram_user_id)

    if player.last_daily_claimed_at is not None:
        next_claim_at = player.last_daily_claimed_at + DAILY_COOLDOWN
        if now < next_claim_at:
            logger.debug(
                "/daily rejected for {}: next claim at {}", telegram_user_id, next_claim_at
            )
            return DailyClaimResult(
                granted=False,
                amount=0,
                new_balance=player.ley_shards,
                next_claim_at=next_claim_at,
            )

    player.ley_shards += DAILY_AMOUNT
    player.last_daily_claimed_at = now
    session.commit()
    logger.info(
        "/daily granted {} Ley Shards to {} (balance={})",
        DAILY_AMOUNT,
        telegram_user_id,
        player.ley_shards,
    )
    return DailyClaimResult(
        granted=True,
        amount=DAILY_AMOUNT,
        new_balance=player.ley_shards,
        next_claim_at=now + DAILY_COOLDOWN,
    )


def apply_trickle(session: Session, telegram_user_id: int, *, today: date) -> bool:
    """Grant the once-per-day activity trickle. Returns whether it was
    actually granted (False if this player already got it today)."""
    player = get_or_create_player(session, telegram_user_id)
    if player.last_trickle_date == today:
        logger.debug("Trickle already granted today for {}", telegram_user_id)
        return False

    player.ley_shards += TRICKLE_AMOUNT
    player.last_trickle_date = today
    session.commit()
    logger.debug("Trickle granted {} Ley Shards to {}", TRICKLE_AMOUNT, telegram_user_id)
    return True


@dataclass(frozen=True)
class AwardGuessResult:
    granted: bool
    amount: int
    new_balance: int
    awards_remaining_today: int


def award_guess(session: Session, target_telegram_user_id: int, *, today: date) -> AwardGuessResult:
    """Admin/mod-granted bonus for a correct guess in the (manual, not
    bot-run) "guess the anime" topic. Rate-limited per target per day."""
    player = get_or_create_player(session, target_telegram_user_id)

    if player.guess_awards_date != today:
        player.guess_awards_date = today
        player.guess_awards_today = 0

    if player.guess_awards_today >= AWARD_GUESS_DAILY_LIMIT:
        session.commit()
        logger.warning("/award_guess denied for {}: daily limit reached", target_telegram_user_id)
        return AwardGuessResult(
            granted=False, amount=0, new_balance=player.ley_shards, awards_remaining_today=0
        )

    player.guess_awards_today += 1
    player.ley_shards += AWARD_GUESS_AMOUNT
    session.commit()
    logger.info(
        "/award_guess granted {} Ley Shards to {} ({} remaining today)",
        AWARD_GUESS_AMOUNT,
        target_telegram_user_id,
        AWARD_GUESS_DAILY_LIMIT - player.guess_awards_today,
    )
    return AwardGuessResult(
        granted=True,
        amount=AWARD_GUESS_AMOUNT,
        new_balance=player.ley_shards,
        awards_remaining_today=AWARD_GUESS_DAILY_LIMIT - player.guess_awards_today,
    )


def grant(session: Session, target_telegram_user_id: int, amount: int) -> int:
    """Admin-only arbitrary grant, e.g. for one-off events. Returns the new
    balance."""
    if amount <= 0:
        msg = "Grant amount must be positive"
        raise ValueError(msg)

    player = get_or_create_player(session, target_telegram_user_id)
    player.ley_shards += amount
    session.commit()
    logger.info(
        "/grant gave {} Ley Shards to {} (balance={})",
        amount,
        target_telegram_user_id,
        player.ley_shards,
    )
    return player.ley_shards
