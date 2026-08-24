# Game Mechanics: Characters, Weapons, and Economy

This is the authoritative doc for the game's *entities* and the economy
around them: what a character or weapon actually is (rarity, role/element,
stats, constellations/refinement) and where currencies come from. It
covers the full target design across Phase 1, 1.1, and 1.2 — not just
what's implemented today — so each row below is marked with its status.
See `ARCHITECTURE.md` for how the system is built and `GACHA.md` for how
these entities are actually *obtained* (pull costs, pity, banners) —
that's deliberately not repeated here.

## Status

| Feature | Status |
|---|---|
| Ley Shards, Echoes, `/daily`/trickle/`/award_guess`/`/grant` | **Implemented** (Phase 1) |
| Fixed-time (02:00 UTC) daily reset for `/daily`/trickle/`/award_guess` | **Implemented** (Phase 1, fixed post-launch — see "Daily reset" below) |
| Characters: rarity, placeholder base stats | **Implemented** (Phase 1) |
| Character `description`/tags (AniList-sourced) | Planned (Phase 1.1) |
| Standard/event banner tickets | Planned (Phase 1.1) |
| Constellations (character duplicate leveling) | Planned (Phase 1.1) |
| Weapons: rarity, `weapon_type`, base stats | Planned (Phase 1.2) |
| `characters.role`/`element`, admin stat editing | Planned (Phase 1.2) |
| Refinement (weapon duplicate leveling), weapon ticket | Planned (Phase 1.2) |
| Constellation/refinement effects, skills, passives, weapon effects | Planned (Phase 2) |

## Currencies

| Currency | Source | Spend |
|---|---|---|
| **Ley Shards** 💎 | `/daily` (60, once per game day — see "Daily reset" below); first message of the game day (20, auto, once per game day); `/award_guess @user` (15, admin/mod-only, rate-limited to 3 per game day per target); `/grant` (arbitrary, admin-only) | The base currency — direct pulls, or converted into banner tickets via `/buy_ticket` (Phase 1.1). See `GACHA.md`'s "Pull costs" for the confirm-before-spend rule. |
| **Echoes** | Duplicate pulls of an already-maxed character (constellation 6) or weapon (refinement 5, Phase 1.2), scaled by rarity | Banked, not yet spendable — reserved for a future ascension/combat system (Phase 2). Exists so pulling stays a real sink even after a character/weapon is fully leveled — see `GACHA.md`'s "Duplicates" section for exactly when a pull becomes Echoes instead of a level. |
| **Standard ticket** (Phase 1.1) | `/buy_ticket standard <count>`, 160 Ley Shards each | Standard-banner pulls only. |
| **Event ticket** (Phase 1.1) | `/buy_ticket event <count>`, 160 Ley Shards each | Event-character-banner pulls only. |
| **Weapon ticket** (Phase 1.2) | `/buy_ticket weapon <count>`, 160 Ley Shards each | Paired event-weapon-banner pulls only. |

Tickets are plain balance columns on `players` (fungible, like Ley Shards
and Echoes), not individually-owned items — see `ARCHITECTURE.md`'s data
model. Full ticket-purchase/spend mechanics live in `GACHA.md`; this table
is the currency reference, not the pull-time behavior.

### Daily reset

