"""
pl_paths.py — single vault-rooted path resolver for Private Ledger (top-level app).

Installer design D8: persistence derives from the vault root (D7), not a
hardcoded home path. PRIVATE_LEDGER_DB (and the legacy LEDGER_DB) override for
migration off an existing install.
"""
from __future__ import annotations

import os
from pathlib import Path


def vault_root() -> Path:
    return Path(os.environ.get("WILLOW_STORE_ROOT", str(Path.home() / ".willow" / "store"))).expanduser()


def db_path() -> Path:
    env = os.environ.get("PRIVATE_LEDGER_DB") or os.environ.get("LEDGER_DB")
    return Path(env).expanduser() if env else vault_root() / "private-ledger" / "private-ledger.db"
