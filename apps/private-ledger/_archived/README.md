# _archived/

Retired code, kept for reference (archive, don't delete).

## `app.py` + `pl_paths.py` — the standalone single-table TUI

An earlier, simpler Private Ledger TUI backed by a single `entries` table. It
was superseded by the packaged app under `src/private_ledger/` (accounts +
categories + transactions schema, natural-language capture, budget bars, and
local LLM insights), which is what `safe-app-manifest.json` (`entry_point:
private_ledger.app:main`) and `pyproject.toml` (`[project.scripts]`) declare as
canonical.

`dev.sh` / `dev.ps1` now launch the packaged app (`python -m private_ledger`);
they previously ran this top-level `app.py`, which caused two disconnected
apps + schemas to live in one directory. The two files are moved together so
`app.py`'s `import pl_paths` still resolves if you run it directly from here.

Note: the two apps use different SQLite schemas (`entries` here vs.
`ledger_transactions`/`ledger_accounts`/`ledger_categories` in the package) at
the same DB path. If anyone has real data in the old `entries` table, a one-off
migration into the packaged schema is still an open follow-up.

## The scattered / dead Willow integration — replaced by `willow_bridge.py`

`safe_integration.py`, `ledger_db.py`, `backfill_from_willow.py`, and
`lattice_fallback.py` were the old, scattered Willow integration. They are
retired: nothing in the live app imported them (they only imported each other —
`backfill_from_willow` → `ledger_db` → `lattice_fallback`, and
`safe_integration` was imported by nothing), and the pattern they embodied was
the anti-pattern the new seam removes.

- `safe_integration.py` — portless no-op stubs (`ask`/`send`/`query` all return
  "not available in portless mode") that also read Willow's `store.db` SQLite
  file **directly**. Reaching into another service's database is exactly the
  coupling the injected bridge eliminates.
- `ledger_db.py` — an unused Postgres backend keyed to the "23-cubed lattice"
  model; never wired into the packaged `src/private_ledger/` app.
- `backfill_from_willow.py` — a one-off seeder built on `ledger_db` with a
  hardcoded synthetic seed; dead once `ledger_db` was.
- `lattice_fallback.py` — local-mode lattice constants used only by
  `ledger_db.py`.

All Willow contact now flows through a single outward seam:
`src/private_ledger/willow_bridge.py`. It imports the core (never the reverse),
takes an **injected** `ingest` callable instead of `import willow`, emits only
aggregates (privacy_tier `client_only` — no raw transaction rows), and fails
loudly (`PromotionRefused`) when a KB write is refused. See
`apps/oakenscrolls-office/willow_bridge.py` for the house pattern it mirrors.
