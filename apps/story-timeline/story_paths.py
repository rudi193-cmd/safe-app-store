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


def willow_root() -> Path | None:
    """Locate a Willow checkout that ships sap/clients/soil_client.py.

    Probes WILLOW_ROOT, then WILLOW_CORE (which historically pointed at
    <root>/core), then well-known checkout locations. Each candidate is
    validated before use so a stale path never lands on sys.path (ST-PATH-01).
    Returns None when nothing is found — callers degrade gracefully.
    """
    core = os.environ.get("WILLOW_CORE", "")
    candidates = [
        os.environ.get("WILLOW_ROOT", ""),
        str(Path(core).expanduser().parent) if core else "",
        str(Path(__file__).resolve().parent.parent.parent.parent / "willow-2.0"),
        str(Path.home() / "github" / "willow-2.0"),
        str(Path.home() / "willow-2.0"),
        str(Path.home() / "github" / "willow-1.9"),
    ]
    for c in candidates:
        if c and (Path(c).expanduser() / "sap" / "clients" / "soil_client.py").is_file():
            return Path(c).expanduser()
    return None
