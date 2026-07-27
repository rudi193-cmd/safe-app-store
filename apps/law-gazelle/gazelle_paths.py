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

# The shared resolver (box audit A5). vault_root is re-exported so callers that
# do `from gazelle_paths import vault_root` keep working.
from vault_paths import app_dir, vault_root  # noqa: F401

APP_ID = "law-gazelle"


def app_data() -> Path:
    """This app's own persistence, under the vault. APP_DATA overrides."""
    return app_dir(APP_ID)


def nest_source() -> Path:
    """Sensitive Nest legal data (PII), under the vault by default.
    NEST_SOURCE overrides (e.g. a legacy ~/Desktop/Nest during migration)."""
    env = os.environ.get("NEST_SOURCE")
    return Path(env).expanduser() if env else app_data() / "nest"


def persona_path() -> Path:
    """Client persona (PII), under the vault. PERSONA_PATH overrides."""
    env = os.environ.get("PERSONA_PATH")
    return Path(env).expanduser() if env else app_data() / "persona.md"
