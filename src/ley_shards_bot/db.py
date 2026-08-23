"""Database engine/session setup — the one place that builds them.

Sync SQLAlchemy, called directly from async command handlers. Deliberately
simple: this bot serves a handful of players in one group chat, nowhere
near enough load for a blocking DB call to matter. Revisit only if that
stops being true (YAGNI — see CLAUDE.md).

Lazily initialized so importing this module (e.g. transitively, via
commands/) doesn't require DATABASE_URL to be set — only actually opening
a session does.

expire_on_commit=False deliberately overrides the SQLAlchemy default:
handlers build their reply (e.g. formatting a PullOutcome's character
name/image) *after* `with session_scope() as session:` exits, once the
session has committed and closed. With the default, every attribute on
every object touched in that session would be expired at commit and
require a live session to re-fetch on next access — raising
DetachedInstanceError right when the handler tries to read it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from loguru import logger
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ley_shards_bot.config import database_url

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _get_session_factory() -> sessionmaker[Session]:
    global _engine, _session_factory
    if _session_factory is None:
        logger.debug("Creating DB engine (first session_scope() call)")
        _engine = create_engine(database_url())
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
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
        logger.opt(exception=True).warning("Rolling back session due to an exception")
        session.rollback()
        raise
    finally:
        session.close()
