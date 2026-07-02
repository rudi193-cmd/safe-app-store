"""Resolve app root and data/ for dev tree, editable install, and wheel."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def app_root() -> Path:
    """Directory containing app.py, data/, and scripts/."""
    env = os.environ.get("CIVICS_CHECK_HOME", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    # civics/paths.py → app root in source / editable install
    root = Path(__file__).resolve().parent.parent
    if (root / "app.py").exists() and (root / "data").exists():
        return root
    # Installed wheel: top-level modules live next to civics/ under site-packages
    if (root / "data" / "catalog.json").exists():
        return root
    pkg_data = Path(__file__).resolve().parent / "data"
    if (pkg_data / "catalog.json").exists():
        return Path(__file__).resolve().parent
    return root


@lru_cache(maxsize=1)
def data_dir() -> Path:
    """Compiled catalog and sources — data/ at app root or civics/data in wheels."""
    root = app_root()
    for candidate in (root / "data", Path(__file__).resolve().parent / "data"):
        if (candidate / "catalog.json").exists():
            return candidate
    # Dev before first catalog build — prefer app-root data/
    if (root / "data").is_dir():
        return root / "data"
    bundled = Path(__file__).resolve().parent / "data"
    if bundled.is_dir():
        return bundled
    return root / "data"
