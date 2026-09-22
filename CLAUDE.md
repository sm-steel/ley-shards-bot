# ley-shards-bot

Private Telegram gacha game bot for a small friend group. Players earn
**Ley Shards** 💎 and spend them pulling real anime characters (sourced from
AniList) on standard/event banners, with classic gacha pity mechanics.
Runs as a Docker Compose stack on a self-hosted VPS.

**Read `ARCHITECTURE.md` before making non-trivial changes** — it covers the
system design, data model, and infra topology (e.g. why Telegram traffic
may need to be routed through a proxy, depending on your host). `GACHA.md`
covers pull mechanics
(costs, pity, banners) and `MECHANICS.md` covers the game entities
(characters, weapons) and economy — read whichever is relevant before
touching gacha/economy code. This file is about where things live and how
to work in this repo day to day.

## Where things are

```
src/ley_shards_bot/
  config.py       # env/.env loading — the only place that reads os.environ
  commands/       # one module per Telegram command (thin: parse update,
                   # call a service, format a reply — no business logic here)
    helpers/      # shared Telegram-aware plumbing used across commands —
                   # scoping/permission checks, target resolution, shared
                   # formatting, the command menu. Nothing here registers a
                   # CommandHandler; see ARCHITECTURE.md's Component
                   # boundaries for the full commands/ vs commands/helpers/
                   # split and why it exists.
  services/       # the actual game logic: economy, gacha engine, roster
                   # ingestion, plus shared cross-domain concepts no single
                   # domain owns (players.py, pagination.py). Framework-
                   # agnostic — no python-telegram-bot imports in this
                   # package.
  models/         # SQLAlchemy ORM models, one module per table/aggregate
  api/            # (Phase 1.1) FastAPI routes for the admin panel — same
                   # rule as commands/: parse the request, call a service,
                   # return a response, no business logic here either.
                   # Shares services/+models/ with the bot, doesn't
                   # reimplement game rules.
migrations/       # Alembic migrations
tests/            # mirrors src/ layout, including tests/commands/ — unit
                   # tests target services/, models/, AND the Telegram
                   # command handlers directly (thin-layer: topic scoping,
                   # error-to-reply mapping, not the game math those
                   # handlers call into)
scripts/          # one-off / operational scripts (e.g. roster ingestion CLI)
admin/            # (Phase 1.1) Vite + TypeScript + React admin frontend —
                   # separate toolchain, see "Tooling" below. Built to
                   # static assets and served by api/.
Dockerfile, docker-compose.yml   # bot + mariadb (+ api from Phase 1.1),
                                  # see ARCHITECTURE.md
```

Current scope is **Phase 1** (shipped): bot skeleton, economy, gacha pulls,
collection viewing. **Phase 1.1** (admin panel, banner curation, banner
tickets) and **Phase 1.2** (weapons) are designed — see `GACHA.md`,
`MECHANICS.md`, and `ARCHITECTURE.md` for the target design — but not yet
built; work happens ticket-by-ticket against the GitHub issues for those
milestones, not ahead of them. Turn-based combat and story content are
explicitly out of scope even for those (see `ARCHITECTURE.md`'s Roadmap
section) — don't build toward them speculatively.

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

