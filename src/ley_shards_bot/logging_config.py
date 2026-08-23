"""Logging setup — the one place logging gets configured.

Uses loguru instead of bare stdlib `logging` calls (project convention,
see the python-tooling skill). python-telegram-bot and its dependencies
still log through stdlib `logging` internally, so stdlib's root logger is
redirected into loguru via the standard InterceptHandler recipe — every
log line, ours or a library's, ends up on the same sink with the same
format.

Level defaults to INFO (LOG_LEVEL env var overrides). DEBUG exists
throughout the codebase for routine/high-frequency events (pity counter
detail, trickle checks, session lifecycle) — it's there to turn on when
diagnosing something, not to run production at by default. See CLAUDE.md's
Logging section for which level to use when adding a new log call.
"""

from __future__ import annotations

import logging
import sys

from loguru import logger


class _InterceptHandler(logging.Handler):
    """Redirects stdlib `logging` records (python-telegram-bot, httpx,
    sqlalchemy, ...) into loguru so everything shares one sink/format."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    logger.remove()
    logger.add(sys.stderr, level=level.upper())
