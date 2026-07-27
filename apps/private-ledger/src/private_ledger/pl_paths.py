"""
pl_paths.py — single vault-rooted path resolver for Private Ledger (packaged app).

Installer design D8: persistence derives from the vault root (D7), not a
hardcoded home path. PRIVATE_LEDGER_DB (and the legacy LEDGER_DB) override for
migration off an existing install.
"""
from __future__ import annotations

from pathlib import Path

# The shared resolver (box audit A5). vault_root is re-exported so callers that
# do `from private_ledger.pl_paths import vault_root` keep working.
from vault_paths import resolve, vault_root  # noqa: F401


def db_path() -> Path:
    # PRIVATE_LEDGER_DB (then the legacy LEDGER_DB) override for migration.
    return resolve("private-ledger", "private-ledger.db",
                   env_vars=("PRIVATE_LEDGER_DB", "LEDGER_DB"))
