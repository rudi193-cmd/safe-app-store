"""
nightstand_paths.py — single vault-rooted path resolver for The Nightstand.

Installer design D8: every persistence location derives from the vault root
(D7). No hardcoded home paths. Env overrides are preserved so an operator can
point at a legacy location during migration into the vault.
"""
from __future__ import annotations

import os
from pathlib import Path

APP_ID = "the-nightstand"


def vault_root() -> Path:
    """The vault box (D7). Defaults to the willow store root."""
    return Path(os.environ.get("WILLOW_STORE_ROOT", str(Path.home() / ".willow" / "store"))).expanduser()


def db_path() -> Path:
    """This app's database, under the vault. NIGHTSTAND_DB overrides."""
    env = os.environ.get("NIGHTSTAND_DB")
    return Path(env).expanduser() if env else vault_root() / APP_ID / "nightstand.db"
