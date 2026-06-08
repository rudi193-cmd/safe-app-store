"""
willow_edges.py — Willow edge layer for story-timeline v2.

Edges scoped to user-{uuid}/story-timeline/_graph/edges.
Talks to Willow via SoilClient (MCP/stdio) — all calls go through the SAP gate.
Degrades gracefully to no-op when Willow is unavailable.
"""
import os
import re
import sys
from pathlib import Path
from typing import Optional

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
            sys.stderr.write("[willow_edges] store init failed: SoilClient unavailable\n")
            _CLIENT_INIT_FAILED = True
            return None
        _CLIENT = client
        return _CLIENT
    except Exception as e:
        sys.stderr.write(f"[willow_edges] store init failed: {e}\n")
        _CLIENT_INIT_FAILED = True
        return None


def _collection(uuid: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "-", uuid)
    return f"user-{safe}/story-timeline/_graph/edges"


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]", "-", value)


def add_edge(from_id: str, to_id: str, relation: str,
             context: str = "", uuid: Optional[str] = None) -> Optional[str]:
    if not uuid:
        return None
    client = _get_client()
    if not client:
        return None
    edge_id = f"{_safe_id(from_id)}__{_safe_id(relation)}__{_safe_id(to_id)}"
    record = {
        "id": edge_id,
        "from_id": from_id,
        "to_id": to_id,
        "relation": relation,
        "context": context,
    }
    return client.put(_collection(uuid), record, record_id=edge_id)


def edges_for(node_id: str, uuid: Optional[str] = None) -> list[dict]:
    if not uuid:
        return []
    client = _get_client()
    if not client:
        return []
    records = client.list(_collection(uuid))
    return [
        r for r in records
        if isinstance(r, dict) and (
            r.get("from_id") == node_id or r.get("to_id") == node_id
        )
    ]


def delete_edge(edge_id: str, uuid: Optional[str] = None) -> bool:
    if not uuid:
        return False
    client = _get_client()
    if not client:
        return False
    return client.delete(_collection(uuid), edge_id)


def reconcile_orphans(valid_node_ids: list[str], uuid: Optional[str] = None) -> int:
    """Soft-delete edges whose from_id or to_id is not in valid_node_ids.
    Returns count of edges removed. Called at boot for integrity check."""
    if not uuid:
        return 0
    client = _get_client()
    if not client:
        return 0
    valid = set(valid_node_ids)
    records = client.list(_collection(uuid))
    removed = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("from_id") not in valid or record.get("to_id") not in valid:
            edge_id = record.get("id")
            if edge_id and client.delete(_collection(uuid), edge_id):
                removed += 1
    return removed
