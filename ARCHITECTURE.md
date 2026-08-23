# Architecture

## Overview

A Python Telegram bot providing a gacha game inside one private group chat.
Players collect real anime characters, pulled from **standard** (permanent)
and **event** (rotating, rate-up) banners using a currency they earn for
free, with genre-standard pity mechanics. See `CLAUDE.md` for repo layout
and coding conventions; this doc covers the system design.

```
                         ┌────────────────────────────┐
                         │         moscow VPS          │
                         │  ┌──────────┐  ┌──────────┐ │
Telegram  ◄── proxy ─────┼──┤   bot    │──┤ mariadb  │ │
 servers      (helsinki)  │  │(container)│  │(container)│ │
                         │  └──────────┘  └──────────┘ │
                         │   docker compose network     │
                         └────────────────────────────┘
```

## Infrastructure

- **Host:** `moscow` — chosen for its RAM headroom (a
  containerized MariaDB needs more than a small 1GB box comfortably offers).
- **Docker Compose stack**, two services:
  - `bot` — built from the repo `Dockerfile` (uv-based Python image).
  - `mariadb` — official `mariadb:11` image, data in a named volume. Not
    installed on the host — deliberately containerized like everything else
    deployed to these VPSes.
- **Telegram connectivity:** moscow has no direct route to
  `api.telegram.org`. The bot routes *all* Telegram API traffic — both
  `getUpdates` long-polling and outgoing `send*` calls — through
  `helsinki`'s tinyproxy (`http://<user>:<pass>@helsinki:8888`),
  configured on `ApplicationBuilder`'s `proxy` and `get_updates_proxy`.
  Credentials and both proxies are documented in the vault's
  `инфраструктура/Прокси.md`.
- **Topics:** the group has Telegram topics enabled. A dedicated **"🎰
  Gacha"** topic hosts all game activity; gacha commands are scoped to it
  via `message_thread_id`, keeping it separate from generic chat and the
  "guess the anime" topic.

## Component boundaries

```
commands/  →  services/  →  models/
(Telegram)    (game rules)   (persistence)
```

- **`commands/`** — one handler per Telegram command. Parses the
  `Update`, calls into `services/`, formats the reply. No game rules live
  here.
- **`services/`** — the game logic, framework-agnostic (no
  `python-telegram-bot` imports). This is what unit tests target.
- **`models/`** — SQLAlchemy ORM models, one module per table/aggregate.

This separation exists so pity math, RNG weighting, and balance changes can
be tested as plain Python without a Telegram update or a live DB.

## Data model

| Table | Purpose |
|---|---|
| `players` | Telegram user id, Ley Shards balance, Echoes balance, `last_daily_claimed_at`, `last_trickle_date`. |
| `characters` | Name, series, image URL, rarity (3★/4★/5★), placeholder base stats (HP/ATK/DEF/SPD) for future combat use. |
| `banners` | `type` (standard/event), active date range, nullable rate-up `character_id`. |
| `player_characters` | Ownership: `(player_id, character_id, copies_owned)`. |
| `pity_state` | `(player_id, banner_type)` → current pull count + guarantee flags. Standard and event pity are tracked separately; event pity persists across event banner rotations. |
| `pulls` | History log — `(player_id, banner_id, character_id, timestamp)` — for auditing pity/RNG correctness, not shown to players directly. |

## Economy — "Ley Shards" 💎

| Source | Amount | Rule |
|---|---|---|
| `/daily` | 60 | Once per rolling 24h, per player. |
| First message of the day | 20 | Automatic, capped once/day per player. |
| `/award_guess @user` | 15 | Admin/mod-only, for a correct call in the manual "guess the anime" topic. Rate-limited (max 3/day per target) — that topic isn't bot-run, so this is a manual grant, not detection. |
| `/grant` | arbitrary | Admin-only, for one-off events. |

Duplicate character pulls convert into a second currency, **Echoes**
(amount scaled by rarity) — banked for a future ascension/combat system
rather than refunded as Ley Shards, so pulling stays a real sink.

## Gacha pulls

- Single pull: 160 Ley Shards. 10-pull: 1600, guaranteed ≥ one 4★+.
- **Standard banner:** permanent, full roster, no rate-up.
- **Event banner:** admin-curated rate-up character on top of the standard
  pool; classic 50/50 (losing it guarantees the rate-up on the banner's next
  5★).
- **Pity** (Genshin-shaped): 5★ base rate ~0.6%, soft pity ramps from pull
  ~74, hard pity (guaranteed) at 90. 4★ guaranteed at least once every 10
  pulls. Tracked per player, per banner type.

The exact rates/thresholds are named constants in `services/`, not
scattered literals — see `CLAUDE.md`'s DRY note.

## Character roster

An admin-only ingestion command queries the **AniList GraphQL API**,
ranking characters by `favourites` and keeping only those with artwork.
Favourites percentile buckets characters into rarity (top slice → 5★, next
→ 4★, rest → 3★). Re-running the command pulls in more characters later;
it doesn't need to be re-run for the bot to function once seeded.

## Roadmap (explicitly out of scope for Phase 1)

- **Combat:** turn-based system using pulled characters' stored base
  stats. Own design pass once this phase is validated in the test group.
- **Story:** narrative framing for banners/events, deeper chapter content.
  Own design pass, likely alongside or after combat.

`characters.base_stats` exists now specifically so combat has data to build
on later without re-deriving the roster — that's the only forward-looking
concession Phase 1 makes; everything else follows YAGNI.

## Testing strategy

- **Unit tests** (`tests/`, mirrors `services/`+`models/`): pity/RNG
  statistical simulation (thousands of simulated pulls per banner type
  confirming rates converge and pity actually forces a 5★ by pull 90),
  economy balance math, roster rarity bucketing.
- **Manual end-to-end**: a throwaway test bot + empty test group (topics
  enabled, matching "🎰 Gacha" topic) before anything touches the real
  group. See `README.md` for the deploy commands used there.
