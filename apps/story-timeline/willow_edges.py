"""
willow_edges.py — Willow edge layer for story-timeline v2.

Wraps WillowStore (from willow-1.9/core/willow_store.py) for graph edges.
All edges scoped to user-{uuid}/story-timeline/_graph/edges.
Degrades gracefully to no-op when Willow is unavailable.
"""
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

_STORE = None
_WILLOW_AVAILABLE = False
_WILLOW_CORE_LAST = None

def _get_store():
    """Lazy-load and cache WillowStore. Re-initializes if WILLOW_CORE changes."""
    global _STORE, _WILLOW_AVAILABLE, _WILLOW_CORE_LAST

    willow_core = os.environ.get(
        "WILLOW_CORE",
        str(Path.home() / "github" / "willow-1.9" / "core")
    )

    # If WILLOW_CORE changed, reset cache and remove from sys.modules/sys.path to force re-initialization
    if willow_core != _WILLOW_CORE_LAST:
        _WILLOW_CORE_LAST = willow_core
        _STORE = None
        _WILLOW_AVAILABLE = False
        # Remove cached module and clean sys.path
        if 'willow_store' in sys.modules:
            del sys.modules['willow_store']
        # Remove old willow paths from sys.path
        sys.path = [p for p in sys.path if 'willow' not in p.lower()]

    if _WILLOW_AVAILABLE:
        return _STORE

    try:
        if willow_core not in sys.path:
            sys.path.insert(0, willow_core)
        from willow_store import WillowStore
        _STORE = WillowStore()
        _WILLOW_AVAILABLE = True
        return _STORE
    except Exception as e:
        sys.stderr.write(f"[willow_edges] store init failed: {e}\n")
        _STORE = None
        _WILLOW_AVAILABLE = False
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
    store = _get_store()
    if not store:
        return None
    edge_id = f"{_safe_id(from_id)}__{_safe_id(relation)}__{_safe_id(to_id)}"
    record = {
        "id": edge_id,
        "from_id": from_id,
        "to_id": to_id,
        "relation": relation,
        "context": context,
    }
    try:
        store.put(_collection(uuid), record, record_id=edge_id)
        return edge_id
    except Exception as e:
        sys.stderr.write(f"[willow_edges] add_edge failed: {e}\n")
        return None


def edges_for(node_id: str, uuid: Optional[str] = None) -> list[dict]:
    if not uuid:
        return []
    store = _get_store()
    if not store:
        return []
    try:
        col = _collection(uuid)
        conn = store._conn(col)
        try:
            rows = conn.execute(
                "SELECT data FROM records WHERE deleted = 0"
            ).fetchall()
        finally:
            conn.close()
        results = []
        for row in rows:
            edge = json.loads(row[0])
            if edge.get("from_id") == node_id or edge.get("to_id") == node_id:
                results.append(edge)
        return results
    except Exception:
        return []


def delete_edge(edge_id: str, uuid: Optional[str] = None) -> bool:
    if not uuid:
        return False
    store = _get_store()
    if not store:
        return False
    try:
        col = _collection(uuid)
        conn = store._conn(col)
        try:
            cur = conn.execute(
                "UPDATE records SET deleted = 1 WHERE id = ?", (edge_id,)
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
    except Exception:
        return False


def reconcile_orphans(valid_node_ids: list[str], uuid: Optional[str] = None) -> int:
    """Soft-delete edges whose from_id or to_id is not in valid_node_ids.
    Returns count of edges removed. Called at boot for integrity check."""
    if not uuid:
        return 0
    store = _get_store()
    if not store:
        return 0
    valid = set(valid_node_ids)
    removed = 0
    try:
        col = _collection(uuid)
        conn = store._conn(col)
        try:
            rows = conn.execute(
                "SELECT id, data FROM records WHERE deleted = 0"
            ).fetchall()
            for row in rows:
                edge = json.loads(row[1])
                if edge.get("from_id") not in valid or edge.get("to_id") not in valid:
                    conn.execute(
                        "UPDATE records SET deleted = 1 WHERE id = ?", (row[0],)
                    )
                    removed += 1
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        sys.stderr.write(f"[willow_edges] reconcile error: {e}\n")
        return removed
    return removed
