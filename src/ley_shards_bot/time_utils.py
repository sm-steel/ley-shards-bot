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

from datetime import UTC, datetime


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
