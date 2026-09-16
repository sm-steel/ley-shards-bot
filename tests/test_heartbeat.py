import asyncio
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from telegram.ext import Application

from ley_shards_bot import heartbeat


@pytest.mark.asyncio
async def test_install_touches_heartbeat_after_successful_get_updates(tmp_path: Path) -> None:
    heartbeat_path = tmp_path / "heartbeat"
    application = Application.builder().token("123:fake-token-for-test").build()

    original = AsyncMock(return_value=[])
    type(application.bot).get_updates = original

    heartbeat.install(application, heartbeat_path=heartbeat_path)

    # install() itself touches the file once immediately.
    first_mtime = heartbeat_path.stat().st_mtime

    # ensure a distinguishable mtime on filesystems with coarse resolution
    await asyncio.sleep(0.01)
    await type(application.bot).get_updates(application.bot)

    second_mtime = heartbeat_path.stat().st_mtime
    assert second_mtime > first_mtime


@pytest.mark.asyncio
async def test_install_does_not_touch_heartbeat_on_failed_get_updates(tmp_path: Path) -> None:
    heartbeat_path = tmp_path / "heartbeat"
    application = Application.builder().token("123:fake-token-for-test").build()

    async def failing_get_updates(self, *args, **kwargs):
        raise RuntimeError("simulated network failure")

    type(application.bot).get_updates = cast(Any, failing_get_updates)

    heartbeat.install(application, heartbeat_path=heartbeat_path)
    first_mtime = heartbeat_path.stat().st_mtime

    await asyncio.sleep(0.01)
    with pytest.raises(RuntimeError, match="simulated network failure"):
        await type(application.bot).get_updates(application.bot)

    second_mtime = heartbeat_path.stat().st_mtime
    assert second_mtime == first_mtime
