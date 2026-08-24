"""Tests for the Ley Shards economy service: /daily, trickle, /award_guess,
/grant balance logic. All pure DB logic, no Telegram involved.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ley_shards_bot.models import Base, Player
from ley_shards_bot.services.economy import (
    AWARD_GUESS_AMOUNT,
    AWARD_GUESS_DAILY_LIMIT,
    DAILY_AMOUNT,
    TRICKLE_AMOUNT,
    apply_trickle,
    award_guess,
    claim_daily,
    grant,
    revoke,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


class TestClaimDaily:
    """Daily reset is a fixed 02:00 UTC boundary (the "game day" — see
    MECHANICS.md's "Daily reset", issue #42), not a rolling 24h cooldown
    and not UTC midnight."""

    def test_first_claim_grants_the_full_amount(self, session):
        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

        result = claim_daily(session, 1, now=now)

        assert result.granted is True
        assert result.amount == DAILY_AMOUNT
        assert result.new_balance == DAILY_AMOUNT

    def test_second_claim_same_game_day_is_rejected(self, session):
        first = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        claim_daily(session, 1, now=first)

        second = first + timedelta(hours=1)
        result = claim_daily(session, 1, now=second)

        assert result.granted is False
        assert result.amount == 0
        assert result.new_balance == DAILY_AMOUNT  # unchanged

    def test_claim_shortly_after_the_boundary_succeeds_even_less_than_24h_later(self, session):
        # 2h45m apart — nowhere near a rolling 24h cooldown — but the
        # 02:00 UTC boundary between them makes it a new game day.
        first = datetime(2026, 1, 1, 23, 30, tzinfo=UTC)
        claim_daily(session, 1, now=first)

        second = datetime(2026, 1, 2, 2, 15, tzinfo=UTC)
        result = claim_daily(session, 1, now=second)

        assert result.granted is True
        assert result.new_balance == DAILY_AMOUNT * 2

    def test_claim_just_before_the_boundary_next_day_is_still_rejected(self, session):
        # Almost 24h apart, but both moments fall before the *next*
        # 02:00 UTC boundary — still the same game day.
        first = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        claim_daily(session, 1, now=first)

        second = datetime(2026, 1, 2, 1, 59, tzinfo=UTC)
        result = claim_daily(session, 1, now=second)

        assert result.granted is False
        assert result.new_balance == DAILY_AMOUNT  # unchanged

    def test_rejected_claim_reports_next_claim_time(self, session):
        first = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        claim_daily(session, 1, now=first)

        result = claim_daily(session, 1, now=first + timedelta(hours=1))

        # The next 02:00 UTC boundary after the rejected attempt — stored/
        # returned as naive UTC by convention, see time_utils.py.
        assert result.next_claim_at == datetime(2026, 1, 2, 2, 0)  # noqa: DTZ001

    def test_captures_username(self, session):
        claim_daily(session, 1, now=datetime(2026, 1, 1, 12, 0, tzinfo=UTC), username="aleksey")

        assert session.get(Player, 1).username == "aleksey"


class TestApplyTrickle:
    def test_first_message_of_the_day_grants_trickle(self, session):
        applied = apply_trickle(session, 1, today=date(2026, 1, 1))

        assert applied is True
        assert session.get(Player, 1).ley_shards == TRICKLE_AMOUNT

    def test_second_message_same_day_grants_nothing(self, session):
        apply_trickle(session, 1, today=date(2026, 1, 1))

        applied_again = apply_trickle(session, 1, today=date(2026, 1, 1))

        assert applied_again is False
        assert session.get(Player, 1).ley_shards == TRICKLE_AMOUNT

    def test_next_day_grants_again(self, session):
        apply_trickle(session, 1, today=date(2026, 1, 1))

        applied = apply_trickle(session, 1, today=date(2026, 1, 2))

        assert applied is True
        assert session.get(Player, 1).ley_shards == TRICKLE_AMOUNT * 2

    def test_captures_username(self, session):
        apply_trickle(session, 1, today=date(2026, 1, 1), username="aleksey")

        assert session.get(Player, 1).username == "aleksey"


class TestAwardGuess:
    def test_grants_bonus_to_target(self, session):
        result = award_guess(session, 5, today=date(2026, 1, 1))

        assert result.granted is True
        assert result.amount == AWARD_GUESS_AMOUNT
        assert result.new_balance == AWARD_GUESS_AMOUNT

    def test_stops_after_daily_limit(self, session):
        today = date(2026, 1, 1)
        for _ in range(AWARD_GUESS_DAILY_LIMIT):
            award_guess(session, 5, today=today)

        result = award_guess(session, 5, today=today)

        assert result.granted is False
        assert result.awards_remaining_today == 0
        assert session.get(Player, 5).ley_shards == AWARD_GUESS_AMOUNT * AWARD_GUESS_DAILY_LIMIT

    def test_limit_resets_the_next_day(self, session):
        today = date(2026, 1, 1)
        for _ in range(AWARD_GUESS_DAILY_LIMIT):
            award_guess(session, 5, today=today)

        result = award_guess(session, 5, today=date(2026, 1, 2))

        assert result.granted is True

    def test_captures_target_username(self, session):
        award_guess(session, 5, today=date(2026, 1, 1), username="aleksey")

        assert session.get(Player, 5).username == "aleksey"


class TestGrant:
    def test_adds_arbitrary_amount_to_target_balance(self, session):
        new_balance = grant(session, 9, 250)

        assert new_balance == 250
        assert session.get(Player, 9).ley_shards == 250

    def test_stacks_across_calls(self, session):
        grant(session, 9, 100)
        new_balance = grant(session, 9, 50)

        assert new_balance == 150

    def test_rejects_non_positive_amount(self, session):
        with pytest.raises(ValueError, match="positive"):
            grant(session, 9, 0)

    def test_captures_target_username(self, session):
        grant(session, 9, 100, username="aleksey")

        assert session.get(Player, 9).username == "aleksey"


class TestRevoke:
    def test_deducts_arbitrary_amount_from_target_balance(self, session):
        grant(session, 9, 250)

        new_balance = revoke(session, 9, 100)

        assert new_balance == 150
        assert session.get(Player, 9).ley_shards == 150

    def test_clamps_at_zero_rather_than_going_negative(self, session):
        grant(session, 9, 50)

        new_balance = revoke(session, 9, 100)

        assert new_balance == 0
        assert session.get(Player, 9).ley_shards == 0

    def test_rejects_non_positive_amount(self, session):
        with pytest.raises(ValueError, match="positive"):
            revoke(session, 9, 0)

    def test_captures_target_username(self, session):
        revoke(session, 9, 100, username="aleksey")

        assert session.get(Player, 9).username == "aleksey"
