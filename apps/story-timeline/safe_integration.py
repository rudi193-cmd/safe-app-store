"""
safe_integration.py — User identity + session composite for story-timeline v2.

Reads user UUID from ~/.willow/user_identity.json (provisioned by willow-seed).
Writes a structured session composite atom to Willow on app close.
Degrades gracefully if Willow is unavailable.
"""
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

_IDENTITY_PATH = Path.home() / ".willow" / "user_identity.json"

_WILLOW_STORE = None
_WILLOW_CORE_LAST = None


def _get_store():
    """Lazy-load and cache WillowStore. Re-initializes if WILLOW_CORE changed."""
    global _WILLOW_STORE, _WILLOW_CORE_LAST

    willow_core = os.environ.get(
        "WILLOW_CORE",
        str(Path.home() / "github" / "willow-1.9" / "core")
    )

    # If WILLOW_CORE changed, reset cache and remove from sys.modules/sys.path to force re-initialization
    if willow_core != _WILLOW_CORE_LAST:
        _WILLOW_CORE_LAST = willow_core
        _WILLOW_STORE = None
        # Remove cached module and clean sys.path
        if 'willow_store' in sys.modules:
            del sys.modules['willow_store']
        # Remove old willow paths from sys.path
        sys.path = [p for p in sys.path if 'willow' not in p.lower()]

    if _WILLOW_STORE is not None:
        return _WILLOW_STORE

    try:
        if willow_core not in sys.path:
            sys.path.insert(0, willow_core)
        from willow_store import WillowStore
        store_root = os.environ.get("WILLOW_STORE_ROOT")
        _WILLOW_STORE = WillowStore(root=store_root) if store_root else WillowStore()
        return _WILLOW_STORE
    except Exception as e:
        sys.stderr.write(f"[safe_integration] store init failed: {e}\n")
        _WILLOW_STORE = None
        return None


def get_user_uuid() -> Optional[str]:
    try:
        data = json.loads(_IDENTITY_PATH.read_text())
        return data.get("uuid") or None
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def write_session_composite(stats: dict, uuid: str) -> bool:
    store = _get_store()
    if not store or not uuid:
        return False
    safe_uuid = re.sub(r"[^a-zA-Z0-9_\-]", "-", uuid)
    collection = f"user-{safe_uuid}/story-timeline/atoms"
    now = datetime.now()
    atom_id = f"session-{now.strftime('%Y%m%dT%H%M%S')}"
    record = {
        "id": atom_id,
        "type": "session_composite",
        "app_id": "story-timeline",
        "user_uuid": uuid,
        "created_at": now.isoformat(),
        **stats,
    }
    try:
        store.put(collection, record, record_id=atom_id)
        return True
    except Exception as e:
        sys.stderr.write(f"[safe_integration] write_session_composite failed: {e}\n")
        return False
