"""Database engine/session setup — the one place that builds them.

Sync SQLAlchemy, called directly from async command handlers. Deliberately
simple: this bot serves a handful of players in one group chat, nowhere
near enough load for a blocking DB call to matter. Revisit only if that
stops being true (YAGNI — see CLAUDE.md).

Lazily initialized so importing this module (e.g. transitively, via
commands/) doesn't require DATABASE_URL to be set — only actually opening
a session does.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ley_shards_bot.config import database_url

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _get_session_factory() -> sessionmaker[Session]:
    global _engine, _session_factory
    if _session_factory is None:
        _engine = create_engine(database_url())
        _session_factory = sessionmaker(bind=_engine)
    return _session_factory


@contextmanager
def session_scope() -> Iterator[Session]:
    """`with session_scope() as session:` — commits on success, rolls back
    and re-raises on any exception, always closes."""
    session = _get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
