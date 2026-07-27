"""
story_paths.py — Vault-root path resolver for story-timeline (installer design D8).

All data persistence routes through here instead of hardcoded home paths, so
the app honors WILLOW_STORE_ROOT (and APP_DATA) overrides at runtime.
"""
import os
from pathlib import Path

# The shared resolver (box audit A5). vault_root is re-exported so callers that
# do `from story_paths import vault_root` keep working.
from vault_paths import app_dir, vault_root  # noqa: F401


def app_data() -> Path:
    return app_dir("story-timeline")


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
