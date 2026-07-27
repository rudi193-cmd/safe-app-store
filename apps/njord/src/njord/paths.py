"""paths.py — single vault-rooted path resolver for Njord.

Persistence derives from the vault root (WILLOW_STORE_ROOT), never a hardcoded
home path — mirrors private-ledger's pl_paths design. All Njord state (journal,
kill-switch dead-man's-file, provenance cache, paper track record) lives under
$WILLOW_STORE_ROOT/njord/.
"""
from __future__ import annotations

from pathlib import Path

# The shared resolver (box audit A5). vault_root is re-exported so callers that
# do `from njord.paths import vault_root` keep working.
from vault_paths import app_dir as _vault_app_dir, vault_root  # noqa: F401


def app_dir() -> Path:
    """Njord's own directory under the vault. NJORD_HOME overrides for tests."""
    return _vault_app_dir("njord", env_var="NJORD_HOME")


def ensure_app_dir() -> Path:
    d = app_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def journal_path() -> Path:
    return app_dir() / "journal.jsonl"


def killswitch_path() -> Path:
    """Dead-man's-file. Its presence means: stop trading immediately."""
    return app_dir() / "KILL"


def paper_record_path() -> Path:
    """Append-only record of simulated (paper) fills — the paper track record
    the live gate inspects."""
    return app_dir() / "paper_record.jsonl"


def provenance_cache_dir() -> Path:
    return app_dir() / "cache"
