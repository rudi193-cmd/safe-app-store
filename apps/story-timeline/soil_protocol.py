"""
soil_protocol.py — SOIL collection helpers for story-timeline protocol records.

Mirrors protocol nodes and provenance atoms to stable SOIL paths so other
Willow tools can read commonplace → timeline wiring without the TUI.
Degrades gracefully when no StorageBackend is configured.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime

import story_protocol
from storage_backend import get_backend


def mirror_protocol_record(node: dict, *, uuid: str) -> bool:
    collection_suffix = story_protocol.collection_for_type(node.get("type", ""))
    if not collection_suffix:
        return False
    client = get_backend()
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
    client = get_backend()
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
