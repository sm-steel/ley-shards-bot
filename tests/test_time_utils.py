"""Tests for the game-day boundary (issue #42): every "once per day" limit
(/daily, trickle, /award_guess) resets at a single fixed wall-clock time,
02:00 UTC, rather than rolling-24h or midnight-UTC. See MECHANICS.md's
"Daily reset" section for the full rule.
"""

from datetime import UTC, datetime

from ley_shards_bot.time_utils import game_day, next_game_day_start


class TestGameDay:
    def test_moment_just_before_the_boundary_is_the_previous_game_day(self):
        moment = datetime(2026, 8, 24, 1, 59, tzinfo=UTC)

        assert game_day(moment).isoformat() == "2026-08-23"

    def test_moment_exactly_at_the_boundary_starts_the_new_game_day(self):
        moment = datetime(2026, 8, 24, 2, 0, tzinfo=UTC)

        assert game_day(moment).isoformat() == "2026-08-24"

    def test_moment_well_after_the_boundary_is_the_same_game_day(self):
        moment = datetime(2026, 8, 24, 23, 59, tzinfo=UTC)

        assert game_day(moment).isoformat() == "2026-08-24"

    def test_accepts_naive_utc_too(self):
        moment = datetime(2026, 8, 24, 1, 0)  # noqa: DTZ001 — naive-UTC by convention

        assert game_day(moment).isoformat() == "2026-08-23"


class TestNextGameDayStart:
    def test_before_todays_boundary_returns_todays_boundary(self):
        moment = datetime(2026, 8, 24, 1, 0, tzinfo=UTC)

        result = next_game_day_start(moment)

        assert result.isoformat() == "2026-08-24T02:00:00"

    def test_after_todays_boundary_returns_tomorrows_boundary(self):
        moment = datetime(2026, 8, 24, 13, 0, tzinfo=UTC)

        result = next_game_day_start(moment)

        assert result.isoformat() == "2026-08-25T02:00:00"

    def test_exactly_at_the_boundary_returns_tomorrows_boundary(self):
        # The boundary moment itself already belongs to the new game day
        # (see TestGameDay above) — so the *next* reset is tomorrow's.
        moment = datetime(2026, 8, 24, 2, 0, tzinfo=UTC)

        result = next_game_day_start(moment)

        assert result.isoformat() == "2026-08-25T02:00:00"
