# safe-app-field-notes

Quick-capture notebook for observations, ideas, and research notes. Feeds into The Binder.

## Install

    pip install safe-app-field-notes

## Run from source (standalone)

No Willow checkout, Postgres, or network required — the TUI stores notes in
`~/.willow/field-notes.db`.

    ./dev.sh        # macOS/Linux
    ./dev.ps1       # Windows (PowerShell)

The launcher creates a local virtualenv, installs requirements, and starts the
app. The Willow-backed `notes_db.py` backend is optional and only activates
when a Willow checkout is present (`WILLOW_CORE`).
