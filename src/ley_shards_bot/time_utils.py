"""UTC time helpers — the one place datetimes cross the naive/aware boundary.

Every datetime stored in the DB is naive, and by convention always UTC.
This isn't a shortcut: MariaDB's DATETIME (what production runs on) has no
timezone-aware storage at all, and SQLite doesn't reliably round-trip
tzinfo through a commit-then-refetch either. Declaring columns
`DateTime(timezone=True)` would just be a promise the DB can't keep. So
instead: convert to naive UTC right when a value enters the system
(`utc_now`, `to_utc_naive`), and treat every stored/retrieved datetime as
implicitly UTC from then on.
"""

from datetime import UTC, date, datetime, timedelta

# Every "once per day" limit (/daily, trickle, /award_guess — see
# MECHANICS.md's "Daily reset") resets at this fixed wall-clock hour, not
# at UTC midnight and not on a rolling 24h-since-last-claim basis. See
# issue #42.
GAME_DAY_RESET_HOUR_UTC = 2


def utc_now() -> datetime:
    """The current time, naive, in UTC — use this instead of
    datetime.now(UTC) anywhere a value will be stored or compared against
    a stored value."""
    return datetime.now(UTC).replace(tzinfo=None)


def to_utc_naive(moment: datetime) -> datetime:
    """Normalize a datetime (aware or already-naive-UTC) to naive UTC, so
    callers can pass either without the storage layer caring."""
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(UTC).replace(tzinfo=None)


def game_day(moment: datetime) -> date:
    """The "game day" `moment` falls in — the shared boundary for every
    daily reset (see GAME_DAY_RESET_HOUR_UTC above). Two moments are "the
    same day" for reset purposes iff `game_day` returns the same date for
    both, however close together or far apart the wall-clock gap between
    them actually is."""
    return (to_utc_naive(moment) - timedelta(hours=GAME_DAY_RESET_HOUR_UTC)).date()


def next_game_day_start(moment: datetime) -> datetime:
    """The next 02:00 UTC boundary strictly after `moment` — used to
    report "claim again at" for fixed-boundary daily resets."""
    moment = to_utc_naive(moment)
    todays_boundary = moment.replace(
        hour=GAME_DAY_RESET_HOUR_UTC, minute=0, second=0, microsecond=0
    )
    return todays_boundary if moment < todays_boundary else todays_boundary + timedelta(days=1)
