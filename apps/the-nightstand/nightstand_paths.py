"""
nightstand_paths.py — single vault-rooted path resolver for The Nightstand.

Installer design D8: every persistence location derives from the vault root
(D7). No hardcoded home paths. Env overrides are preserved so an operator can
point at a legacy location during migration into the vault.
"""
from __future__ import annotations

from pathlib import Path

# The shared resolver (box audit A5). vault_root is re-exported so callers that
# do `from nightstand_paths import vault_root` keep working.
from vault_paths import resolve, vault_root  # noqa: F401

APP_ID = "the-nightstand"


def db_path() -> Path:
    """This app's database, under the vault. NIGHTSTAND_DB overrides."""
    return resolve(APP_ID, "nightstand.db", env_vars=("NIGHTSTAND_DB",))
