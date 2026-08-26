"""Ley Shards economy: /daily, first-message-of-day trickle, /award_guess,
/grant. See ARCHITECTURE.md's Economy section for the rules this encodes.

Framework-agnostic — no python-telegram-bot imports (see CLAUDE.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING

from loguru import logger

from ley_shards_bot.services.players import PlayerRef, get_or_create_player
from ley_shards_bot.time_utils import game_day, next_game_day_start, to_utc_naive

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

DAILY_AMOUNT = 60

TRICKLE_AMOUNT = 20

AWARD_GUESS_AMOUNT = 15
AWARD_GUESS_DAILY_LIMIT = 3


@dataclass(frozen=True)
class DailyClaimResult:
    granted: bool
    amount: int
    new_balance: int
    next_claim_at: datetime


def claim_daily(session: Session, player: PlayerRef, *, now: datetime) -> DailyClaimResult:
    now = to_utc_naive(now)
    account = get_or_create_player(session, player)

    if account.last_daily_claimed_at is not None and game_day(
        account.last_daily_claimed_at
    ) == game_day(now):
        next_claim_at = next_game_day_start(now)
        logger.debug(
            "/daily rejected for {}: next claim at {}", player.telegram_user_id, next_claim_at
        )
        return DailyClaimResult(
            granted=False,
            amount=0,
            new_balance=account.ley_shards,
            next_claim_at=next_claim_at,
        )

    account.ley_shards += DAILY_AMOUNT
    account.last_daily_claimed_at = now
    session.commit()
    logger.info(
        "/daily granted {} Ley Shards to {} (balance={})",
        DAILY_AMOUNT,
        player.telegram_user_id,
        account.ley_shards,
    )
    return DailyClaimResult(
        granted=True,
        amount=DAILY_AMOUNT,
        new_balance=account.ley_shards,
        next_claim_at=next_game_day_start(now),
    )


def apply_trickle(session: Session, player: PlayerRef, *, today: date) -> bool:
    """Grant the once-per-day activity trickle. Returns whether it was
    actually granted (False if this player already got it today)."""
    account = get_or_create_player(session, player)
    if account.last_trickle_date == today:
        logger.debug("Trickle already granted today for {}", player.telegram_user_id)
        return False

    account.ley_shards += TRICKLE_AMOUNT
    account.last_trickle_date = today
    session.commit()
    logger.debug("Trickle granted {} Ley Shards to {}", TRICKLE_AMOUNT, player.telegram_user_id)
    return True


@dataclass(frozen=True)
class AwardGuessResult:
    granted: bool
    amount: int
    new_balance: int
    awards_remaining_today: int


def award_guess(session: Session, target: PlayerRef, *, today: date) -> AwardGuessResult:
    """Admin/mod-granted bonus for a correct guess in the (manual, not
    bot-run) "guess the anime" topic. Rate-limited per target per day."""
    account = get_or_create_player(session, target)

    if account.guess_awards_date != today:
        account.guess_awards_date = today
        account.guess_awards_today = 0

    if account.guess_awards_today >= AWARD_GUESS_DAILY_LIMIT:
        session.commit()
        logger.warning("/award_guess denied for {}: daily limit reached", target.telegram_user_id)
        return AwardGuessResult(
            granted=False, amount=0, new_balance=account.ley_shards, awards_remaining_today=0
        )

    account.guess_awards_today += 1
    account.ley_shards += AWARD_GUESS_AMOUNT
    session.commit()
    logger.info(
        "/award_guess granted {} Ley Shards to {} ({} remaining today)",
        AWARD_GUESS_AMOUNT,
        target.telegram_user_id,
        AWARD_GUESS_DAILY_LIMIT - account.guess_awards_today,
    )
    return AwardGuessResult(
        granted=True,
        amount=AWARD_GUESS_AMOUNT,
        new_balance=account.ley_shards,
        awards_remaining_today=AWARD_GUESS_DAILY_LIMIT - account.guess_awards_today,
    )


def grant(session: Session, target: PlayerRef, amount: int) -> int:
    """Admin-only arbitrary grant, e.g. for one-off events. Returns the new
    balance."""
    if amount <= 0:
        msg = "Grant amount must be positive"
        raise ValueError(msg)

    account = get_or_create_player(session, target)
    account.ley_shards += amount
    session.commit()
    logger.info(
        "/grant gave {} Ley Shards to {} (balance={})",
        amount,
        target.telegram_user_id,
        account.ley_shards,
    )
    return account.ley_shards


def revoke(session: Session, target: PlayerRef, amount: int) -> int:
    """Admin-only balance correction, e.g. undoing a mistaken /grant. Clamps
    at 0 rather than allowing a negative balance. Returns the new balance."""
    if amount <= 0:
        msg = "Revoke amount must be positive"
        raise ValueError(msg)

    account = get_or_create_player(session, target)
    account.ley_shards = max(0, account.ley_shards - amount)
    session.commit()
    logger.info(
        "/revoke took {} Ley Shards from {} (balance={})",
        amount,
        target.telegram_user_id,
        account.ley_shards,
    )
    return account.ley_shards
