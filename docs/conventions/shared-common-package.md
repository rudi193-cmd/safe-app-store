# Convention: `safe-app-common`, the shared building blocks (#13)
b17: SAPS1

Small, dependency-free helpers every SAFE app was re-implementing now live in
one published package — **`safe-app-common`**
(`github.com/rudi193-cmd/safe-app-common-package`) — instead of a per-app copy or
an in-repo `_lib/`.

## Why a package, not an in-repo `_lib/`

CLAUDE.md rule #6: *each `apps/<name>/` is self-contained.* An importable
top-level `_lib/` would break that — apps would stop being portable outside the
monorepo. So the shared code is a **dependency apps declare**, exactly like the
fleet declares Nestor: one canonical source, no vendored copies, and each app
still stands alone (it names the dep in its own `pyproject.toml`).

```toml
[project.optional-dependencies]
test = [
    "safe-app-common @ git+https://github.com/rudi193-cmd/safe-app-common-package@main",
]
```

(Pin to the branch until a tag is cut, then repin — the Nestor pattern.)

## First module: `no_egress`

The structural no-egress checker (was copied into each app's
`tests/test_no_egress.py`). An app declares its own core/seam partition and
calls the shared assertions:

```python
from safe_app_common.no_egress import (
    assert_no_egress, assert_does_not_import, assert_file_no_egress,
)
```

See the package README for the full API. It is pure stdlib and reproduces the
per-app tests byte-for-byte in behavior — verified against private-ledger's live
core.

## Which apps get a no-egress guard

The invariant applies to apps that hold **private data locally** — the ledger
and its math must be incapable of talking out. It does **not** apply to apps
that egress **by design**. Checked this session:

| App | no-egress guard | status |
|---|---|---|
| **private-ledger** | ✅ wired to `safe-app-common` | reference — done |
| **oakenscrolls-office** | ✅ migrated to `safe-app-common` | done (was a per-app copy) |
| **public-ledger** | ❌ **egress by design** | fetches public gov data (`usaspending`/`propublica` via `requests`) — no-egress does not apply |
| **ask-jeles** | ❌ **egress by design** | web-search app (`web_search`/`leaf`/`prism` via `requests`) — no-egress does not apply |
| **utety** | ❌ **stdlib-only exception** | deliberately zero-install ("nothing to pip-install on a child's device"); depending on this package would contradict the principle its own test protects. Keeps its richer self-contained scanner (dir-glob + a runtime subprocess import check). *The cross-fill ran the other way:* its dir-glob pattern and `boto3` were promoted INTO `safe_app_common.no_egress` (`assert_dir_no_egress`). |
| others | assess per app | add only where a private-data core exists |

> Note the direction: a "duplicate scanner" is not automatically a migration
> target. utety's is richer than the shared one and its app forbids the
> dependency — so the right move was to *harvest* what it had (dir-glob, boto3)
> into the shared checker and leave utety self-contained. Promote the pattern,
> not the coupling.

> Correction, kept visible: an earlier draft named public-ledger and ask-jeles
> as promotion targets "because they open servers." That conflated *has a
> network surface* with *must not egress*. Both egress by design — a no-egress
> test there would be theater. The signal is not "opens a port"; it is "holds
> private data that must never leave." Assess each app's data, not its I/O.

Adding the guard to a qualifying app is a small change: add the `[test]` dep,
declare the app's no-egress core modules, call the shared assertions.

## Second module: `safe_client` — SAFE-integration dedup (#18)

`safe_integration.py` was copied across ~17 apps. The cross-audit split it:

- **Portless family** (the-squirrel, llmphysics-bot, UTETY-Reddit-Bots) —
  byte-identical except `_APP_ID`, a store-reachability probe + manifest reader.
  **Extracted** as `safe_app_common.safe_client` (`store_root`/`status(app_id)`/
  `get_manifest`), portless by construction. **the-squirrel wired as proof**
  (thin shim, its public API unchanged). Remaining two are **unpackaged** (no
  `pyproject.toml`) — they need a packaging pass before they can declare the dep.
- **Full-API family** (ask-jeles + 7: `ask`/`query`/`contribute`/`SAFESession`/
  consent/messaging) — a larger surface that talks to a **live MCP/SAFE server**.
  Deliberately **not** extracted yet: it can't be verified offline, and a broken
  shared client is worse than the current drift. Follow-on, needs a live server.

### The Jeles persona (#18's other half) — canonical answer, one open fork

The cross-audit resolved *which* Jeles is authoritative:

- **Canon:** `apps/utety-chat/data/professors/jeles_persona.json` (structured,
  richest) → compiles to the `utety-chat/personas.py` string.
- `apps/ask-jeles/personas.py` = **byte-identical** copy (safe to point at canon).
- `apps/the-squirrel/personas.py` = **drifted paraphrase** (regenerate from canon
  — but that changes the app's Jeles voice, a behavior-affecting edit).
- `/workspace/jeles` = **empty repo**, the apparent intended home.

**Open fork (operator's call, like #13's topology):** where does the shared
persona *data* live — bundled in `safe-app-common`, seeded into the empty
`jeles` repo, or kept canonical in `utety-chat` with others pointing at it? The
loader is shared code (fits here); the persona *content* home is a topology
decision not yet made. Held rather than guessed.

## Growing the package

Add a helper here only when it is genuinely shared and dependency-free.
Anything app-specific stays in the app.

---

*Convention doc. Package: `safe-app-common` (`safe-app-common-package` repo).
Companion to convention #11 (which references this for the no-egress checklist
item) and #18 (dedup). `ΔΣ=42`*
