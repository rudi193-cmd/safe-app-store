# safe-app-private-ledger

Local personal budgeting companion — fully private, no cloud sync, paired with Public Ledger.

## Install

    pip install safe-app-private-ledger

## Run from source (standalone)

No Willow checkout, Postgres, or network required — the TUI stores your ledger
in `~/.willow/private-ledger.db`.

    ./dev.sh        # macOS/Linux
    ./dev.ps1       # Windows (PowerShell)

The launcher creates a local virtualenv, installs requirements, and starts the
app. The Willow-backed `ledger_db.py` backend is optional and only activates
when a Willow checkout is present (`WILLOW_CORE`).
