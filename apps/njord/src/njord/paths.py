"""paths.py — single vault-rooted path resolver for Njord.

Persistence derives from the vault root (WILLOW_STORE_ROOT), never a hardcoded
home path — mirrors private-ledger's pl_paths design. All Njord state (journal,
kill-switch dead-man's-file, provenance cache, paper track record) lives under
$WILLOW_STORE_ROOT/njord/.
"""
from __future__ import annotations

import os
from pathlib import Path


def vault_root() -> Path:
    """Root of the local SAFE vault store."""
    return Path(
        os.environ.get("WILLOW_STORE_ROOT", str(Path.home() / ".willow" / "store"))
    ).expanduser()


def app_dir() -> Path:
    """Njord's own directory under the vault. NJORD_HOME overrides for tests."""
    env = os.environ.get("NJORD_HOME")
    return Path(env).expanduser() if env else vault_root() / "njord"


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
