# ley-shards-bot

Private Telegram gacha game bot for a small friend group. Players earn
**Ley Shards** 💎 and spend them pulling real anime characters (sourced from
AniList) on standard/event banners, with classic gacha pity mechanics.
Runs as a Docker Compose stack on the `moscow` VPS.

**Read `ARCHITECTURE.md` before making non-trivial changes** — it covers the
system design, data model, gacha/pity rules, and infra topology (why
Telegram traffic is proxied through `helsinki`, etc.). This file is about
where things live and how to work in this repo day to day.

## Where things are

```
src/ley_shards_bot/
  config.py       # env/.env loading — the only place that reads os.environ
  commands/       # one module per Telegram command (thin: parse update,
                   # call a service, format a reply — no business logic here)
  services/       # the actual game logic: economy, gacha engine, roster
                   # ingestion. Framework-agnostic — no python-telegram-bot
                   # imports in this package.
  models/         # SQLAlchemy ORM models, one module per table/aggregate
migrations/       # Alembic migrations
tests/            # mirrors src/ layout; unit tests target services/ and
                   # models/, not the Telegram command handlers directly
scripts/          # one-off / operational scripts (e.g. roster ingestion CLI)
Dockerfile, docker-compose.yml   # bot + mariadb, see ARCHITECTURE.md
```

Current scope is **Phase 1**: bot skeleton, economy, gacha pulls, collection
viewing. Turn-based combat and story content are explicitly out of scope for
now (see ARCHITECTURE.md's Roadmap section) — don't build toward them
speculatively.

## Tooling

Python 3.11+, managed with `uv`. Don't use pip/venv/poetry directly, and
don't invoke `ruff`/`ty`/`pytest` as bare commands — always run them through
`uv run` so they use the project's pinned versions and `.venv`, not
whatever (if anything) is on PATH.

```sh
uv sync                  # install deps + create .venv
uv run pytest            # test
uv run ruff check .      # lint
uv run ruff format .     # format
uv run ty check          # type check
```

Deployment is Docker-only (see `README.md`) — no bare-metal installs on the
target VPS, including the database.

## Verifying changes

**Before considering any Python change done, run all three — in this
order, via `uv run` — and fix everything they report:**

```sh
uv run ruff check .      # lint (add --fix to autofix what's safe to autofix)
uv run ruff format .     # format
uv run ty check          # type check
```

Then run the relevant tests (`uv run pytest`, or a narrower `uv run pytest
tests/path/to/test_thing.py` while iterating). A change isn't finished if
any of the four fail — don't leave known ruff/ty findings for later or
describe work as complete while they're still red.

## Task tracking (GitHub Issues)

Implementation progress is tracked as **GitHub Issues** on this repo
(`sm-steel/ley-shards-bot`, public), grouped into **Milestones** per phase
(e.g. "Phase 1: Core Economy & Pulls"). Use the `gh` CLI (`gh issue list`,
`gh issue create`, `gh issue close`, `gh api repos/sm-steel/ley-shards-bot/milestones`)
rather than inventing a separate tracking file — the issue tracker is the
source of truth for what's done/in progress/planned.

**Security rule — no exceptions, the repo is public:**

> **Never put real logins, hostnames, IPs, passwords, API keys/tokens, SSH
> keys, or any other credential into an issue title, issue body, issue
> comment, PR description, PR comment, or commit message.** This includes
> the owned VPS infrastructure this bot deploys to. Use the same
> placeholders as the rest of this repo (`USERNAME`, `PASSWORD`,
> `PROXY_HOST`, `PROXY_PORT`, `<user>`, `<pass>`, or an alias like `moscow`/
> `helsinki` with no FQDN) and point at "the ops vault" for real values —
> never write them out, even "temporarily" or "just to explain the bug."
> Everything in this repo — commits, issues, PRs, history — is public and
> indexed by anyone/anything crawling GitHub; there is no private fallback
> to catch a slip.

## Coding practices

- **KISS.** This is a small game for a handful of friends, not a platform.
  Prefer the boring, direct implementation over a general one. Don't add
  configurability, abstraction layers, or plugin points nothing currently
  needs.
- **YAGNI.** Don't build for combat/story now (see Roadmap) — Phase 1's data
  model leaves room for them (e.g. `characters` stores base stats) without
  implementing them.
- **SOLID, applied pragmatically:**
  - *Single responsibility*: a `commands/` handler parses the Telegram
    update and formats the reply; a `services/` function holds the actual
    rule (pity math, balance changes, roster ranking). Keep that boundary —
    it's what makes the game logic testable without spinning up a bot.
  - *Dependency inversion*: `services/` and `models/` never import
    `telegram`/`python-telegram-bot`. Command handlers depend on services,
    not the other way around.
  - Don't chase the rest of SOLID for its own sake — no interfaces with a
    single implementation, no factories for things that are never swapped.
- **DRY** the game rules (pity thresholds, costs, rarity weights) — define
  them once as named constants in `services/`, not re-literaled across
  handlers and tests.
- Prefer pure functions for anything with game-math in it (pity rolls,
  balance math, rarity bucketing) — deterministic given a seed/RNG passed
  in, so it's easy to unit-test with `uv run pytest` (write the test first).
