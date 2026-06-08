"""
soil_protocol.py — SOIL collection helpers for story-timeline protocol records.

Mirrors protocol nodes and provenance atoms to stable SOIL paths so other
Willow tools can read commonplace → timeline wiring without the TUI.
Degrades gracefully when Willow is unavailable.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import story_protocol

_CLIENT = None
_CLIENT_INIT_FAILED = False


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
        client = SoilClient(app_id=story_protocol.APP_ID)
        if not client._available:
            sys.stderr.write("[soil_protocol] SoilClient unavailable\n")
            _CLIENT_INIT_FAILED = True
            return None
        _CLIENT = client
        return _CLIENT
    except Exception as exc:
        sys.stderr.write(f"[soil_protocol] init failed: {exc}\n")
        _CLIENT_INIT_FAILED = True
        return None


def mirror_protocol_record(node: dict, *, uuid: str) -> bool:
    """Mirror a protocol node to its typed SOIL collection."""
    collection_suffix = story_protocol.collection_for_type(node.get("type", ""))
    if not collection_suffix:
        return False
    client = _get_client()
    if not client or not uuid:
        return False
    collection = story_protocol.collection_path(uuid, collection_suffix)
    record = story_protocol.protocol_record_payload(node)
    try:
        result = client.put(collection, record, record_id=node["id"])
        return result is not None
    except Exception as exc:
        sys.stderr.write(f"[soil_protocol] mirror_protocol_record failed: {exc}\n")
        return False


def mirror_provenance(
    *,
    entry_id: str,
    provenance: dict,
    uuid: str,
) -> bool:
    """Write a provenance atom linking a timeline entry to its source."""
    client = _get_client()
    if not client or not uuid:
        return False
    safe_uuid = re.sub(r"[^a-zA-Z0-9_\-]", "-", uuid)
    collection = f"user-{safe_uuid}/story-timeline/atoms"
    now = datetime.now()
    atom_id = f"provenance-{entry_id}"
    record = {
        "id": atom_id,
        "type": "provenance",
        "app_id": story_protocol.APP_ID,
        "entry_id": entry_id,
        "created_at": now.isoformat(),
        **provenance,
    }
    try:
        result = client.put(collection, record, record_id=atom_id)
        return result is not None
    except Exception as exc:
        sys.stderr.write(f"[soil_protocol] mirror_provenance failed: {exc}\n")
        return False


def reset_client() -> None:
    """Test helper — reset cached SoilClient state."""
    global _CLIENT, _CLIENT_INIT_FAILED
    _CLIENT = None
    _CLIENT_INIT_FAILED = False
