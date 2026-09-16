"""Liveness heartbeat for the getUpdates polling loop, written to disk
so a Docker HEALTHCHECK can detect it going stale (see
docker-compose.yml's `bot` service).

Guards against a specific failure mode: a wedged httpx connection pool
can leave getUpdates polling silently dead for hours while the process
keeps running and retrying, with nothing externally visible as broken.
Works even though this bot drives polling via `application.run_polling()`
rather than a hand-rolled loop: `install()` wraps the bot's real
`get_updates` call itself, and `run_polling()` still calls
`bot.get_updates()` internally under the hood — the heartbeat file is
touched on the line after any real call returns successfully,
regardless of what drives the polling loop above it.

Deliberately NOT a periodic `JobQueue` job: `JobQueue` runs on its own
scheduler, a separate asyncio task from the `Updater`'s polling loop —
a stuck `httpx` pool wait doesn't block the event loop, so a periodic
job would keep firing (and reporting "healthy") straight through an
outage exactly like that one.

Patches the bot's *class* (`type(application.bot).get_updates = ...`),
not the instance: `TelegramObject.__setattr__` freezes every attribute
assignment on a live instance once constructed, raising
"AttributeError: Attribute `get_updates` of class `ExtBot` can't be
set!" if you try the instance directly. Patching the class uses
`type.__setattr__` mutating the class's own namespace instead, which
bypasses that guard entirely."""

import asyncio
from pathlib import Path

from telegram.ext import Application

HEARTBEAT_PATH = Path("/tmp/ley-shards-bot-heartbeat")  # noqa: S108 - container-local, not shared


def install(application: Application, *, heartbeat_path: Path = HEARTBEAT_PATH) -> None:
    """Wraps `get_updates` on the bot's *class* (see module docstring
    for why not the instance) so `heartbeat_path` is only touched after
    a real call returns without raising. If the call raises (pool
    timeout, ConnectTimeout, Conflict, anything else), the file simply
    stops updating and goes stale — which is exactly what the Docker
    healthcheck watches for."""
    bot_class = type(application.bot)
    original_get_updates = bot_class.get_updates

    async def get_updates_with_heartbeat(self, *args, **kwargs):
        result = await original_get_updates(self, *args, **kwargs)
        await asyncio.to_thread(heartbeat_path.touch)
        return result

    bot_class.get_updates = get_updates_with_heartbeat
    heartbeat_path.touch()  # a first heartbeat right away, before polling has even started
