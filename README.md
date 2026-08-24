# ley-shards-bot

![Checks](https://github.com/sm-steel/ley-shards-bot/actions/workflows/checks.yml/badge.svg)
![Tests](https://github.com/sm-steel/ley-shards-bot/actions/workflows/tests.yml/badge.svg)

Private Telegram gacha game bot for our group. Players earn **Ley Shards** 💎
and spend them pulling real anime characters (sourced from AniList) on
standard/event banners, with classic pity mechanics. Runs on `moscow`,
routing Telegram API traffic through `helsinki`'s proxy (moscow has no
direct route to `api.telegram.org`).

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

Runs entirely in Docker (bot + MariaDB), via `docker-compose.yml`. On the
target host (moscow):

```sh
cp .env.example .env     # fill in real secrets — see comments in the file
docker compose up -d --build
docker compose logs -f bot
```

The `mariadb` service owns its data in a named volume (`mariadb_data`); the
bot connects to it over the compose network as `mariadb:3306`, not
`localhost`.

## Continuous Integration

Two GitHub Actions workflows run on every push/PR — **Checks**
(`.github/workflows/checks.yml`: `ruff`, `ty`, and `qlty smells`, via the
same `.pre-commit-config.yaml` the local pre-commit hook uses) and
**Tests** (`.github/workflows/tests.yml`: `pytest`). A third workflow,
**Deploy** (`.github/workflows/deploy.yml`), runs only on a push to
`master`: it re-verifies both of the above, then SSHs into `moscow` and
rebuilds/restarts the bot stack — merging to `master` is what ships a
change, no manual deploy step. See `CLAUDE.md` for details.
