"""
gazelle_paths.py — single vault-rooted path resolver for Law Gazelle.

Installer design D8: every persistence and sensitive-data location derives from
the vault root (D7). No hardcoded home paths. Env overrides are preserved so an
operator can point at a legacy location (e.g. an existing ~/Desktop/Nest) during
migration into the vault.
"""
from __future__ import annotations

import os
from pathlib import Path

APP_ID = "law-gazelle"


def vault_root() -> Path:
    """The vault box (D7). Defaults to the willow store root."""
    return Path(os.environ.get("WILLOW_STORE_ROOT", str(Path.home() / ".willow" / "store"))).expanduser()


def app_data() -> Path:
    """This app's own persistence, under the vault. APP_DATA overrides."""
    env = os.environ.get("APP_DATA")
    return Path(env).expanduser() if env else vault_root() / APP_ID


def nest_source() -> Path:
    """Sensitive Nest legal data (PII), under the vault by default.
    NEST_SOURCE overrides (e.g. a legacy ~/Desktop/Nest during migration)."""
    env = os.environ.get("NEST_SOURCE")
    return Path(env).expanduser() if env else app_data() / "nest"


def persona_path() -> Path:
    """Client persona (PII), under the vault. PERSONA_PATH overrides."""
    env = os.environ.get("PERSONA_PATH")
    return Path(env).expanduser() if env else app_data() / "persona.md"
