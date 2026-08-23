"""Admin-run CLI: populate/refresh the character roster from AniList.

Re-runnable — upserts by anilist_id, so running it again just refreshes
existing rows and adds newly-qualifying characters. See
ley_shards_bot.services.roster for the actual pipeline.

Usage:
    uv run python scripts/ingest_roster.py [--limit 300]

Requires DATABASE_URL in the environment/.env (see .env.example) — nothing
else from the bot's config is needed to run this.
"""

from __future__ import annotations

import argparse

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ley_shards_bot.config import database_url
from ley_shards_bot.services.roster import (
    DEFAULT_ROSTER_SIZE,
    assign_rarities,
    build_characters,
    fetch_top_characters,
    upsert_characters,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_ROSTER_SIZE,
        help=f"how many characters to fetch (default: {DEFAULT_ROSTER_SIZE})",
    )
    args = parser.parse_args()

    engine = create_engine(database_url())
    with httpx.Client(timeout=30) as client, Session(engine) as session:
        candidates = fetch_top_characters(client, limit=args.limit)
        rated = assign_rarities(candidates)
        characters = build_characters(rated)
        count = upsert_characters(session, characters)

    print(f"Upserted {count} characters.")


if __name__ == "__main__":
    main()
