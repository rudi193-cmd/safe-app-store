"""SAFE Framework Integration for UTETY Reddit Bots."""

import os as _os
import sqlite3 as _sqlite3

_STORE_ROOT = _os.path.join(_os.path.expanduser("~"), ".willow", "store")
_STORE_ROOT = _os.environ.get("WILLOW_STORE_ROOT", _STORE_ROOT)
_APP_ID = "safe-app-UTETY-Reddit-Bots"


def get_manifest():
    import json
    from pathlib import Path
    manifest_path = Path(__file__).parent / "safe-app-manifest.json"
    return json.loads(manifest_path.read_text())


def status():
    """Check if Willow store is reachable."""
    db_path = _os.path.join(_STORE_ROOT, "knowledge", "store.db")
    reachable = _os.path.exists(db_path)
    return {"ok": reachable, "store": _STORE_ROOT, "mode": "portless"}
