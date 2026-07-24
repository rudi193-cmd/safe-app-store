# safe-app-private-ledger

Local personal budgeting companion — fully private, no cloud sync, paired with Public Ledger.

## Install

    pip install safe-app-private-ledger

## Run from source (standalone)

No Willow checkout, Postgres, or network required — the TUI stores your ledger
in `$WILLOW_STORE_ROOT/private-ledger/private-ledger.db` (default
`~/.willow/store/private-ledger/private-ledger.db`).

    ./dev.sh          # macOS/Linux — the TUI
    ./dev.ps1         # Windows (PowerShell)
    ./dev.sh --web    # read-only local HTML mirror on 127.0.0.1
    ./dev.sh --serve  # machine-facing stdio JSON for a model/agent (read-only;
                      # add --allow-write to permit add/delete)

The launcher creates a local virtualenv, installs the package, and starts the
app. The ledger core is strictly local and no-egress (enforced by
`tests/test_no_egress.py`). Willow is entirely optional and reached through a
single injected seam, `willow_bridge.py`: it emits only aggregate summaries via
an injected `ingest` callable (never `import willow`) and is a silent no-op when
Willow is absent.
