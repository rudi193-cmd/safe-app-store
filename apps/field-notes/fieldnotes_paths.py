"""
fieldnotes_paths.py — single vault-rooted path resolver for Field Notes.

Installer design D8: every persistence and sensitive-data location derives from
the vault root (D7). No hardcoded home paths. Env overrides are preserved so an
operator can point at a legacy location during migration into the vault.
"""
from __future__ import annotations

from pathlib import Path

# The shared resolver (box audit A5). vault_root is re-exported so callers that
# do `from fieldnotes_paths import vault_root` keep working.
from vault_paths import resolve, vault_root  # noqa: F401

APP_ID = "field-notes"


def db_path() -> Path:
    """This app's notes database, under the vault. FIELD_NOTES_DB overrides."""
    return resolve("field-notes", "field-notes.db", env_vars=("FIELD_NOTES_DB",))
