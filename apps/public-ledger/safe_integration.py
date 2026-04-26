"""
SAFE Framework Integration — Public Ledger
============================================
Pigeon bus helpers for dropping messages to Willow.

Drop point: POST /api/pigeon/drop
Topics: ask, query, contribute, connect, status
"""

import json
import os
import uuid
import sqlite3 as _sqlite3
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

_STORE_ROOT = os.path.join(os.path.expanduser("~"), ".willow", "store")
_STORE_ROOT = os.environ.get("WILLOW_STORE_ROOT", _STORE_ROOT)
APP_ID = "safe-app-public-ledger"

_session_id = str(uuid.uuid4())
_APP_DATA = Path(os.path.expanduser("~")) / ".willow" / "apps" / APP_ID


def ask(prompt: str, persona: Optional[str] = None, tier: str = "free") -> str:
    """LLM routing via Willow — not available in portless mode."""
    return "[Willow LLM routing not available in portless mode]"


def ask_raw(prompt: str, tier: str = "free") -> dict:
    """LLM routing via Willow — not available in portless mode."""
    return {"ok": False, "error": "LLM routing not available in portless mode"}


def query(q: str, limit: int = 5) -> list:
    """Query Willow's knowledge store directly via SOIL SQLite."""
    db_path = os.path.join(_STORE_ROOT, "knowledge", "store.db")
    if not os.path.exists(db_path):
        return []
    try:
        conn = _sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT data FROM records WHERE deleted=0 AND data LIKE ? LIMIT ?",
            (f"%{q}%", limit)
        ).fetchall()
        conn.close()
        return [json.loads(r[0]) for r in rows]
    except Exception:
        return []


def contribute(content: str, category: str = "note", metadata: Optional[dict] = None) -> dict:
    """Stage a contribution to the Willow intake queue (filesystem, portless)."""
    try:
        intake_dir = _APP_DATA / "intake"
        intake_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        fname = intake_dir / f"{ts}_{uuid.uuid4().hex[:8]}.json"
        fname.write_text(json.dumps({
            "source_app": APP_ID,
            "type": category,
            "content": content,
            "metadata": metadata or {},
            "contributed_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2))
        return {"ok": True, "staged": str(fname)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def status() -> dict:
    """Check if Willow store is reachable."""
    db_path = os.path.join(_STORE_ROOT, "knowledge", "store.db")
    reachable = os.path.exists(db_path)
    return {"ok": reachable, "store": _STORE_ROOT, "mode": "portless"}


def _drop(topic: str, payload: dict) -> dict:
    return {"ok": False, "error": "portless mode — porch removed"}


# ── Willow Consent Helpers ────────────────────────────────────────────────────

def get_consent_status(token=None):
    return False


def request_consent_url():
    return None


def send(to_app, subject, body, thread_id=None):
    return {"ok": False, "error": "messaging not available in portless mode"}


def check_inbox(unread_only=True):
    return []

