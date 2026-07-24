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
