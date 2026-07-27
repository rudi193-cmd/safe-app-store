"""SAFE Framework Integration for LLMPhysics Bot."""

import os as _os
import sqlite3 as _sqlite3

from vault_paths import vault_root as _vault_root  # shared resolver (box audit A5)

_STORE_ROOT = str(_vault_root())
_APP_ID = "llmphysics-bot"


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
