"""Character roster ingestion — sources pullable characters from AniList.

Framework-agnostic (no python-telegram-bot imports): meant to be driven by
scripts/ingest_roster.py, an admin-run CLI, not a live bot command. See
CLAUDE.md for the commands/services/models boundary this follows.

Pipeline: fetch_top_characters -> assign_rarities -> build_characters ->
upsert_characters. Each stage is a separate function so the pure parts
(everything except the actual HTTP fetch and DB write) are easy to test
without a network connection or a real database.
"""

from __future__ import annotations

import random
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING

import httpx
from loguru import logger

from ley_shards_bot.models import Character, Rarity

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

ANILIST_GRAPHQL_URL = "https://graphql.anilist.co"
DEFAULT_ROSTER_SIZE = 300
PAGE_SIZE = 50
MAX_RATE_LIMIT_RETRIES = 5
DEFAULT_RETRY_AFTER_SECONDS = 5.0

# Rarity is assigned by percentile rank within the fetched, favourites-sorted
# set: the top FIVE_STAR_PERCENTILE of characters become 5-star, the next
# slice up through FOUR_STAR_PERCENTILE become 4-star, the rest 3-star.
FIVE_STAR_PERCENTILE = 0.10
FOUR_STAR_PERCENTILE = 0.35

# Base combat stat ranges per rarity — placeholder data for a future combat
# system (see ARCHITECTURE.md Roadmap). Deliberately simple: higher rarity
# means a strictly higher floor and ceiling on every stat.
STAT_RANGES: dict[Rarity, dict[str, tuple[int, int]]] = {
    Rarity.THREE_STAR: {"hp": (40, 60), "atk": (20, 35), "defense": (15, 25), "spd": (30, 45)},
    Rarity.FOUR_STAR: {"hp": (60, 80), "atk": (35, 50), "defense": (25, 35), "spd": (45, 60)},
    Rarity.FIVE_STAR: {"hp": (80, 100), "atk": (50, 65), "defense": (35, 45), "spd": (60, 75)},
}

_CHARACTERS_QUERY = """
query ($page: Int, $perPage: Int) {
  Page(page: $page, perPage: $perPage) {
    pageInfo { hasNextPage }
    characters(sort: FAVOURITES_DESC) {
      id
      name { full }
      image { large }
      favourites
      media(sort: POPULARITY_DESC, perPage: 1) {
        nodes { title { romaji } }
      }
    }
  }
}
"""


@dataclass(frozen=True)
class RosterCandidate:
    anilist_id: int
    name: str
    series: str
    image_url: str
    favourites: int


@dataclass(frozen=True)
class BaseStats:
    hp: int
    atk: int
    defense: int
    spd: int


def _parse_candidate(raw: dict) -> RosterCandidate | None:
    """None if the character is missing artwork or a series — skip those
    rather than storing an incomplete roster entry."""
    image_url = (raw.get("image") or {}).get("large")
    media_nodes = (raw.get("media") or {}).get("nodes") or []
    name = (raw.get("name") or {}).get("full")
    series = media_nodes[0]["title"]["romaji"] if media_nodes else None
    if not image_url or not series or not name:
        return None
    return RosterCandidate(
        anilist_id=raw["id"],
        name=name,
        series=series,
        image_url=image_url,
        favourites=raw.get("favourites") or 0,
    )


def _request_page(client: httpx.Client, *, page: int, per_page: int) -> dict:
    for _attempt in range(MAX_RATE_LIMIT_RETRIES):
        response = client.post(
            ANILIST_GRAPHQL_URL,
            json={"query": _CHARACTERS_QUERY, "variables": {"page": page, "perPage": per_page}},
        )
        if response.status_code != HTTPStatus.TOO_MANY_REQUESTS:
            response.raise_for_status()
            return response.json()["data"]["Page"]
        retry_after = float(response.headers.get("Retry-After", DEFAULT_RETRY_AFTER_SECONDS))
        logger.warning("AniList rate-limited us on page {}, retrying in {}s", page, retry_after)
        time.sleep(retry_after)
    msg = f"AniList rate limit retries exhausted (page {page})"
    logger.error(msg)
    raise RuntimeError(msg)


def fetch_top_characters(
    client: httpx.Client, *, limit: int = DEFAULT_ROSTER_SIZE, page_size: int = PAGE_SIZE
) -> list[RosterCandidate]:
    """Fetch characters from AniList, favourites-descending, until `limit`
    valid candidates are collected or AniList runs out of pages."""
    candidates: list[RosterCandidate] = []
    page = 1
    while len(candidates) < limit:
        logger.debug(
            "Fetching AniList page {} (have {}/{} candidates)", page, len(candidates), limit
        )
        page_data = _request_page(client, page=page, per_page=page_size)
        skipped = 0
        for raw in page_data["characters"]:
            candidate = _parse_candidate(raw)
            if candidate is not None:
                candidates.append(candidate)
            else:
                skipped += 1
            if len(candidates) >= limit:
                break
        if skipped:
            logger.debug("Skipped {} characters on page {} (missing art/series)", skipped, page)
        if not page_data["pageInfo"]["hasNextPage"]:
            logger.info("AniList has no more pages; stopping at {} candidates", len(candidates))
            break
        page += 1
    logger.info("Fetched {} roster candidates from AniList", len(candidates))
    return candidates


def assign_rarities(
    candidates: Sequence[RosterCandidate],
) -> list[tuple[RosterCandidate, Rarity]]:
    """Bucket candidates into rarities by favourites-percentile rank."""
    ordered = sorted(candidates, key=lambda c: c.favourites, reverse=True)
    total = len(ordered)
    rated: list[tuple[RosterCandidate, Rarity]] = []
    for rank, candidate in enumerate(ordered):
        percentile = (rank + 1) / total
        if percentile <= FIVE_STAR_PERCENTILE:
            rarity = Rarity.FIVE_STAR
        elif percentile <= FOUR_STAR_PERCENTILE:
            rarity = Rarity.FOUR_STAR
        else:
            rarity = Rarity.THREE_STAR
        rated.append((candidate, rarity))
    return rated


def derive_base_stats(anilist_id: int, rarity: Rarity) -> BaseStats:
    """Deterministic placeholder stats — same id + rarity always yields the
    same result, so re-ingestion doesn't reroll a character's stats."""
    rng = random.Random(anilist_id * 10 + rarity.value)
    ranges = STAT_RANGES[rarity]
    return BaseStats(
        hp=rng.randint(*ranges["hp"]),
        atk=rng.randint(*ranges["atk"]),
        defense=rng.randint(*ranges["defense"]),
        spd=rng.randint(*ranges["spd"]),
    )


def build_characters(rated: Iterable[tuple[RosterCandidate, Rarity]]) -> list[Character]:
    characters = []
    for candidate, rarity in rated:
        stats = derive_base_stats(candidate.anilist_id, rarity)
        characters.append(
            Character(
                anilist_id=candidate.anilist_id,
                name=candidate.name,
                series=candidate.series,
                image_url=candidate.image_url,
                rarity=rarity,
                base_hp=stats.hp,
                base_atk=stats.atk,
                base_def=stats.defense,
                base_spd=stats.spd,
            )
        )
    return characters


def upsert_characters(session: Session, characters: Iterable[Character]) -> int:
    """Insert-or-update by anilist_id, so re-running ingestion refreshes
    existing rows instead of duplicating them."""
    count = 0
    for character in characters:
        session.merge(character)
        count += 1
    session.commit()
    logger.info("Upserted {} characters into the roster", count)
    return count
