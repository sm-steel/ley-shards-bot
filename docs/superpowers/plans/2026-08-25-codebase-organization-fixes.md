# Codebase Organization Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 5 file/function-placement findings from the joint codebase
review (issue #58), and document the resulting placement rules in
`ARCHITECTURE.md` so future changes land in the right file the first time.

**Architecture:** Pure relocation + import-path updates — no behavior
changes. Each move gets its own task so the diff stays reviewable and the
test suite stays green after every single task, not just at the end. Two
new shared-code homes get created: `commands/helpers/` (Telegram-aware
plumbing that isn't itself a command handler) and `services/pagination.py`
(a domain-agnostic sibling to `services/players.py`).

**Tech Stack:** Python 3.11+, `uv`, `pytest`/`pytest-asyncio` (auto mode),
`ruff`, `ty`, `qlty`. No new dependencies.

**Spec:** This plan *is* the spec — it implements the 5 findings agreed on
in the joint review recorded in issue
[#58](https://github.com/sm-steel/ley-shards-bot/issues/58) and the
codebase map artifact linked from it. No separate spec doc exists.

## Global Constraints

- Every task must leave `uv run pytest`, `uv run ruff check .`,
  `uv run ruff format .`, `uv run ty check`, and `qlty smells --all
  --no-snippets` clean before it's considered done (see `CLAUDE.md`'s
  Verifying Changes section) — these also run as the pre-commit hook, so a
  task that skips this just fails on commit instead.
- No behavior change anywhere in this plan. Every moved function keeps its
  exact signature and body; only its import path (and, for `_is_admin`/
  `_resolve_target`, its public name — see Tasks 2–3) changes.
- Prefer `git mv` for pure relocations so file history follows the code.
- Public names dropped their leading underscore only where they're now
  actually imported from another module (`is_admin`, `resolve_target`,
  `RARITY_STARS`). Names that stay private to their new file keep the
  underscore (`_replied_to_user_id`, `_replied_to_username`,
  `_username_from_args` inside the new `targeting.py`).
- Branch once for the whole plan (`git checkout -b codebase-organization-fixes`)
  before Task 1; commit after every task, same as this repo's normal
  per-issue workflow. Don't open the PR until Task 8 is committed — the
  reviewer should see the fixes and the doc that explains them together.

---

## File Structure

```
src/ley_shards_bot/
  commands/
    helpers/                 # NEW — Telegram-aware plumbing, not commands
      __init__.py            # NEW, empty
      menu.py                # MOVED from commands/menu.py, unchanged
      scoping.py              # MOVED from commands/scoping.py, + is_admin (moved from economy.py)
      targeting.py            # NEW — resolve_target + its 3 private helpers (moved from economy.py)
      formatting.py            # NEW — RARITY_STARS (deduped from gacha.py + collection.py)
    gacha.py                  # MODIFIED — imports updated, local _RARITY_STARS/PlayerRef removed
    collection.py              # MODIFIED — imports updated, local _RARITY_STARS removed
    economy.py                # MODIFIED — _is_admin/_replied_to_*/_username_from_args/_resolve_target removed
    help.py                   # MODIFIED — imports is_admin instead of reimplementing it
  services/
    players.py                 # MODIFIED — gains PlayerRef
    gacha.py                    # MODIFIED — PlayerRef removed, imported from services.players instead
    collection.py                # MODIFIED — Page/paginate/PAGE_SIZE removed
    pagination.py                 # NEW — Page, paginate, PAGE_SIZE (moved from services/collection.py)
  app.py                          # MODIFIED — import path for menu

tests/
  commands/
    helpers/                     # NEW
      __init__.py                # NEW, empty
      test_scoping.py             # MOVED from tests/commands/test_scoping.py, + is_admin tests
      test_targeting.py            # NEW — direct tests for resolve_target
  services/
    test_gacha.py                  # MODIFIED — PlayerRef import path updated
    test_collection.py              # MODIFIED — TestPaginate class removed
    test_pagination.py               # NEW — TestPaginate moved here verbatim

CLAUDE.md                           # MODIFIED — stale tests/ claim fixed, commands/helpers/ noted
ARCHITECTURE.md                     # MODIFIED — Component boundaries expanded, new process-rule
                                     # subsection, Testing strategy bullet fixed
```

---

### Task 1: Create `commands/helpers/`, move `menu.py` + `scoping.py` into it

**Files:**
- Create: `src/ley_shards_bot/commands/helpers/__init__.py`
- Move: `src/ley_shards_bot/commands/menu.py` → `src/ley_shards_bot/commands/helpers/menu.py`
- Move: `src/ley_shards_bot/commands/scoping.py` → `src/ley_shards_bot/commands/helpers/scoping.py`
- Modify: `src/ley_shards_bot/app.py:32`
- Modify: `src/ley_shards_bot/commands/help.py:16`
- Modify: `src/ley_shards_bot/commands/gacha.py:20`
- Modify: `src/ley_shards_bot/commands/collection.py:18`
- Modify: `src/ley_shards_bot/commands/economy.py:24`
- Move: `tests/commands/test_scoping.py` → `tests/commands/helpers/test_scoping.py`
- Create: `tests/commands/helpers/__init__.py`

**Interfaces:**
- Produces: `ley_shards_bot.commands.helpers.menu.{PLAYER_COMMANDS, ADMIN_COMMANDS}`,
  `ley_shards_bot.commands.helpers.scoping.{in_private_chat, NOT_IN_DM_MESSAGE}` —
  same names, same signatures, new import path. Tasks 2–4 build on this
  package existing.

- [ ] **Step 1: Create the package and move the two files**

```bash
mkdir -p src/ley_shards_bot/commands/helpers
touch src/ley_shards_bot/commands/helpers/__init__.py
git mv src/ley_shards_bot/commands/menu.py src/ley_shards_bot/commands/helpers/menu.py
git mv src/ley_shards_bot/commands/scoping.py src/ley_shards_bot/commands/helpers/scoping.py
mkdir -p tests/commands/helpers
touch tests/commands/helpers/__init__.py
git mv tests/commands/test_scoping.py tests/commands/helpers/test_scoping.py
```

Neither moved file needs any content change in this step — `menu.py` and
`scoping.py` are unchanged, only their path moved.

- [ ] **Step 2: Update every importer's path**

In `src/ley_shards_bot/app.py:32`, change:

```python
from ley_shards_bot.commands.menu import ADMIN_COMMANDS, PLAYER_COMMANDS
```

to:

```python
from ley_shards_bot.commands.helpers.menu import ADMIN_COMMANDS, PLAYER_COMMANDS
```

In `src/ley_shards_bot/commands/help.py:16`, change:

```python
from ley_shards_bot.commands.menu import ADMIN_COMMANDS, PLAYER_COMMANDS
```

to:

```python
from ley_shards_bot.commands.helpers.menu import ADMIN_COMMANDS, PLAYER_COMMANDS
```

Also update `help.py`'s module docstring (line 4), which currently says
`Descriptions come from commands/menu.py` — change to
`commands/helpers/menu.py`.

In `src/ley_shards_bot/commands/gacha.py:20`, change:

```python
from ley_shards_bot.commands.scoping import NOT_IN_DM_MESSAGE, in_private_chat
```

to:

```python
from ley_shards_bot.commands.helpers.scoping import NOT_IN_DM_MESSAGE, in_private_chat
```

Make the identical change in `src/ley_shards_bot/commands/collection.py:18`
and `src/ley_shards_bot/commands/economy.py:24`.

In `tests/commands/helpers/test_scoping.py`, change:

```python
from ley_shards_bot.commands.scoping import in_private_chat
```

to:

```python
from ley_shards_bot.commands.helpers.scoping import in_private_chat
```

- [ ] **Step 3: Run the full suite and confirm nothing broke**

Run: `uv run pytest -q`
Expected: all 160 tests still pass (this is a pure path move — nothing
here should fail; if something does, an importer was missed — search with
`grep -rn "commands.menu\|commands.scoping\|commands import menu\|commands import scoping" src/ tests/`
excluding the new `helpers/` paths themselves).

- [ ] **Step 4: Verify + commit**

```bash
uv run ruff check .
uv run ruff format .
uv run ty check
qlty smells --all --no-snippets
git add -A
git commit -m "Move menu.py and scoping.py into a new commands/helpers/ package

Neither one registers a CommandHandler — they're shared Telegram-aware
plumbing every command handler pulls from, not commands themselves.
Splitting them out keeps the flat commands/ listing to actual handlers.
Pure move, no behavior change.

Part of #58"
```

---

### Task 2: Add `is_admin` to `commands/helpers/scoping.py`, remove the duplicate in `help.py`

**Files:**
- Modify: `src/ley_shards_bot/commands/helpers/scoping.py`
- Modify: `src/ley_shards_bot/commands/economy.py:36-42, 161, 213`
- Modify: `src/ley_shards_bot/commands/help.py:31-36`
- Modify: `tests/commands/helpers/test_scoping.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `ley_shards_bot.commands.helpers.scoping.is_admin(update, context) -> bool`
  — same behavior as the old `commands.economy._is_admin`, public name.
  Task 3 doesn't depend on this, but both live in the same file by the end
  of this task.

- [ ] **Step 1: Write the failing test for `is_admin` in its new home**

Append to `tests/commands/helpers/test_scoping.py`:

```python
from types import SimpleNamespace
from unittest.mock import MagicMock

from ley_shards_bot.commands.helpers.scoping import in_private_chat, is_admin


def _make_admin_check_update(*, user_id: int = 1) -> MagicMock:
    update = MagicMock()
    update.effective_user.id = user_id
    return update


def _make_admin_check_context(*, admin_ids: frozenset[int]) -> MagicMock:
    context = MagicMock()
    context.bot_data = {"config": SimpleNamespace(admin_user_ids=admin_ids)}
    return context


class TestIsAdmin:
    def test_true_for_a_configured_admin(self):
        update = _make_admin_check_update(user_id=1)
        context = _make_admin_check_context(admin_ids=frozenset({1}))

        assert is_admin(update, context) is True

    def test_false_for_a_non_admin(self):
        update = _make_admin_check_update(user_id=2)
        context = _make_admin_check_context(admin_ids=frozenset({1}))

        assert is_admin(update, context) is False

    def test_false_when_theres_no_user(self):
        update = _make_admin_check_update(user_id=1)
        update.effective_user = None
        context = _make_admin_check_context(admin_ids=frozenset({1}))

        assert is_admin(update, context) is False
```

(This duplicates the existing `in_private_chat` import already at the top
of the file with the new `is_admin` name added — replace the existing
`from ley_shards_bot.commands.helpers.scoping import in_private_chat` line
at the top of the file with the combined import shown above instead of
adding a second import line.)

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/commands/helpers/test_scoping.py::TestIsAdmin -v`
Expected: FAIL — `ImportError: cannot import name 'is_admin'` (it doesn't
exist in `scoping.py` yet).

- [ ] **Step 3: Add `is_admin` to `scoping.py`**

`src/ley_shards_bot/commands/helpers/scoping.py` currently ends after
`in_private_chat`. Add the following, which needs two new imports at the
top of the file (`TYPE_CHECKING` is already imported; `logger` is not):

```python
from loguru import logger
```

(add this alongside the existing `from typing import TYPE_CHECKING` line)

Then append at the end of the file:

```python
def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    config = context.bot_data["config"]
    user = update.effective_user
    admin = user is not None and user.id in config.admin_user_ids
    if user is not None and not admin:
        logger.warning("Non-admin {} attempted an admin-only command", user.id)
    return admin
```

`Update` is already imported under `TYPE_CHECKING` in this file; `is_admin`
needs it (and `ContextTypes`) available at runtime too, since it's a
regular function, not just a type hint. Change the top of the file from:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telegram import Update
```

to:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes
```

`ContextTypes` stays `TYPE_CHECKING`-only (it's only used in the type
hint, same as `Update` already was) — only `logger` needs a real runtime
import.

- [ ] **Step 4: Run the new tests, verify they pass**

Run: `uv run pytest tests/commands/helpers/test_scoping.py -v`
Expected: PASS, all of `TestInPrivateChat` and `TestIsAdmin`.

- [ ] **Step 5: Remove `_is_admin` from `economy.py`, use the shared one instead**

In `src/ley_shards_bot/commands/economy.py`, delete the whole
`_is_admin` function (lines 36–42):

```python
def _is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    config = context.bot_data["config"]
    user = update.effective_user
    is_admin = user is not None and user.id in config.admin_user_ids
    if user is not None and not is_admin:
        logger.warning("Non-admin {} attempted an admin-only economy command", user.id)
    return is_admin
```

Change the import at line 24 from:

```python
from ley_shards_bot.commands.helpers.scoping import NOT_IN_DM_MESSAGE, in_private_chat
```

to:

```python
from ley_shards_bot.commands.helpers.scoping import NOT_IN_DM_MESSAGE, in_private_chat, is_admin
```

Update the two call sites — line 161 (`award_guess_command`) and line 213
(`_execute_amount_command`) — from `if not _is_admin(update, context):` to
`if not is_admin(update, context):` (both occurrences).

- [ ] **Step 6: Remove the duplicate inline check from `help.py`**

In `src/ley_shards_bot/commands/help.py`, change the import at line 16
from:

```python
from ley_shards_bot.commands.helpers.menu import ADMIN_COMMANDS, PLAYER_COMMANDS
```

to:

```python
from ley_shards_bot.commands.helpers.menu import ADMIN_COMMANDS, PLAYER_COMMANDS
from ley_shards_bot.commands.helpers.scoping import is_admin
```

Then in `help_command` (lines 31–36), change:

```python
    config = context.bot_data["config"]
    user = update.effective_user
    is_admin = user is not None and user.id in config.admin_user_ids

    sections = [_format_commands(PLAYER_COMMANDS)]
    if is_admin:
        sections.append(_format_commands(ADMIN_COMMANDS))
```

to:

```python
    sections = [_format_commands(PLAYER_COMMANDS)]
    if is_admin(update, context):
        sections.append(_format_commands(ADMIN_COMMANDS))
```

(The local variable named `is_admin` shadowed the function name we're
about to import, which is exactly why it was reimplemented inline instead
of imported in the first place — removing the local variable removes the
naming collision too.)

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest -q`
Expected: all tests pass — `tests/commands/test_economy.py`'s existing
non-admin-rejection tests (`TestAwardGuessCommand::test_non_admin_is_rejected`,
`TestGrantCommand::test_non_admin_is_rejected`,
`TestRevokeCommand::test_non_admin_is_rejected`) and `tests/commands/test_help.py`'s
admin-visibility tests now exercise the shared `is_admin` transitively —
they were written against behavior, not against `_is_admin` directly, so
they need no changes themselves.

- [ ] **Step 8: Verify + commit**

```bash
uv run ruff check .
uv run ruff format .
uv run ty check
qlty smells --all --no-snippets
git add -A
git commit -m "Extract is_admin into commands/helpers/scoping.py, dedupe help.py

_is_admin lived in economy.py only because /grant/revoke/award_guess
happened to be the first admin commands written — nothing about it is
economy logic, it's a permission check, same category as
in_private_chat already living in scoping.py. help.py needed the exact
same check and, unable to import something economy-flavored for a
non-economy reason, had reimplemented it inline instead.

Part of #58"
```

---

### Task 3: Extract target-resolution into `commands/helpers/targeting.py`

**Files:**
- Create: `src/ley_shards_bot/commands/helpers/targeting.py`
- Create: `tests/commands/helpers/test_targeting.py`
- Modify: `src/ley_shards_bot/commands/economy.py`

**Interfaces:**
- Consumes: `ley_shards_bot.services.players.find_player_by_username(session, username) -> Player | None`
  (already exists, unchanged).
- Produces: `ley_shards_bot.commands.helpers.targeting.resolve_target(update, session, args, *, reply_hint) -> tuple[int, str | None, list[str]] | None`
  — same behavior as the old `commands.economy._resolve_target`, public
  name, moved wholesale including its 3 private helper functions.

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/helpers/test_targeting.py`:

```python
"""Tests for resolve_target: admin-style @username-or-reply targeting,
shared by any command that needs to resolve which player it's about (today
that's /grant, /revoke, /award_guess in commands/economy.py — nothing
about resolve_target itself is admin-specific, see issue #58).
"""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ley_shards_bot.commands.helpers.targeting import resolve_target
from ley_shards_bot.models import Base, Player

REPLY_HINT = "Reply to the target player's message, or use @username."


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _make_update(
    *, replied_user_id: int | None = None, replied_username: str | None = None
) -> MagicMock:
    update = MagicMock()
    message = MagicMock()
    message.reply_text = AsyncMock()
    if replied_user_id is not None:
        message.reply_to_message.from_user.id = replied_user_id
        message.reply_to_message.from_user.username = replied_username
    else:
        message.reply_to_message = None
    update.effective_message = message
    return update


class TestResolveTarget:
    async def test_resolves_by_username_when_first_arg_is_an_at_mention(self, session):
        session.add(Player(telegram_user_id=5, username="aleksey"))
        session.commit()
        update = _make_update()

        result = await resolve_target(update, session, ["@aleksey", "100"], reply_hint=REPLY_HINT)

        assert result == (5, "aleksey", ["100"])

    async def test_unknown_username_replies_and_returns_none(self, session):
        update = _make_update()

        result = await resolve_target(update, session, ["@nobody", "100"], reply_hint=REPLY_HINT)

        assert result is None
        update.effective_message.reply_text.assert_awaited_once()
        (text,), _ = update.effective_message.reply_text.call_args
        assert "@nobody" in text

    async def test_falls_back_to_reply_target_when_no_username_arg(self, session):
        update = _make_update(replied_user_id=7, replied_username="mira")

        result = await resolve_target(update, session, ["100"], reply_hint=REPLY_HINT)

        assert result == (7, "mira", ["100"])

    async def test_no_username_and_no_reply_shows_the_hint(self, session):
        update = _make_update()

        result = await resolve_target(update, session, [], reply_hint=REPLY_HINT)

        assert result is None
        (text,), _ = update.effective_message.reply_text.call_args
        assert text == REPLY_HINT
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/commands/helpers/test_targeting.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ley_shards_bot.commands.helpers.targeting'`.

- [ ] **Step 3: Create `targeting.py` with the moved code**

Create `src/ley_shards_bot/commands/helpers/targeting.py`:

```python
"""Target resolution for commands that act on another player:
@username-first, falling back to reply-to-message targeting.

Nothing here checks permissions — it only answers "which player is this
command about." It happens to only be used by admin commands today
(/grant, /revoke, /award_guess in commands/economy.py) but that's a fact
about today's callers, not about this module — see issue #58.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ley_shards_bot.services.players import find_player_by_username

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from telegram import Update


def _replied_to_user_id(update: Update) -> int | None:
    """The user a reply-based command targets — whoever sent the message
    being replied to. None if this command wasn't used as a reply."""
    message = update.effective_message
    if message is None or message.reply_to_message is None:
        return None
    replied_user = message.reply_to_message.from_user
    return replied_user.id if replied_user is not None else None


def _replied_to_username(update: Update) -> str | None:
    """The @username (if any) of a reply-based command's target —
    captured the same way as the acting user's own, so a player can become
    @username-targetable just by being replied to, even if they've never
    used the bot themselves. See issue #12."""
    message = update.effective_message
    if message is None or message.reply_to_message is None:
        return None
    replied_user = message.reply_to_message.from_user
    return replied_user.username if replied_user is not None else None


def _username_from_args(args: list[str]) -> str | None:
    """The @username (without the @) a command was targeted at via its
    first argument, e.g. `/grant @aleksey 500` -> "aleksey". None if there
    are no args or the first one isn't an @username — in which case the
    caller falls back to reply-based targeting. See issue #13."""
    if not args or not args[0].startswith("@"):
        return None
    return args[0][1:]


async def resolve_target(
    update: Update,
    session: Session,
    args: list[str],
    *,
    reply_hint: str,
) -> tuple[int, str | None, list[str]] | None:
    """Resolve a command's target player, trying `@username` (via the
    first arg) before falling back to reply-to-message targeting — see
    issue #13. On success, returns `(target_id, username_to_capture,
    remaining_args)`, where `remaining_args` has the leading `@username`
    consumed if there was one (so callers parse e.g. an amount from it
    instead of from `args` directly). On failure, sends a friendly reply
    itself (unknown username, or no target at all) and returns None.

    Doesn't take `message` separately — every caller has already
    null-checked `update.effective_message` before calling this, so it's
    re-derived here rather than passed as a redundant parameter (see
    issue #48).
    """
    message = update.effective_message
    if message is None:
        return None

    target_username = _username_from_args(args)
    if target_username is not None:
        target_player = find_player_by_username(session, target_username)
        if target_player is None:
            await message.reply_text(f"Haven't seen @{target_username} use the bot yet.")
            return None
        return target_player.telegram_user_id, target_player.username, args[1:]

    target_id = _replied_to_user_id(update)
    if target_id is None:
        await message.reply_text(reply_hint)
        return None
    return target_id, _replied_to_username(update), args
```

- [ ] **Step 4: Run the new tests, verify they pass**

Run: `uv run pytest tests/commands/helpers/test_targeting.py -v`
Expected: PASS, all 4 tests.

- [ ] **Step 5: Remove the moved code from `economy.py`, import `resolve_target` instead**

In `src/ley_shards_bot/commands/economy.py`, delete the four functions
`_replied_to_user_id`, `_replied_to_username`, `_username_from_args`, and
`_resolve_target` in their entirety (this is everything between the now
already-removed `_is_admin` and `daily_command` — i.e. what's currently
lines 45–114).

By this point (after Task 2), `economy.py`'s import block reads:

```python
from ley_shards_bot.commands.helpers.scoping import NOT_IN_DM_MESSAGE, in_private_chat, is_admin
from ley_shards_bot.db import session_scope
from ley_shards_bot.services import economy
from ley_shards_bot.services.players import find_player_by_username
from ley_shards_bot.time_utils import game_day, utc_now
```

`ruff`'s import-sort rule sorts `commands.helpers.targeting` right after
`commands.helpers.scoping` (`scoping` < `targeting`, both before `db`).
The now-unused `from ley_shards_bot.services.players import
find_player_by_username` import is also removed here — `targeting.py` owns
that call now, `economy.py` no longer calls it directly. Result:

```python
from ley_shards_bot.commands.helpers.scoping import NOT_IN_DM_MESSAGE, in_private_chat, is_admin
from ley_shards_bot.commands.helpers.targeting import resolve_target
from ley_shards_bot.db import session_scope
from ley_shards_bot.services import economy
from ley_shards_bot.time_utils import game_day, utc_now
```

Update the two call sites: `await _resolve_target(` becomes
`await resolve_target(` in both `award_guess_command` and
`_execute_amount_command`.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q`
Expected: all tests pass. `tests/commands/test_economy.py`'s existing
username-targeting and reply-targeting tests
(`test_admin_awards_by_username`, `test_unknown_username_reports_friendly_error`,
etc., across `TestAwardGuessCommand`/`TestGrantCommand`/`TestRevokeCommand`)
exercise `resolve_target` transitively through the command handlers and
need no changes — they were never written against `_resolve_target`
directly.

- [ ] **Step 7: Verify + commit**

```bash
uv run ruff check .
uv run ruff format .
uv run ty check
qlty smells --all --no-snippets
git add -A
git commit -m "Extract target resolution into commands/helpers/targeting.py

_resolve_target and its 3 private helpers touch no config, no admin
check, nothing economy-specific — they resolve which player a command
is about via @username or reply-to-message, and would work identically
for a non-admin command that takes a target. They only lived in
economy.py because /grant/revoke/award_guess were the first callers.

Part of #58"
```

---

### Task 4: Dedupe `_RARITY_STARS` into `commands/helpers/formatting.py`

**Files:**
- Create: `src/ley_shards_bot/commands/helpers/formatting.py`
- Modify: `src/ley_shards_bot/commands/gacha.py:31-37, 53, 63, 86`
- Modify: `src/ley_shards_bot/commands/collection.py:23-27, 56`

**Interfaces:**
- Produces: `ley_shards_bot.commands.helpers.formatting.RARITY_STARS: dict[Rarity, str]`
  — identical mapping, public name.

- [ ] **Step 1: Create `formatting.py`**

Create `src/ley_shards_bot/commands/helpers/formatting.py`:

```python
"""Shared Telegram-facing formatting constants, used by more than one
command module — kept here instead of re-literaled in each one (was
duplicated verbatim between gacha.py and collection.py, see issue #58).
"""

from __future__ import annotations

from ley_shards_bot.models import Rarity

RARITY_STARS = {
    Rarity.THREE_STAR: "★★★",
    Rarity.FOUR_STAR: "★★★★",
    Rarity.FIVE_STAR: "★★★★★",
}
```

- [ ] **Step 2: Use it from `gacha.py`**

In `src/ley_shards_bot/commands/gacha.py`, delete the local definition
(lines 31–37):

```python
_RARITY_STARS = {
    Rarity.THREE_STAR: "★★★",
    Rarity.FOUR_STAR: "★★★★",
    Rarity.FIVE_STAR: "★★★★★",
}
```

Keep the `from ley_shards_bot.models import Rarity` import at line 22 —
`_HIGHLIGHT_RARITIES = frozenset({Rarity.FOUR_STAR, Rarity.FIVE_STAR})`
further down the file still needs it, this file does not lose the import.

`ruff`'s import-sort rule (`I`, enabled in `pyproject.toml`) is strict
about ordering, so place the new import precisely: it sorts *before* the
existing `commands.helpers.scoping` import (`formatting` < `scoping`), as
the new first import line in the file:

```python
from ley_shards_bot.commands.helpers.formatting import RARITY_STARS
from ley_shards_bot.commands.helpers.scoping import NOT_IN_DM_MESSAGE, in_private_chat
```

Replace all three usages: `_RARITY_STARS[outcome.rarity]` (lines 53, 63,
86) becomes `RARITY_STARS[outcome.rarity]`.

- [ ] **Step 3: Use it from `collection.py`**

In `src/ley_shards_bot/commands/collection.py`, delete the local
definition (lines 23–27):

```python
_RARITY_STARS = {
    Rarity.THREE_STAR: "★★★",
    Rarity.FOUR_STAR: "★★★★",
    Rarity.FIVE_STAR: "★★★★★",
}
```

The `from ley_shards_bot.models import Rarity` import at line 20 in this
file has no other use in `collection.py` once this dict is gone (verified —
`Rarity` appears nowhere else in the file) — remove it entirely. Add the
new import sorting *before* the existing `commands.helpers.scoping` import
(`formatting` < `scoping`), as the new first import line in the file:

```python
from ley_shards_bot.commands.helpers.formatting import RARITY_STARS
from ley_shards_bot.commands.helpers.scoping import NOT_IN_DM_MESSAGE, in_private_chat
```

Replace the one usage at line 56: `_RARITY_STARS[owned.character.rarity]`
becomes `RARITY_STARS[owned.character.rarity]`.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: all tests pass — every existing test that asserts star strings
appear in a reply (`tests/commands/test_gacha.py`,
`tests/commands/test_collection.py`) exercises `RARITY_STARS`
transitively and needs no changes.

- [ ] **Step 5: Verify + commit**

```bash
uv run ruff check .
uv run ruff format .
uv run ty check
qlty smells --all --no-snippets
git add -A
git commit -m "Dedupe _RARITY_STARS into commands/helpers/formatting.py

The exact same dict was typed out independently in both gacha.py and
collection.py — never imported from one. Third consumer (/banners,
Phase 1.1) would have made it three copies instead of a shared constant.

Part of #58"
```

---

### Task 5: Move `PlayerRef` from `services/gacha.py` to `services/players.py`

**Files:**
- Modify: `src/ley_shards_bot/services/players.py`
- Modify: `src/ley_shards_bot/services/gacha.py:19, 82-89`
- Modify: `src/ley_shards_bot/commands/gacha.py:23, 103, 137, 160`
- Modify: `tests/services/test_gacha.py:34`

**Interfaces:**
- Produces: `ley_shards_bot.services.players.PlayerRef` — identical
  dataclass (`telegram_user_id: int`, `username: str | None = None`), new
  home. `services/gacha.py`'s `pull_single`/`pull_ten` keep taking a
  `PlayerRef` parameter — only where the type comes from changes.

- [ ] **Step 1: Add `PlayerRef` to `services/players.py`**

`src/ley_shards_bot/services/players.py` currently starts:

```python
"""Shared player lookup — used by economy.py and gacha.py alike, so it
lives in its own module rather than being owned by either.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import func, select

from ley_shards_bot.models import Player

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
```

Change it to:

```python
"""Shared player lookup — used by economy.py and gacha.py alike, so it
lives in its own module rather than being owned by either. PlayerRef
follows the same reasoning: a player's Telegram identity (id + the
opportunistically captured @username) isn't gacha-specific, it just
started out defined in services/gacha.py because pull_single/pull_ten
were its first consumer — see issue #58.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import func, select

from ley_shards_bot.models import Player

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass(frozen=True)
class PlayerRef:
    """A player's Telegram identity: id plus the opportunistically
    captured @username (see #12) — bundled together because callers that
    need "who is this" treat it as one concept, not two independent
    parameters. See issue #49."""

    telegram_user_id: int
    username: str | None = None
```

(The dataclass goes right after the imports, before `get_or_create_player`.)

- [ ] **Step 2: Remove `PlayerRef` from `services/gacha.py`, import it instead**

In `src/ley_shards_bot/services/gacha.py`, delete the class (currently
lines 81–89):

```python
@dataclass(frozen=True)
class PlayerRef:
    """A player's Telegram identity: id plus the opportunistically
    captured @username (see #12) — bundled together because pull_single/
    pull_ten treat "who's pulling" as one concept, not two independent
    parameters. See issue #49."""

    telegram_user_id: int
    username: str | None = None
```

Change line 34 from:

```python
from ley_shards_bot.services.players import get_or_create_player
```

to:

```python
from ley_shards_bot.services.players import PlayerRef, get_or_create_player
```

`pull_single`/`pull_ten`'s signatures (`player: PlayerRef`) don't change —
only where the name resolves from.

- [ ] **Step 3: Update `commands/gacha.py`**

In `src/ley_shards_bot/commands/gacha.py`, change line 23 from:

```python
from ley_shards_bot.services import gacha
```

to:

```python
from ley_shards_bot.services import gacha
from ley_shards_bot.services.players import PlayerRef
```

Update the three usages: line 103's type hint `player: gacha.PlayerRef,`
becomes `player: PlayerRef,`; the two construction call sites at lines 137
and 160, `gacha.PlayerRef(user.id, username=user.username)`, both become
`PlayerRef(user.id, username=user.username)`.

- [ ] **Step 4: Update `tests/services/test_gacha.py`**

Line 34 currently imports `PlayerRef` as one of many names from
`ley_shards_bot.services.gacha`:

```python
from ley_shards_bot.models import (
    Banner,
    BannerType,
    Base,
    Character,
    PityState,
    Player,
    PlayerCharacter,
    Rarity,
)
from ley_shards_bot.services.gacha import (
    ECHOES_PER_DUPLICATE,
    FIVE_STAR_HARD_PITY,
    FOUR_STAR_HARD_PITY,
    PULL_COST_LEY_SHARDS,
    TEN_PULL_COST_LEY_SHARDS,
    TEN_PULL_SIZE,
    InsufficientLeyShardsError,
    PlayerRef,
    five_star_probability,
    get_or_create_standard_banner,
    next_pity_counts,
    pull_single,
    pull_ten,
    resolve_event_five_star,
    roll_rarity,
)
```

Remove `PlayerRef,` from the `services.gacha` import block and add a
separate import line for it:

```python
from ley_shards_bot.services.gacha import (
    ECHOES_PER_DUPLICATE,
    FIVE_STAR_HARD_PITY,
    FOUR_STAR_HARD_PITY,
    PULL_COST_LEY_SHARDS,
    TEN_PULL_COST_LEY_SHARDS,
    TEN_PULL_SIZE,
    InsufficientLeyShardsError,
    five_star_probability,
    get_or_create_standard_banner,
    next_pity_counts,
    pull_single,
    pull_ten,
    resolve_event_five_star,
    roll_rarity,
)
from ley_shards_bot.services.players import PlayerRef
```

Every other reference to `PlayerRef(...)` in this file (there are 15,
across the pull-cost/pity/rate-up test classes) stays exactly as written —
only the import line changes, `PlayerRef` is still the name in scope.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: all tests pass.

- [ ] **Step 6: Verify + commit**

```bash
uv run ruff check .
uv run ruff format .
uv run ty check
qlty smells --all --no-snippets
git add -A
git commit -m "Move PlayerRef from services/gacha.py to services/players.py

PlayerRef is a two-field \"player's Telegram identity\" dataclass —
nothing about pity, rarity, or pull mechanics is in it. It only lived
in gacha.py because pull_single/pull_ten were its first consumer.
services/players.py's own docstring already states the exact reasoning
that should have put it there from the start.

Part of #58"
```

---

### Task 6: Move `Page`/`paginate`/`PAGE_SIZE` to `services/pagination.py`

**Files:**
- Create: `src/ley_shards_bot/services/pagination.py`
- Modify: `src/ley_shards_bot/services/collection.py`
- Modify: `src/ley_shards_bot/commands/collection.py:21`
- Modify: `tests/services/test_collection.py`
- Create: `tests/services/test_pagination.py`

**Interfaces:**
- Produces: `ley_shards_bot.services.pagination.{Page, paginate, PAGE_SIZE}`
  — identical generic pagination utility, new home, domain-agnostic (no
  `Character`/`Rarity`/collection-specific imports).

- [ ] **Step 1: Create `services/pagination.py`**

Create `src/ley_shards_bot/services/pagination.py`:

```python
"""Generic pagination — pages any sequence, nothing here is specific to
character collections. Was previously bundled inside services/collection.py
(its first consumer); Phase 1.1's /banners, /banner_info, and the admin
panel's users table all need the same thing — see issue #58.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from collections.abc import Sequence

PAGE_SIZE = 10

T = TypeVar("T")


@dataclass(frozen=True)
class Page(Generic[T]):
    items: list[T]
    page_number: int
    total_pages: int
    has_previous: bool
    has_next: bool


def paginate(items: Sequence[T], page_number: int, page_size: int = PAGE_SIZE) -> Page[T]:
    total_pages = max(1, math.ceil(len(items) / page_size))
    page_number = max(0, min(page_number, total_pages - 1))
    start = page_number * page_size
    end = start + page_size
    return Page(
        items=list(items[start:end]),
        page_number=page_number,
        total_pages=total_pages,
        has_previous=page_number > 0,
        has_next=page_number < total_pages - 1,
    )
```

- [ ] **Step 2: Remove the moved code from `services/collection.py`**

`src/ley_shards_bot/services/collection.py` currently reads:

```python
"""Character collection viewing: owned-character lookup + pagination.

Framework-agnostic — no python-telegram-bot imports (see CLAUDE.md).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, TypeVar

from loguru import logger
from sqlalchemy import select

from ley_shards_bot.models import Character, PlayerCharacter, Rarity

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm import Session

PAGE_SIZE = 10

# Highest rarity first, then alphabetical within a rarity tier.
_RARITY_SORT_ORDER = {Rarity.FIVE_STAR: 0, Rarity.FOUR_STAR: 1, Rarity.THREE_STAR: 2}


@dataclass(frozen=True)
class OwnedCharacter:
    character: Character
    copies_owned: int


def get_owned_characters(session: Session, player_id: int) -> list[OwnedCharacter]: ...


T = TypeVar("T")


@dataclass(frozen=True)
class Page(Generic[T]):
    items: list[T]
    page_number: int
    total_pages: int
    has_previous: bool
    has_next: bool


def paginate(items: Sequence[T], page_number: int, page_size: int = PAGE_SIZE) -> Page[T]: ...
```

Change it to (removing `PAGE_SIZE`, the second `T = TypeVar("T")`, `Page`,
`paginate`, and the now-unused `math`/`Generic`/`TypeVar`/`Sequence`
imports — `get_owned_characters` and `OwnedCharacter` are everything that
stays):

```python
"""Character collection viewing: owned-character lookup.

Framework-agnostic — no python-telegram-bot imports (see CLAUDE.md).
Generic pagination lives in services/pagination.py, not here — nothing
about paging a list is collection-specific (see issue #58).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import select

from ley_shards_bot.models import Character, PlayerCharacter, Rarity

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Highest rarity first, then alphabetical within a rarity tier.
_RARITY_SORT_ORDER = {Rarity.FIVE_STAR: 0, Rarity.FOUR_STAR: 1, Rarity.THREE_STAR: 2}


@dataclass(frozen=True)
class OwnedCharacter:
    character: Character
    copies_owned: int


def get_owned_characters(session: Session, player_id: int) -> list[OwnedCharacter]:
    rows = session.execute(
        select(PlayerCharacter, Character)
        .join(Character, PlayerCharacter.character_id == Character.anilist_id)
        .where(PlayerCharacter.player_id == player_id)
    ).all()
    owned = [
        OwnedCharacter(character=character, copies_owned=player_character.copies_owned)
        for player_character, character in rows
    ]
    owned.sort(key=lambda o: (_RARITY_SORT_ORDER[o.character.rarity], o.character.name))
    logger.debug("Collection lookup for {}: {} distinct characters", player_id, len(owned))
    return owned
```

- [ ] **Step 3: Update `commands/collection.py`**

Change line 21 from:

```python
from ley_shards_bot.services.collection import PAGE_SIZE, Page, get_owned_characters, paginate
```

to:

```python
from ley_shards_bot.services.collection import get_owned_characters
from ley_shards_bot.services.pagination import PAGE_SIZE, Page, paginate
```

No other line in `commands/collection.py` changes — `PAGE_SIZE`, `Page`,
`paginate`, and `get_owned_characters` are all still the same names in
scope, just split across two import lines now.

- [ ] **Step 4: Move `TestPaginate` out of `tests/services/test_collection.py`**

`tests/services/test_collection.py` currently has two classes,
`TestGetOwnedCharacters` and `TestPaginate`, and imports:

```python
from ley_shards_bot.services.collection import get_owned_characters, paginate
```

Change the import to:

```python
from ley_shards_bot.services.collection import get_owned_characters
```

and delete the entire `TestPaginate` class (currently the file's last 41
lines, from `class TestPaginate:` to end of file) — it moves to a new
file, not away entirely.

Create `tests/services/test_pagination.py`:

```python
"""Tests for the generic pagination utility — domain-agnostic, so these
tests use plain lists rather than any model (moved out of
tests/services/test_collection.py, see issue #58).
"""

from ley_shards_bot.services.pagination import paginate


class TestPaginate:
    def test_first_page_of_a_short_list(self):
        page = paginate([1, 2, 3], page_number=0, page_size=10)

        assert page.items == [1, 2, 3]
        assert page.total_pages == 1
        assert page.has_previous is False
        assert page.has_next is False

    def test_splits_across_pages(self):
        items = list(range(25))

        first = paginate(items, page_number=0, page_size=10)
        second = paginate(items, page_number=1, page_size=10)
        third = paginate(items, page_number=2, page_size=10)

        assert first.items == list(range(10))
        assert second.items == list(range(10, 20))
        assert third.items == list(range(20, 25))
        assert first.total_pages == 3
        assert first.has_next is True
        assert first.has_previous is False
        assert third.has_next is False
        assert third.has_previous is True

    def test_out_of_range_page_number_clamps_into_range(self):
        items = list(range(5))

        too_high = paginate(items, page_number=99, page_size=10)
        too_low = paginate(items, page_number=-5, page_size=10)

        assert too_high.page_number == 0
        assert too_low.page_number == 0

    def test_empty_list_is_a_single_empty_page(self):
        page = paginate([], page_number=0, page_size=10)

        assert page.items == []
        assert page.total_pages == 1
        assert page.has_previous is False
        assert page.has_next is False
```

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: all tests pass, same total count as before (4 tests moved
files, none added or removed).

- [ ] **Step 6: Verify + commit**

```bash
uv run ruff check .
uv run ruff format .
uv run ty check
qlty smells --all --no-snippets
git add -A
git commit -m "Move Page/paginate/PAGE_SIZE to a new services/pagination.py

Nothing about paging a sequence is collection-specific — it was only
defined in services/collection.py because /collection was its first
consumer. Phase 1.1's /banners, /banner_info, and the admin panel's
users table all need the same generic pagination.

Part of #58"
```

---

### Task 7: Fix `CLAUDE.md`'s stale test-strategy claim

**Files:**
- Modify: `CLAUDE.md:21-34`

**Interfaces:** none — documentation only.

- [ ] **Step 1: Update the directory tree**

In `CLAUDE.md`, change (lines 21–34):

```
  commands/       # one module per Telegram command (thin: parse update,
                   # call a service, format a reply — no business logic here)
  services/       # the actual game logic: economy, gacha engine, roster
                   # ingestion. Framework-agnostic — no python-telegram-bot
                   # imports in this package.
  models/         # SQLAlchemy ORM models, one module per table/aggregate
  api/            # (Phase 1.1) FastAPI routes for the admin panel — same
                   # rule as commands/: parse the request, call a service,
                   # return a response, no business logic here either.
                   # Shares services/+models/ with the bot, doesn't
                   # reimplement game rules.
migrations/       # Alembic migrations
tests/            # mirrors src/ layout; unit tests target services/ and
                   # models/, not the Telegram command handlers directly
```

to:

```
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
```

- [ ] **Step 2: Verify + commit**

No tests to run — doc-only change. Just confirm the pre-commit hook still
passes (it will; nothing Python changed):

```bash
uv run ruff check .
uv run ruff format .
uv run ty check
qlty smells --all --no-snippets
git add CLAUDE.md
git commit -m "CLAUDE.md: fix stale test-strategy claim, note commands/helpers/

tests/commands/ has been a full first-class suite testing command
handlers directly for a while — CLAUDE.md's own directory-tree comment
said the opposite. Also documents the new commands/helpers/ package
from this same set of fixes.

Part of #58"
```

---

### Task 8: Document the placement rules in `ARCHITECTURE.md`

**Files:**
- Modify: `ARCHITECTURE.md:67-96` (Component boundaries)
- Modify: `ARCHITECTURE.md:296-309` (Testing strategy)

**Interfaces:** none — documentation only.

- [ ] **Step 1: Rewrite "Component boundaries"**

In `ARCHITECTURE.md`, replace the entire "Component boundaries" section
(currently lines 67–96):

```markdown
## Component boundaries

```
commands/  →  services/  →  models/
(Telegram)    (game rules)   (persistence)
                    ▲
                    │
                  api/  (Phase 1.1, FastAPI — same services/models/,
                         different front door)
```

- **`commands/`** — one handler per Telegram command. Parses the
  `Update`, calls into `services/`, formats the reply. No game rules live
  here.
- **`services/`** — the game logic, framework-agnostic (no
  `python-telegram-bot` imports). This is what unit tests target, and
  what both `commands/` and (from Phase 1.1) `api/` call into — one
  source of truth for gacha/economy rules shared between the bot and the
  web panel, not two parallel implementations.
- **`models/`** — SQLAlchemy ORM models, one module per table/aggregate.
- **`api/`** (Phase 1.1) — FastAPI routes for the admin panel: one
  handler per endpoint, parses the request, calls into `services/`,
  returns a Pydantic response model. Validates Keycloak-issued OIDC
  tokens against Keycloak's JWKS endpoint. Mirrors `commands/`'s job for
  a different transport, and follows the same rule — no game rules live
  here either.

This separation exists so pity math, RNG weighting, and balance changes can
be tested as plain Python without a Telegram update, an HTTP request, or a
live DB.
```

with:

```markdown
## Component boundaries

```
commands/            →  services/           →  models/
commands/helpers/       (game rules)            (persistence)
(Telegram)                    ▲
                               │
                             api/  (Phase 1.1, FastAPI — same services/models/,
                                    different front door)
```

- **`commands/`** — one module per Telegram command (or small group of
  closely related commands, e.g. `gacha.py` holds both `/pull` and
  `/pull10`). Parses the `Update`, calls into `services/`, formats the
  reply. No game rules live here. Every function that ends in `_command`
  (or is registered as a `CommandHandler`/`CallbackQueryHandler` in
  `app.py`) lives in one of these files — nothing else does.
- **`commands/helpers/`** — Telegram-aware plumbing that more than one
  command file needs, but that isn't itself a command: chat-type/
  permission checks (`scoping.py`), resolving which player a command
  targets (`targeting.py`), formatting constants shared across replies
  (`formatting.py`), and the command-menu data shared by `/` autocomplete
  and `/help` (`menu.py`). Nothing in this package registers a handler in
  `app.py`. The test for "does this belong in `commands/helpers/` instead
  of a plain `commands/*.py` file" is simple: does it get used by more
  than one command module, or does it not correspond to an actual
  `/command` at all? Either one means `helpers/`, not the flat directory.
- **`services/`** — the game logic, framework-agnostic (no
  `python-telegram-bot` imports). This is what unit tests target, and
  what both `commands/` and (from Phase 1.1) `api/` call into — one
  source of truth for gacha/economy rules shared between the bot and the
  web panel, not two parallel implementations. Mostly one module per
  domain (`gacha.py`, `economy.py`, `roster.py`), but a concept that
  isn't owned by any single domain gets its own shared module instead of
  living inside whichever domain happened to need it first — e.g.
  `players.py` (a player's Telegram identity and its lookup, used by both
  `gacha.py` and `economy.py`) and `pagination.py` (paging any sequence,
  used by `collection.py` today and by Phase 1.1's `/banners`/admin-panel
  listings later). If you're about to add a function or type to a
  domain's `services/` module and it doesn't actually reference that
  domain's rules (no pity/rarity math in it, no currency amounts, no
  roster fields), that's the sign it belongs in a shared module instead —
  see "Before adding something new" below.
- **`models/`** — SQLAlchemy ORM models, one module per table/aggregate.
  Columns and relationships only — if a model file needs a method beyond
  what SQLAlchemy itself generates, that logic belongs in `services/`
  instead.
- **`api/`** (Phase 1.1) — FastAPI routes for the admin panel: one
  handler per endpoint, parses the request, calls into `services/`,
  returns a Pydantic response model. Validates Keycloak-issued OIDC
  tokens against Keycloak's JWKS endpoint. Mirrors `commands/`'s job for
  a different transport, and follows the same rule — no game rules live
  here either.

This separation exists so pity math, RNG weighting, and balance changes can
be tested as plain Python without a Telegram update, an HTTP request, or a
live DB.

### Before adding something new

When a change introduces a genuinely new file, module, enum, or shared
concept — not just a function added to an existing, already-scoped file —
its placement gets discussed and decided explicitly before writing code,
and this section gets updated with the decision. The alternative is how
`commands/helpers/`, `services/pagination.py`, and the move of `PlayerRef`
into `services/players.py` all came to be needed in the first place: each
one was originally dropped into whichever file happened to need it first
(`economy.py`, `collection.py`, `gacha.py`), not because it belonged
there, and it took a dedicated audit
([#58](https://github.com/sm-steel/ley-shards-bot/issues/58)) to notice
and fix it. Deciding placement up front is cheaper than an audit later.

A quick way to sanity-check a placement decision before committing to it:
does the new code reference the domain it's about to live in? A rule that
touches pity counters or rarity weights belongs in `services/gacha.py`; a
permission check or a value object with no game-rule content in it almost
certainly doesn't belong in any single domain's file.
```

- [ ] **Step 2: Fix the "Testing strategy" section**

In `ARCHITECTURE.md`, change the first bullet of "Testing strategy"
(currently line 298):

```markdown
- **Unit tests** (`tests/`, mirrors `services/`+`models/`): pity/RNG
  statistical simulation (thousands of simulated pulls per banner type
  confirming rates converge and pity actually forces a 5★ by the hard-pity
  pull), economy balance math, roster rarity bucketing.
```

to:

```markdown
- **Unit tests** (`tests/`, mirrors `src/` layout): `services/`+`models/`
  tests cover pity/RNG statistical simulation (thousands of simulated
  pulls per banner type confirming rates converge and pity actually
  forces a 5★ by the hard-pity pull), economy balance math, and roster
  rarity bucketing. `commands/` tests are thin-layer — topic/DM scoping,
  error-to-reply mapping, that a successful action produces the right
  reply — not a second copy of the game-math tests.
```

- [ ] **Step 3: Verify + commit**

```bash
uv run ruff check .
uv run ruff format .
uv run ty check
qlty smells --all --no-snippets
git add ARCHITECTURE.md
git commit -m "ARCHITECTURE.md: document commands/helpers/, services/ shared-module
pattern, and a placement-first rule for new code

Component boundaries now explains the commands/ vs commands/helpers/
split and why services/ has cross-domain modules like players.py and
pagination.py alongside per-domain ones. New \"Before adding something
new\" subsection makes explicit that placement gets discussed before
code for anything genuinely new, not decided by accident of which file
happened to need it first. Testing strategy's first bullet corrected
to match CLAUDE.md's fix in the previous commit.

Closes #58"
```

---

## Self-Review Notes

- **Spec coverage:** all 5 findings from issue #58 have a task —
  `_RARITY_STARS` (Task 4), `PlayerRef` (Task 5), the `_is_admin`/
  `_resolve_target` split (Tasks 2–3), pagination (Task 6), and the stale
  `CLAUDE.md` claim (Task 7). The user's two process requests — an
  authoritative "what goes where" reference and a "discuss before adding
  something new" rule, both in `ARCHITECTURE.md` — are Task 8.
- **Placeholder scan:** every step has real code, real file paths, real
  line numbers pulled from the actual current source (verified via `grep
  -n` immediately before writing this plan, so line numbers reflect the
  state after issue #18/#19's merges).
- **Type/name consistency:** `is_admin`, `resolve_target`, and
  `RARITY_STARS` are named identically everywhere they're introduced
  (Tasks 2/3/4) and everywhere they're later imported (Tasks 2/3/4's own
  "update callers" steps) — no drift between what a task produces and
  what a later task expects.
