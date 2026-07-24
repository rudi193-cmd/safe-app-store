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

## Promotion status (store-wide)

| App | no-egress guard | action |
|---|---|---|
| **private-ledger** | ✅ wired to `safe-app-common` | reference — done |
| **oakenscrolls-office** | has its own copy | migrate to the shared checker |
| **public-ledger** | none (opens a server) | add via `safe-app-common` |
| **ask-jeles** | none (opens an API) | add via `safe-app-common` |
| others | none | add as each gains a network-capable seam |

The network-surface apps (public-ledger, ask-jeles) are the priority — they open
servers, so they most need the guard. Each is a small PR: add the `[test]` dep,
declare the app's core modules, call the shared assertions.

## Growing the package

Add a helper here only when it is genuinely shared and dependency-free (the
next candidates surfaced this session: a canonical persona loader for #18, once
the divergent per-app `personas.py` are reconciled). Anything app-specific stays
in the app.

---

*Convention doc. Package: `safe-app-common` (`safe-app-common-package` repo).
Companion to convention #11 (which references this for the no-egress checklist
item) and #18 (dedup). `ΔΣ=42`*