**`admin/` (Phase 1.1) is a separate toolchain — Vite + TypeScript +
React, linted/formatted with `biome`, not `uv`/`ruff`/`ty`.** Don't run
Python verify commands against it or vice versa; its own verify commands
land here once the frontend is scaffolded enough to know the exact ones.
**shadcn/ui is the UI component library for all web work** in `admin/`
(docs: https://ui.shadcn.com/docs) — reach for it before hand-rolling or
reaching for a second component library. Its Claude Code skill
(https://ui.shadcn.com/docs/skills) is installed in `admin/` once
`components.json` exists there.

**[qlty](https://github.com/qltysh/qlty) checks Python complexity and
duplication** — neither is covered by `ruff`/`ty`. It's a standalone
native binary (installed once per machine via `qlty.sh`'s install
script, `~/.qlty/bin` — not a `uv` dependency, nothing in
`pyproject.toml`), configured by the committed `.qlty/qlty.toml`. Only
its own built-in complexity/duplication analysis is enabled; every
third-party linter plugin it can also run (ruff, bandit, radarlint,
hadolint, trufflehog, ripgrep) is explicitly disabled in that config —
`ruff`/`ty` via `uv run` stay the only linter/type-checker, this tool
adds a capability they don't have rather than a second copy of one they
already do.

```sh
qlty smells --all --no-snippets   # complexity + duplication findings
qlty metrics --all --sort complexity --limit 15   # per-file complexity/LOC table
```

**Never resolve a qlty finding by loosening its check (raising a
threshold, disabling a rule, excluding a path) — fix the actual code.**
A finding is a real signal about the code, not the config; adjusting
`.qlty/qlty.toml` to make it stop appearing is hiding the problem, not
solving it, and quietly lowers the bar for everything after it. If a
finding turns out to be a false positive on inspection (not just
inconvenient), say so explicitly and get confirmation before touching
the config — don't default to loosening it.

**All four checks — `ruff check`, `ruff format --check`, `ty check`,
`qlty smells` — run as a git pre-commit hook** via
[pre-commit](https://pre-commit.com) (`.pre-commit-config.yaml`,
installed as a `uv` dev dependency — `uv run pre-commit install` sets up
the hook once per clone). A commit is blocked if any of them fail;
output prints straight to the terminal (or to whatever ran `git
commit`), same as running the commands by hand. Every hook is a `local`
entry (`language: system`) that shells out to the project's own `uv run
ruff`/`uv run ty` — deliberately **not** the hosted
`astral-sh/ruff-pre-commit` repo, which pins its own separate tool
version independent of this project's `uv.lock` and could drift out of
sync. `qlty` is expected on `PATH` (see above); a shell opened before
qlty was installed won't see it until restarted.

To skip in a genuine emergency: `git commit --no-verify` — but fix
what it would have caught before the next real commit, don't make a
habit of it.

**CI (`.github/workflows/`) runs the exact same checks as the local
pre-commit hook — never a separate copy of them.** These two verification
workflows run on GitHub-hosted runners only (never self-hosted — GitHub
explicitly warns against self-hosted runners on public repos, since any
fork PR can run arbitrary code on one, including reading secrets):
- **`checks.yml`** (badge in `README.md`) — installs `uv`+`qlty`, then
  `uv run pre-commit run --all-files` against the committed
  `.pre-commit-config.yaml` — literally the same hooks the local git
  hook runs, not a second implementation of them. Deliberately not the
  `pre-commit/action` marketplace action: it does its own `pip install
  pre-commit` into whatever venv is active, but a `uv`-managed venv has
  no `pip` in it — `pre-commit` is already a `uv` dev dependency here.
- **`tests.yml`** (badge in `README.md`) — `uv run pytest -q`. No service
  containers: every test fixture uses an in-memory SQLite engine.

Deployment is not automated by a workflow in this repo — deploying your
own instance (building/pulling the image and running `docker compose up
-d`) is up to you. See `README.md`'s Deployment section for a
step-by-step guide.

If a local pre-commit pass ever disagrees with `checks.yml`'s result on
the same commit, that's a bug in the CI setup (a version/config drift
between local and CI) worth fixing directly, not something to route
around by re-running or ignoring.

### LSP access (cclsp)

A `cclsp` MCP server (github.com/ktnyt/cclsp) is registered at
**project** scope via the committed `.mcp.json`, so it's available in
any Claude Code session opened in this repo, on any machine — not tied
to one machine's local config. It gives real LSP-backed
go-to-definition/find-references/hover instead of Grep text search.
Config is the committed `cclsp.json` at the repo root, pointing
`.py`/`.pyi` files at `uv run ty server` — `ty`'s own built-in LSP mode,
already a project dependency, so this adds no new Python tooling and its
diagnostics match `ty check`/CI exactly. Since `.mcp.json` is
repo-committed, Claude Code requires a one-time approval per machine the
first time a session opens here (`claude mcp list` shows "Pending
approval" until then) — a deliberate trust gate, not a bug.

## Logging

Uses **loguru** (`from loguru import logger`) everywhere, not stdlib
`logging` directly — set up once in `logging_config.py`, which also
redirects python-telegram-bot's own stdlib logging into the same sink (the
standard `InterceptHandler` recipe) so everything ends up in one place with
one format. Sink level defaults to `INFO`, overridable via the `LOG_LEVEL`
env var (`.env`) — `docker compose logs bot` should be readable by default,
not a DEBUG firehose.

**Log generously, but pick the right level:**

| Level | Use for | Example in this codebase |
|---|---|---|
| `TRACE` | Fires on essentially every update | the trickle handler's per-message check |
| `DEBUG` | Routine/internal detail, expected outcomes | pity counter values before a roll, a rejected `/daily` (too soon), command entry logs |
| `INFO` | A meaningful game/economic event | a pull's outcome, a grant, a new player, roster ingestion summary |
| `WARNING` | Recoverable anomaly, rejected action | insufficient balance, non-admin hitting an admin command, AniList rate-limit retry |
| `ERROR` | Something is actually broken | empty rarity pool (roster gap), AniList retries exhausted |

When adding a new log call, ask "would this be useful in production at
`LOG_LEVEL=INFO`, or is it something I'd only want while debugging?" — the
former is `INFO`+, the latter is `DEBUG`/`TRACE`. Don't log routine,
frequent, expected-outcome events at `INFO` — that's what turns `INFO` logs
into background noise nobody reads.

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

The first three (not `pytest`) plus `qlty smells` also run automatically
as a git pre-commit hook (see Tooling above) — committing re-verifies
them regardless, but running them yourself first means the commit
doesn't just fail on the first attempt.

## Branching & workflow

`develop` is the integration branch — every task branch gets PR'd there.
`master` is the GitHub **default** branch (what visitors see, what gets
cloned) and release-only: it only moves via a deliberate `develop` →
`master` PR when you actually want to cut a release, and that push is
what triggers `release.yml` (see "Verifying changes" above). Both
branches require a PR — no direct pushes, no force pushes, no deletions.

Because `master`, not `develop`, is the GitHub default, **a new PR's
base branch defaults to `master` and does not auto-select `develop`** —
GitHub ties "default branch" and "default PR base branch" to the same
setting, so this can't be fixed with a repo setting alone. Always target
`develop` explicitly: `gh pr create --base develop …`, or pick `develop`
from the base-branch dropdown in the GitHub UI.

The standard flow for any task:

1. Make sure it has a GitHub issue (see "Task tracking" below).
2. Branch from `develop` (not `master`) as `<type>/<issue#>-<slug>` —
   `<type>` matches the Conventional Commits type (`feat/`, `fix/`,
   `chore/`, `docs/`, …), e.g. `feat/126-version-command`.
3. Work and commit there, then open a PR explicitly targeting `develop`
   (see above — it won't be preselected).

Releasing is its own separate step, not something that happens as a side
effect of a task PR: open a `develop` → `master` PR and merge it when
you're ready to cut a version. That merge leaves a commit on `master`
that `develop` doesn't have — `sync-develop.yml` opens a follow-up
`master` → `develop` PR automatically; merge that one too before
starting new task branches, so they fork from a `develop` that's
actually caught up.

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
> `PROXY_HOST`, `PROXY_PORT`, `<user>`, `<pass>`, or a host alias with no
> FQDN) and point at your own private ops notes for real values —
> never write them out, even "temporarily" or "just to explain the bug."
> Everything in this repo — commits, issues, PRs, history — is public and
> indexed by anyone/anything crawling GitHub; there is no private fallback
> to catch a slip.

## Commit messages: Conventional Commits

This repo uses [Conventional Commits](https://www.conventionalcommits.org/)
— required by `python-semantic-release`
(`.github/workflows/release.yml`), which uses the commit type to decide
the version bump.

Format: `<type>(<optional scope>): <description>`

- `feat: ...` — a new capability. Triggers a **minor** version bump.
- `fix: ...` — a bug fix. Triggers a **patch** version bump.
- `feat!: ...` or a `BREAKING CHANGE: ...` footer — triggers a **major**
  bump. Rare for a bot this size; use deliberately.
- `chore:`, `docs:`, `refactor:`, `test:`, `style:`, `ci:`, `build:` — no
  version bump. Use for anything that isn't a user-facing fix or feature.

One logical change per commit, same as always — this doesn't change that,
it just adds a prefix that says what kind of change it is.

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
