# ley-shards-bot

![Checks](https://github.com/sm-steel/ley-shards-bot/actions/workflows/checks.yml/badge.svg)
![Tests](https://github.com/sm-steel/ley-shards-bot/actions/workflows/tests.yml/badge.svg)

A private Telegram gacha game bot, built for a small friend group but
self-hostable by anyone. Players earn **Ley Shards** 💎 and spend them
pulling real anime characters (sourced from AniList) on standard/event
banners, with classic pity mechanics.

Phase 1 scope (this repo, currently): bot skeleton, economy, gacha pulls,
collection viewer. Turn-based combat and story content are tracked as
follow-up phases — see the design plan.

## Stack

- Python 3.11+, managed with [uv](https://docs.astral.sh/uv/)
- [python-telegram-bot](https://docs.python-telegram-bot.org/) (async, long-polling)
- SQLAlchemy + Alembic against MariaDB
- Linting/formatting: `ruff`. Type checking: `ty`.

## Dev setup

```sh
uv sync                  # install deps + create .venv
cp .env.example .env     # fill in BOT_TOKEN, DATABASE_URL, etc.
uv run pytest            # run tests
uv run ruff check .      # lint
uv run ruff format .     # format
uv run ty check          # type check
```

## Deployment

Runs entirely in Docker (bot + MariaDB), via `docker-compose.yml`. These
steps set up your own instance.

### 1. Prerequisites

- Docker + the Docker Compose plugin installed on your host
- A Telegram account to create the bot with

### 2. Create a Telegram bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram, send
   `/newbot`, and follow the prompts.
2. Save the bot token it gives you — this is `BOT_TOKEN`.
3. Add the bot to your group. If you want the rare-pull group
   announcement to post into a specific [forum
   topic](https://telegram.org/blog/topics-in-groups-collectible-usernames),
   create or pick that topic too.

### 3. Get `GROUP_CHAT_ID` and `GACHA_TOPIC_ID`

1. Add the bot to your group as an admin (needed to read messages/topics).
2. Send a message in the group (and, if using a topic, in that topic).
3. Open `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates` in a browser
   — in the response, `message.chat.id` is `GROUP_CHAT_ID`, and
   `message.message_thread_id` (if present) is `GACHA_TOPIC_ID`.

### 4. Configure `.env`

```sh
cp .env.example .env
```

Fill in `BOT_TOKEN`, `GROUP_CHAT_ID`, `GACHA_TOPIC_ID`, `ADMIN_USER_IDS`
(comma-separated Telegram user ids), and the `MARIADB_*`/`DATABASE_URL`
credentials (they must match each other). Only set `TELEGRAM_PROXY_URL`
if your host has no direct route to `api.telegram.org` — see
`ARCHITECTURE.md`'s Infrastructure section.

### 5. Run it

Build from source:

```sh
docker compose up -d --build
```

Or run the pre-built image published to GHCR on every release instead of
building locally — add a `docker-compose.override.yml` that overrides the
`bot` service's `build: .` with
`image: ghcr.io/sm-steel/ley-shards-bot:<version>` (see
[Releases](https://github.com/sm-steel/ley-shards-bot/releases) for
available tags).

### 6. Updating

Pull the latest code (or a new image tag) and re-run `docker compose up
-d --build` — or `docker compose pull && docker compose up -d` if you're
using the pre-built image. The `mariadb` service owns its data in a named
volume (`mariadb_data`), so it's unaffected by rebuilding/restarting
`bot`; the bot connects to it over the compose network as
`mariadb:3306`, not `localhost`.

## Continuous Integration

Three GitHub Actions workflows run on this repo — **Checks**
(`.github/workflows/checks.yml`, every push/PR: `ruff`, `ty`, and `qlty
smells`, via the same `.pre-commit-config.yaml` the local pre-commit hook
uses), **Tests** (`.github/workflows/tests.yml`, every push/PR:
`pytest`), and **Release** (`.github/workflows/release.yml`, on push to
`master`: runs `python-semantic-release` and publishes a versioned image
to GHCR when a release is cut). Deploying that image to your own host
isn't automated by a workflow in this repo — see Deployment above.
