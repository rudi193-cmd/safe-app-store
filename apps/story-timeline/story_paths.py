"""
story_paths.py — Vault-root path resolver for story-timeline (installer design D8).

All data persistence routes through here instead of hardcoded home paths, so
the app honors WILLOW_STORE_ROOT (and APP_DATA) overrides at runtime.
"""
import os
from pathlib import Path


def vault_root() -> Path:
    return Path(os.environ.get("WILLOW_STORE_ROOT", str(Path.home() / ".willow" / "store"))).expanduser()


def app_data() -> Path:
    env = os.environ.get("APP_DATA")
    return Path(env).expanduser() if env else vault_root() / "story-timeline"
