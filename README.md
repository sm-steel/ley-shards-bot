# ley-shards-bot

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