**Implemented.** Fixes a Phase 1 bug found in manual validation (issue
#9) — see issue #42. Every "once per day" limit above —
`/daily`, the first-message trickle, and `/award_guess`'s per-target
3/day cap — resets at a single fixed wall-clock time, **02:00 UTC**, not
at rolling 24h-since-last-claim and not at UTC midnight. This is the
**game day** boundary, and it applies to `/daily`/trickle/`/award_guess`
today and to any future daily-reset mechanic (a Phase 1.1/1.2 feature
that needs "once per day" reuses the same boundary rather than inventing
a new one).

Concretely: a moment's game day is its UTC calendar date *after
subtracting 2 hours* — so `2026-08-24 01:59 UTC` is still game day
`2026-08-23`, and `2026-08-24 02:00 UTC` is game day `2026-08-24`. Two
claims are "the same day" iff they fall in the same game day, however
close together or far apart the wall-clock gap between them actually is.

This replaces `/daily`'s original rolling-24h cooldown (claim, then wait
24h from that exact moment) — found during Phase 1 manual validation
(issue #9) to be the wrong model: a fixed reset time is the standard,
predictable shape for a daily-claim game mechanic (players learn "reset
is at 2am UTC" once, rather than tracking a personal rolling timer per
claim), and it's what `/award_guess`'s per-target limit already
approximated (UTC midnight) — this just moves all three onto the same
explicit boundary instead of two different implicit ones.

## Characters

**Sourcing.** Every character comes from a real, existing anime via the
**AniList GraphQL API** — never invented. Today (Phase 1) that's a bulk
ingestion script bucketing characters into rarity by favourites
percentile; from Phase 1.1 on, it's a curated, one-at-a-time flow: an
admin searches AniList by name in the panel, previews the result (photo,
description, tags), and picks one — the admin sets rarity explicitly at
that point rather than it being computed. See `ARCHITECTURE.md`'s
"Character roster" section for the pipeline itself.

| Attribute | Status | Notes |
|---|---|---|
| `name`, `series`, `image_url` | Implemented | From AniList. |
| `rarity` (3★/4★/5★) | Implemented | Set at import (admin-picked from Phase 1.1 on); drives pull odds — see `GACHA.md`'s Pity section. Admin-editable after the fact from Phase 1.2. |
| `description` | Planned (Phase 1.1) | Captured from AniList at import time, shown in the admin search/preview view; not backfilled for characters already in the roster. |
| tags | Planned (Phase 1.1) | AniList's genre/tag-ish data, stored as simple JSON/text rather than a relational tags model — no "filter by tag" requirement exists yet to justify more (YAGNI). |
| `role`, `element` | Planned (Phase 1.2) | New enum columns. Exact taxonomy (which roles, which elements) is undecided — TBD when that ticket is picked up. |
| `base_hp`/`base_atk`/`base_def`/`base_spd` | Implemented (placeholder) | Auto-derived deterministically at import today, purely as a forward-compatible placeholder — see `ARCHITECTURE.md`'s Roadmap. No gameplay reads these yet; that's Phase 2 (combat). Admin-editable from Phase 1.2 on, alongside `rarity`/`role`/`element`. |
| Constellations | Planned (Phase 1.1) | 6 levels; how a character gains them is a *pull* mechanic — see `GACHA.md`'s "Duplicates: constellations, refinement, then Echoes". What each level actually **grants** (passive abilities) is Phase 2's job, once combat design exists — this phase only builds the counter. |

## Weapons (Phase 1.2)

**Sourcing.** Unlike characters, weapons have no real-world data source —
an admin creates them directly in the panel (name, image, rarity,
`weapon_type`). Flagged as an assumption in the original plan, to confirm
when that ticket is picked up.

| Attribute | Status | Notes |
|---|---|---|
| `name`, `image_url`, `rarity` | Planned (Phase 1.2) | Mirrors `characters`' shape, admin-authored instead of AniList-sourced. |
| `weapon_type` | Planned (Phase 1.2) | New enum column. Exact taxonomy TBD when that ticket is picked up. |
| Base stats | Planned (Phase 1.2) | Same placeholder-for-later-combat treatment as character base stats, admin-set at creation. |
| Refinement | Planned (Phase 1.2) | 5 ranks; a weapon's first copy is already refinement 1 (unlike a character's constellation 0) — see `GACHA.md`'s "Duplicates" section for the full asymmetry and why. Effects are Phase 2's job, same as constellations. |

## Roadmap: skills, passives, effects (Phase 2)

Combat design itself is out of scope until Phase 2 (see `ARCHITECTURE.md`'s
Roadmap) — nothing here means building any of this now. It's the intended
shape once that phase starts, so Phase 1.1/1.2's schema work doesn't make
it awkward to add later:

- **Character skills/passives** and **weapon effects** become their own
  tables (`character_skills`, `character_passives`, `weapon_effects`),
  additively FK'd to `characters`/`weapons` — not a restructuring of the
  base tables, which is exactly why base stats stay plain scalar columns
  today rather than a JSON blob.
- **Constellation/refinement effects** become their own tables too —
  `character_constellations` (`character_id`, `level` 1–6, effect
  description/data) and a `weapon_refinements` equivalent — hanging off
  the level counters Phase 1.1/1.2 already build (see the Characters and
  Weapons sections above), rather than guessed at or half-built now.
