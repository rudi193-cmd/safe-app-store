"""Bootstrap Willow core modules (jeles_sources, llm_edge) for AskJeles."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _candidates() -> list[Path]:
    env = os.environ.get("WILLOW_ROOT", "").strip()
    if env:
        yield Path(env).expanduser()
    here = Path(__file__).resolve()
    # safe-app-store/apps/ask-jeles/askjeles -> sibling github/willow-2.0
    yield here.parents[3].parent / "willow-2.0"
    yield Path.home() / "github" / "willow-2.0"
    yield Path.home() / "willow-2.0"


def app_root() -> Path:
    """Directory containing personas.py and safe_integration.py."""
    return Path(__file__).resolve().parent.parent


def bootstrap() -> Path | None:
    """Add Willow root and app root to sys.path. Returns Willow root if found."""
    root = app_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    for candidate in _candidates():
        core = candidate / "core" / "jeles_sources.py"
        if core.is_file():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            return candidate
    return None
