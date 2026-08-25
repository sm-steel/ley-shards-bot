"""The gacha pull engine: pity math, banner/rarity/character selection,
ownership + Echoes bookkeeping. See ARCHITECTURE.md's Gacha pulls section
for the rules this encodes.

Framework-agnostic — no python-telegram-bot imports (see CLAUDE.md).

Split deliberately into pure functions (five_star_probability, roll_rarity,
next_pity_counts, resolve_event_five_star — no DB, no I/O) and the
DB-touching orchestration (pull_single, pull_ten) that calls them. The pure
half is what tests/services/test_gacha.py statistically simulates over
thousands of trials; the orchestration half is tested against a real
in-memory session instead.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import select

from ley_shards_bot.models import (
    Banner,
    BannerType,
    Character,
    CurrencyType,
    PityState,
    PlayerCharacter,
    Pull,
    Rarity,
)
from ley_shards_bot.services import currency
from ley_shards_bot.services.players import PlayerRef, get_or_create_player
from ley_shards_bot.time_utils import utc_now

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from sqlalchemy.orm import Session

PULL_COST_LEY_SHARDS = 160
TEN_PULL_SIZE = 10
TEN_PULL_COST_LEY_SHARDS = PULL_COST_LEY_SHARDS * TEN_PULL_SIZE

STANDARD_BANNER_NAME = "Standard Banner"

# 5-star pity: base rate, then a soft-pity ramp starting at pull 74,
# guaranteed by pull 90. Pull numbers below are 1-indexed (the Nth pull
# since the last 5-star, inclusive of this one).
BASE_FIVE_STAR_RATE = 0.006
FIVE_STAR_SOFT_PITY_START = 74
FIVE_STAR_HARD_PITY = 90
FIVE_STAR_SOFT_PITY_INCREMENT = 0.06

# 4-star pity: base rate, hard-guaranteed at least once every 10 pulls.
# A 5-star also counts as "4-star or better" and resets this counter too.
BASE_FOUR_STAR_RATE = 0.13
FOUR_STAR_HARD_PITY = 10

ECHOES_PER_DUPLICATE: dict[Rarity, int] = {
    Rarity.THREE_STAR: 5,
    Rarity.FOUR_STAR: 15,
    Rarity.FIVE_STAR: 50,
}

# A character's first copy is constellation 0 (unlocked, unenhanced). Each
# subsequent duplicate advances one constellation level, up to 6 — so 7
# total copies (1 base + 6 levels) fully constellates a character. Only
# once a player already owns this many copies does a further duplicate
# convert to Echoes instead of leveling anything further. See GACHA.md's
# "Duplicates: constellations, refinement, then Echoes" section.
CONSTELLATION_MAX_COPIES = 7


class InsufficientLeyShardsError(Exception):
    def __init__(self, required: int, available: int) -> None:
        self.required = required
        self.available = available
        super().__init__(f"Need {required} Ley Shards, have {available}.")


class ConfirmationRequiredError(Exception):
    """Raised before any RNG/state mutation when a pull would draw on
    Ley Shards directly — no matching standard ticket for a single pull,
    or a ticket shortfall for a 10-pull — and the caller hasn't already
    confirmed that spend via confirmed_direct_spend=True.
    tickets_to_spend is how many standard tickets will ALSO be spent
    alongside the confirmed Ley Shards amount (0 for a single pull with
    zero tickets; nonzero for a partially-ticket-covered 10-pull)."""

    def __init__(self, ley_shards_required: int, tickets_to_spend: int) -> None:
        self.ley_shards_required = ley_shards_required
        self.tickets_to_spend = tickets_to_spend
        super().__init__(f"Confirm spending {ley_shards_required} Ley Shards directly.")


class EmptyRarityPoolError(Exception):
    """Raised if no characters of a rolled rarity exist — an empty or
    incomplete roster, not a player-facing condition."""


@dataclass(frozen=True)
class PullOutcome:
    character: Character
    rarity: Rarity
    is_new: bool
    echoes_gained: int
    # The level just reached (1-6) on a duplicate-into-level-up pull;
    # None on a first-copy pull or on an Echoes-conversion pull (already
    # at CONSTELLATION_MAX_COPIES). At most one of
    # is_new/constellation_level/echoes_gained is "set" for any outcome.
    constellation_level: int | None
    is_rate_up: bool | None  # None unless this was an event-banner 5-star


# ---------------------------------------------------------------------------
# Pure pity/RNG math
# ---------------------------------------------------------------------------


def five_star_probability(pulls_since_last_5star: int) -> float:
    """Probability the *next* pull is a 5-star, given how many pulls it's
    been since the last one."""
    pull_number = pulls_since_last_5star + 1
    if pull_number >= FIVE_STAR_HARD_PITY:
        return 1.0
    if pull_number < FIVE_STAR_SOFT_PITY_START:
        return BASE_FIVE_STAR_RATE
    pulls_into_ramp = pull_number - FIVE_STAR_SOFT_PITY_START + 1
    return min(1.0, BASE_FIVE_STAR_RATE + pulls_into_ramp * FIVE_STAR_SOFT_PITY_INCREMENT)


def roll_rarity(
    pulls_since_last_5star: int, pulls_since_last_4star: int, rng: random.Random
) -> Rarity:
    if rng.random() < five_star_probability(pulls_since_last_5star):
        return Rarity.FIVE_STAR

    four_star_forced = (pulls_since_last_4star + 1) >= FOUR_STAR_HARD_PITY
    if four_star_forced or rng.random() < BASE_FOUR_STAR_RATE:
        return Rarity.FOUR_STAR

    return Rarity.THREE_STAR


def next_pity_counts(
    pulls_since_last_5star: int, pulls_since_last_4star: int, rarity: Rarity
) -> tuple[int, int]:
    """Pity counters after a pull of the given rarity. A 5-star resets
    both (it's also "4-star or better"); a 4-star resets only its own."""
    if rarity == Rarity.FIVE_STAR:
        return 0, 0
    if rarity == Rarity.FOUR_STAR:
        return pulls_since_last_5star + 1, 0
    return pulls_since_last_5star + 1, pulls_since_last_4star + 1


def resolve_event_five_star(guaranteed_rate_up: bool, rng: random.Random) -> tuple[bool, bool]:
    """The classic 50/50: returns (is_rate_up, guaranteed_rate_up_next_time).
    A prior loss (guaranteed_rate_up=True coming in) always wins this time
    and clears the flag; otherwise it's a coin flip, and losing sets the
    flag for the banner's next 5-star."""
    if guaranteed_rate_up:
        return True, False
    won = rng.random() < 0.5
    return won, not won


def pick_character(pool: Sequence[Character], rng: random.Random) -> Character:
    if not pool:
        msg = "No characters available for this rarity — has the roster been ingested?"
        logger.error("Empty rarity pool: {}", msg)
        raise EmptyRarityPoolError(msg)
    return rng.choice(list(pool))


# ---------------------------------------------------------------------------
# DB-touching orchestration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _PullCostPlan:
    tickets_to_spend: int
    ley_shards_required: int


def _plan_standard_pull_cost(
    session: Session, player_id: int, banner: Banner, pull_count: int
) -> _PullCostPlan:
    """Ticket-then-Ley-Shards cost split for `pull_count` pulls on the
    given banner. TODO(#32): only ever checks STANDARD_TICKET, and only
    when banner.type is STANDARD — /pull and /pull10 always operate on
    the standard banner until banner selection lands, but a non-standard
    banner must never draw on the standard ticket balance (ticket types
    are not interchangeable — see GACHA.md). Once #32 adds an
    event-banner getter, extend this (or add a parallel
    _plan_event_pull_cost) to check EVENT_TICKET the same way for event
    banners."""
    available_tickets = (
        currency.get_balance(session, player_id, CurrencyType.STANDARD_TICKET)
        if banner.type == BannerType.STANDARD
        else 0
    )
    tickets_to_spend = min(available_tickets, pull_count)
    pulls_via_ley_shards = pull_count - tickets_to_spend
    return _PullCostPlan(
        tickets_to_spend=tickets_to_spend,
        ley_shards_required=pulls_via_ley_shards * PULL_COST_LEY_SHARDS,
    )


def get_or_create_standard_banner(session: Session) -> Banner:
    banner = session.scalar(select(Banner).where(Banner.type == BannerType.STANDARD))
    if banner is None:
        logger.info("Creating the standard banner (first pull ever on this deployment)")
        banner = Banner(type=BannerType.STANDARD, name=STANDARD_BANNER_NAME)
        session.add(banner)
        session.flush()
    return banner


def _get_or_create_pity(session: Session, player_id: int, banner_type: BannerType) -> PityState:
    pity = session.get(PityState, (player_id, banner_type))
    if pity is None:
        pity = PityState(player_id=player_id, banner_type=banner_type)
        session.add(pity)
        session.flush()
    return pity


def _characters_of_rarity(session: Session, rarity: Rarity) -> list[Character]:
    return list(session.scalars(select(Character).where(Character.rarity == rarity)))


def _grant_character(
    session: Session, player_id: int, character: Character
) -> tuple[bool, int | None, int]:
    """Add a copy to the player's collection: a brand-new character, a
    constellation level-up (2nd through 7th copy), or — once already at
    the CONSTELLATION_MAX_COPIES cap — a duplicate converted to Echoes
    instead. Returns (is_new, constellation_level, echoes_gained); at
    most one of constellation_level/echoes_gained is set, and neither is
    set when is_new is True."""
    ownership = session.get(PlayerCharacter, (player_id, character.anilist_id))
    if ownership is None:
        session.add(PlayerCharacter(player_id=player_id, character_id=character.anilist_id))
        return True, None, 0

    if ownership.copies_owned < CONSTELLATION_MAX_COPIES:
        ownership.copies_owned += 1
        constellation_level = ownership.copies_owned - 1
        return False, constellation_level, 0

    echoes = ECHOES_PER_DUPLICATE[character.rarity]
    player = get_or_create_player(session, player_id)
    player.echoes += echoes
    return False, None, echoes


def _execute_single_pull(
    session: Session, player_id: int, banner: Banner, rng: random.Random, now: datetime
) -> PullOutcome:
    pity = _get_or_create_pity(session, player_id, banner.type)

    logger.debug(
        "Rolling for player={} banner={} pity(5star={}, 4star={})",
        player_id,
        banner.type,
        pity.pulls_since_last_5star,
        pity.pulls_since_last_4star,
    )
    rarity = roll_rarity(pity.pulls_since_last_5star, pity.pulls_since_last_4star, rng)
    pity.pulls_since_last_5star, pity.pulls_since_last_4star = next_pity_counts(
        pity.pulls_since_last_5star, pity.pulls_since_last_4star, rarity
    )

    is_event_five_star = (
        banner.type == BannerType.EVENT
        and rarity == Rarity.FIVE_STAR
        and banner.rate_up_character_id is not None
    )
    is_rate_up: bool | None = None
    character: Character | None = None
    if is_event_five_star:
        is_rate_up, pity.guaranteed_rate_up = resolve_event_five_star(pity.guaranteed_rate_up, rng)
        logger.debug(
            "Event 50/50 for player={}: is_rate_up={} guaranteed_next={}",
            player_id,
            is_rate_up,
            pity.guaranteed_rate_up,
        )
        if is_rate_up:
            character = session.get(Character, banner.rate_up_character_id)

    if character is None:
        character = pick_character(_characters_of_rarity(session, rarity), rng)

    is_new, constellation_level, echoes_gained = _grant_character(session, player_id, character)
    session.add(
        Pull(
            player_id=player_id,
            banner_id=banner.id,
            character_id=character.anilist_id,
            pulled_at=now,
        )
    )

    return PullOutcome(
        character=character,
        rarity=rarity,
        is_new=is_new,
        echoes_gained=echoes_gained,
        constellation_level=constellation_level,
        is_rate_up=is_rate_up,
    )


def pull_single(
    session: Session,
    player: PlayerRef,
    banner: Banner,
    *,
    rng: random.Random | None = None,
    confirmed_direct_spend: bool = False,
) -> PullOutcome:
    rng = rng or random.Random()
    now = utc_now()

    account = get_or_create_player(session, player.telegram_user_id, username=player.username)
    plan = _plan_standard_pull_cost(session, player.telegram_user_id, banner, 1)
    if plan.ley_shards_required > 0 and account.ley_shards < plan.ley_shards_required:
        logger.warning(
            "Pull rejected for {}: need {} Ley Shards, have {}",
            player.telegram_user_id,
            plan.ley_shards_required,
            account.ley_shards,
        )
        raise InsufficientLeyShardsError(plan.ley_shards_required, account.ley_shards)
    if plan.ley_shards_required > 0 and not confirmed_direct_spend:
        raise ConfirmationRequiredError(plan.ley_shards_required, plan.tickets_to_spend)

    if plan.tickets_to_spend > 0:
        currency.spend(
            session, player.telegram_user_id, CurrencyType.STANDARD_TICKET, plan.tickets_to_spend
        )
    account.ley_shards -= plan.ley_shards_required

    outcome = _execute_single_pull(session, player.telegram_user_id, banner, rng, now)
    session.commit()
    logger.info(
        "Pull: player={} banner={} -> {} {} (new={}, constellation={}, echoes={}, rate_up={}, "
        "tickets_spent={}, ley_shards_spent={})",
        player.telegram_user_id,
        banner.type,
        outcome.rarity,
        outcome.character.name,
        outcome.is_new,
        outcome.constellation_level,
        outcome.echoes_gained,
        outcome.is_rate_up,
        plan.tickets_to_spend,
        plan.ley_shards_required,
    )
    return outcome


def pull_ten(
    session: Session,
    player: PlayerRef,
    banner: Banner,
    *,
    rng: random.Random | None = None,
    confirmed_direct_spend: bool = False,
) -> list[PullOutcome]:
    """Ten pulls charged as one batch. No separate "at least one 4-star+"
    logic is needed here: the continuous pulls_since_last_4star pity
    counter already guarantees a 4-star-or-better at least once every 10
    pulls on its own (see FOUR_STAR_HARD_PITY) — ten sequential pulls
    through the same engine automatically satisfy it."""
    rng = rng or random.Random()
    now = utc_now()

    account = get_or_create_player(session, player.telegram_user_id, username=player.username)
    plan = _plan_standard_pull_cost(session, player.telegram_user_id, banner, TEN_PULL_SIZE)
    if plan.ley_shards_required > 0 and account.ley_shards < plan.ley_shards_required:
        logger.warning(
            "10-pull rejected for {}: need {} Ley Shards, have {}",
            player.telegram_user_id,
            plan.ley_shards_required,
            account.ley_shards,
        )
        raise InsufficientLeyShardsError(plan.ley_shards_required, account.ley_shards)
    if plan.ley_shards_required > 0 and not confirmed_direct_spend:
        raise ConfirmationRequiredError(plan.ley_shards_required, plan.tickets_to_spend)

    if plan.tickets_to_spend > 0:
        currency.spend(
            session, player.telegram_user_id, CurrencyType.STANDARD_TICKET, plan.tickets_to_spend
        )
    account.ley_shards -= plan.ley_shards_required

    outcomes = [
        _execute_single_pull(session, player.telegram_user_id, banner, rng, now)
        for _ in range(TEN_PULL_SIZE)
    ]
    session.commit()
    rarity_counts = Counter(outcome.rarity for outcome in outcomes)
    logger.info(
        "10-pull: player={} banner={} -> {} (tickets_spent={}, ley_shards_spent={})",
        player.telegram_user_id,
        banner.type,
        dict(rarity_counts),
        plan.tickets_to_spend,
        plan.ley_shards_required,
    )
    return outcomes
