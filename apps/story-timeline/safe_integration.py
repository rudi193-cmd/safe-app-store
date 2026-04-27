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


def _init_willow():
    """Initialize Willow store, handling missing/broken WILLOW_CORE gracefully."""
    _WILLOW_CORE = os.environ.get(
        "WILLOW_CORE",
        str(Path.home() / "github" / "willow-1.9" / "core")
    )
    
    if not Path(_WILLOW_CORE).exists():
        return None, False
    
    if _WILLOW_CORE not in sys.path:
        sys.path.insert(0, _WILLOW_CORE)
    
    try:
        from willow_store import WillowStore
        return WillowStore(), True
    except Exception as e:
        sys.stderr.write(f"[safe_integration] store init failed: {e}\n")
        return None, False


_STORE, _WILLOW_AVAILABLE = _init_willow()


def get_user_uuid() -> Optional[str]:
    try:
        data = json.loads(_IDENTITY_PATH.read_text())
        return data.get("uuid") or None
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def write_session_composite(stats: dict, uuid: str) -> bool:
    if not _WILLOW_AVAILABLE or not uuid:
        return False
    safe_uuid = re.sub(r"[^a-zA-Z0-9_\-]", "-", uuid)
    collection = f"user-{safe_uuid}/story-timeline/atoms"
    atom_id = f"session-{datetime.now().strftime('%Y%m%dT%H%M%S')}"
    record = {
        "id": atom_id,
        "type": "session_composite",
        "app_id": "story-timeline",
        "user_uuid": uuid,
        "created_at": datetime.now().isoformat(),
        **stats,
    }
    try:
        _STORE.put(collection, record, record_id=atom_id)
        return True
    except Exception as e:
        sys.stderr.write(f"[safe_integration] write_session_composite failed: {e}\n")
        return False
