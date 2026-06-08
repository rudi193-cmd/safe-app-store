"""
safe_integration.py — User identity + session composite for story-timeline v2.

Reads user UUID from ~/.willow/user_identity.json (provisioned by willow-seed).
Writes a structured session composite atom to Willow on app close.
Talks to Willow via SoilClient (MCP/stdio) — all calls go through the SAP gate.
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

_CLIENT = None
_CLIENT_INIT_FAILED = False

APP_ID = "story-timeline"


def _get_client():
    global _CLIENT, _CLIENT_INIT_FAILED

    if _CLIENT is not None:
        return _CLIENT
    if _CLIENT_INIT_FAILED:
        return None

    try:
        willow_root = os.environ.get(
            "WILLOW_ROOT",
            str(Path(os.environ.get(
                "WILLOW_CORE",
                str(Path.home() / "github" / "willow-1.9" / "core")
            )).parent)
        )
        if willow_root not in sys.path:
            sys.path.insert(0, willow_root)
        from sap.clients.soil_client import SoilClient
        client = SoilClient(app_id=APP_ID)
        if not client._available:
            sys.stderr.write("[safe_integration] store init failed: SoilClient unavailable\n")
            _CLIENT_INIT_FAILED = True
            return None
        _CLIENT = client
        return _CLIENT
    except Exception as e:
        sys.stderr.write(f"[safe_integration] store init failed: {e}\n")
        _CLIENT_INIT_FAILED = True
        return None


def get_user_uuid() -> Optional[str]:
    try:
        data = json.loads(_IDENTITY_PATH.read_text())
        return data.get("uuid") or None
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def write_session_composite(stats: dict, uuid: str) -> bool:
    client = _get_client()
    if not client or not uuid:
        return False
    safe_uuid = re.sub(r"[^a-zA-Z0-9_\-]", "-", uuid)
    collection = f"user-{safe_uuid}/story-timeline/atoms"
    now = datetime.now()
    atom_id = f"session-{now.strftime('%Y%m%dT%H%M%S')}"
    record = {
        "id": atom_id,
        "type": "session_composite",
        "app_id": APP_ID,
        "user_uuid": uuid,
        "created_at": now.isoformat(),
        **stats,
    }
    try:
        result = client.put(collection, record, record_id=atom_id)
        return result is not None
    except Exception as e:
        sys.stderr.write(f"[safe_integration] write_session_composite failed: {e}\n")
        return False
