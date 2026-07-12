"""
jeles_paths.py — single vault-rooted path resolver for Ask Jeles.

Installer design D8: every persistence location derives from the vault root
(D7). No hardcoded home paths. Env overrides are preserved so an operator can
point at a legacy location during migration into the vault.
"""
from __future__ import annotations

import os
from pathlib import Path

APP_ID = "ask-jeles"


def vault_root() -> Path:
    """The vault box (D7). Defaults to the willow store root."""
    return Path(os.environ.get("WILLOW_STORE_ROOT", str(Path.home() / ".willow" / "store"))).expanduser()


def app_data() -> Path:
    """This app's own persistence, under the vault. APP_DATA overrides."""
    env = os.environ.get("APP_DATA")
    return Path(env).expanduser() if env else vault_root() / APP_ID
