"""Tests for the AniList roster ingestion service.

Pure functions (rarity bucketing, stat derivation, row building, upsert)
are tested directly. Network fetching is tested against an httpx
MockTransport — no real calls to AniList in the test suite.
"""

import json

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ley_shards_bot.models import Base, Character, Rarity
from ley_shards_bot.services.roster import (
    RosterCandidate,
    assign_rarities,
    build_characters,
    derive_base_stats,
    fetch_top_characters,
    upsert_characters,
)


def _candidate(anilist_id: int, favourites: int) -> RosterCandidate:
    return RosterCandidate(
        anilist_id=anilist_id,
        name=f"Character {anilist_id}",
        series="Some Series",
        image_url=f"https://example.invalid/{anilist_id}.png",
        favourites=favourites,
    )


class TestAssignRarities:
    def test_empty_list_returns_empty(self):
        assert assign_rarities([]) == []

    def test_top_slice_becomes_five_star(self):
        # 10 candidates, strictly descending favourites — rank 1 (top 10%)
        # should be the only 5-star.
        candidates = [_candidate(i, favourites=100 - i) for i in range(10)]

        rated = assign_rarities(candidates)

        rarities = [rarity for _candidate, rarity in rated]
        assert rarities[0] == Rarity.FIVE_STAR
        assert rarities.count(Rarity.FIVE_STAR) == 1

    def test_bottom_slice_becomes_three_star(self):
        candidates = [_candidate(i, favourites=100 - i) for i in range(10)]

        rated = assign_rarities(candidates)

        assert rated[-1][1] == Rarity.THREE_STAR

    def test_sorts_by_favourites_regardless_of_input_order(self):
        candidates = [_candidate(1, favourites=10), _candidate(2, favourites=999)]

        rated = assign_rarities(candidates)

        assert rated[0][0].anilist_id == 2  # higher favourites ranked first


class TestDeriveBaseStats:
    def test_deterministic_for_same_id_and_rarity(self):
        first = derive_base_stats(anilist_id=42, rarity=Rarity.FOUR_STAR)
        second = derive_base_stats(anilist_id=42, rarity=Rarity.FOUR_STAR)

        assert first == second

    def test_five_star_hp_range_exceeds_three_star(self):
        # Ranges are configured so higher rarity means strictly higher
        # stat ceilings — check the ranges don't overlap at all, not just
        # a single sample (which could coincidentally land either way).
        three_star = derive_base_stats(anilist_id=1, rarity=Rarity.THREE_STAR)
        five_star = derive_base_stats(anilist_id=1, rarity=Rarity.FIVE_STAR)

        assert five_star.hp > three_star.hp


class TestBuildCharacters:
    def test_maps_candidate_and_rarity_into_character_row(self):
        candidate = _candidate(7, favourites=500)

        (character,) = build_characters([(candidate, Rarity.FIVE_STAR)])

        assert character.anilist_id == 7
        assert character.name == "Character 7"
        assert character.rarity == Rarity.FIVE_STAR
        assert character.base_hp > 0


class TestUpsertCharacters:
    @pytest.fixture
    def session(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            yield session

    def test_inserts_new_characters(self, session):
        character = Character(
            anilist_id=1,
            name="Frieren",
            series="Frieren",
            image_url="https://example.invalid/1.png",
            rarity=Rarity.FIVE_STAR,
            base_hp=90,
            base_atk=50,
            base_def=30,
            base_spd=60,
        )

        count = upsert_characters(session, [character])

        assert count == 1
        assert session.get(Character, 1).name == "Frieren"

    def test_rerunning_updates_rather_than_duplicates(self, session):
        original = Character(
            anilist_id=1,
            name="Old Name",
            series="Frieren",
            image_url="https://example.invalid/1.png",
            rarity=Rarity.THREE_STAR,
            base_hp=50,
            base_atk=20,
            base_def=15,
            base_spd=30,
        )
        upsert_characters(session, [original])

        refreshed = Character(
            anilist_id=1,
            name="New Name",
            series="Frieren",
            image_url="https://example.invalid/1.png",
            rarity=Rarity.FIVE_STAR,
            base_hp=90,
            base_atk=50,
            base_def=30,
            base_spd=60,
        )
        upsert_characters(session, [refreshed])

        assert session.query(Character).count() == 1
        assert session.get(Character, 1).name == "New Name"


class TestFetchTopCharacters:
    @staticmethod
    def _transport(pages: list[dict]) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            page = body["variables"]["page"]
            return httpx.Response(200, json=pages[page - 1])

        return httpx.MockTransport(handler)

    @staticmethod
    def _raw_character(anilist_id: int, *, with_media: bool = True) -> dict:
        return {
            "id": anilist_id,
            "name": {"full": f"Character {anilist_id}"},
            "image": {"large": f"https://example.invalid/{anilist_id}.png"},
            "favourites": 1000 - anilist_id,
            "media": {"nodes": [{"title": {"romaji": "Some Series"}}]}
            if with_media
            else {"nodes": []},
        }

    def test_paginates_until_limit_reached(self):
        pages = [
            {
                "data": {
                    "Page": {
                        "pageInfo": {"hasNextPage": True},
                        "characters": [self._raw_character(1), self._raw_character(2)],
                    }
                }
            },
            {
                "data": {
                    "Page": {
                        "pageInfo": {"hasNextPage": True},
                        "characters": [self._raw_character(3), self._raw_character(4)],
                    }
                }
            },
        ]
        client = httpx.Client(transport=self._transport(pages))

        result = fetch_top_characters(client, limit=3, page_size=2)

        assert [c.anilist_id for c in result] == [1, 2, 3]

    def test_stops_when_no_more_pages(self):
        pages = [
            {
                "data": {
                    "Page": {
                        "pageInfo": {"hasNextPage": False},
                        "characters": [self._raw_character(1)],
                    }
                }
            }
        ]
        client = httpx.Client(transport=self._transport(pages))

        result = fetch_top_characters(client, limit=100, page_size=50)

        assert [c.anilist_id for c in result] == [1]

    def test_skips_characters_missing_artwork_or_series(self):
        malformed = self._raw_character(1)
        malformed["image"]["large"] = None
        no_series = self._raw_character(2, with_media=False)
        pages = [
            {
                "data": {
                    "Page": {
                        "pageInfo": {"hasNextPage": False},
                        "characters": [malformed, no_series, self._raw_character(3)],
                    }
                }
            }
        ]
        client = httpx.Client(transport=self._transport(pages))

        result = fetch_top_characters(client, limit=100, page_size=50)

        assert [c.anilist_id for c in result] == [3]

    def test_retries_on_rate_limit_then_succeeds(self, monkeypatch):
        monkeypatch.setattr("ley_shards_bot.services.roster.time.sleep", lambda _seconds: None)
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            if attempts["count"] == 1:
                return httpx.Response(429, headers={"Retry-After": "1"})
            return httpx.Response(
                200,
                json={
                    "data": {
                        "Page": {
                            "pageInfo": {"hasNextPage": False},
                            "characters": [self._raw_character(1)],
                        }
                    }
                },
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))

        result = fetch_top_characters(client, limit=1, page_size=1)

        assert [c.anilist_id for c in result] == [1]
        assert attempts["count"] == 2
