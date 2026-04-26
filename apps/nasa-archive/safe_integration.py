"""
SAFE Framework Integration — NASA Archive Explorer
===================================================
Session hooks, consent management, and Pigeon bus helpers.

Drop point: POST /api/pigeon/drop
Topics: ask, query, contribute, connect, status
"""

import json
import os as _os
import uuid
import sqlite3 as _sqlite3
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime, timezone

# ── Pigeon Bus Helpers ────────────────────────────────────────────────────────

_STORE_ROOT = _os.path.join(_os.path.expanduser("~"), ".willow", "store")
_STORE_ROOT = _os.environ.get("WILLOW_STORE_ROOT", _STORE_ROOT)
APP_ID = "safe-app-nasa-archive"

_session_id = str(uuid.uuid4())
_APP_DATA = Path(_os.path.expanduser("~")) / ".willow" / "apps" / APP_ID


def ask(prompt: str, persona: str = None, tier: str = "free") -> str:
    """LLM routing via Willow — not available in portless mode."""
    return "[Willow LLM routing not available in portless mode]"


def query(q: str, limit: int = 5) -> list:
    """Query Willow's knowledge store directly via SOIL SQLite."""
    db_path = _os.path.join(_STORE_ROOT, "knowledge", "store.db")
    if not _os.path.exists(db_path):
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
    db_path = _os.path.join(_STORE_ROOT, "knowledge", "store.db")
    reachable = _os.path.exists(db_path)
    return {"ok": reachable, "store": _STORE_ROOT, "mode": "portless"}


def _drop(topic: str, payload: dict) -> dict:
    return {"ok": False, "error": "portless mode — porch removed"}


# ── SAFE Session ──────────────────────────────────────────────────────────────

APP_STREAMS = [
    {
        "stream_id": "query_history",
        "purpose": "Remember searches you ran this session",
        "retention": "session",
        "required": False,
        "prompt": "May I remember your searches this session for quick re-run?"
    },
    {
        "stream_id": "saved_discoveries",
        "purpose": "Store datasets and images you explicitly save",
        "retention": "permanent",
        "required": False,
        "prompt": "May I save datasets and images you choose to keep?"
    }
]


class SAFESession:
    """Manages SAFE session lifecycle and consent."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.started_at = datetime.now()
        self.consents = {}
        self.active = True

    def on_session_start(self) -> Dict:
        return {
            "session_id": self.session_id,
            "authorization_requests": APP_STREAMS
        }

    def on_consent_granted(self, stream_id: str, granted: bool) -> Dict:
        self.consents[stream_id] = {
            "granted": granted,
            "timestamp": datetime.now().isoformat()
        }
        return {"status": "ok"}

    def can_access_stream(self, stream_id: str) -> bool:
        return self.consents.get(stream_id, {}).get("granted", False)

    def on_session_end(self) -> Dict:
        self.active = False
        actions = []
        if self.can_access_stream("query_history"):
            actions.append({"action": "delete", "stream": "query_history", "reason": "session_ended"})
        if self.can_access_stream("saved_discoveries"):
            actions.append({"action": "retain", "stream": "saved_discoveries", "reason": "permanent_consent"})
        return {
            "session_id": self.session_id,
            "ended_at": datetime.now().isoformat(),
            "duration_seconds": (datetime.now() - self.started_at).total_seconds(),
            "cleanup_actions": actions
        }

    def on_revoke(self, stream_id: str) -> Dict:
        if stream_id in self.consents:
            self.consents[stream_id]["granted"] = False
            self.consents[stream_id]["revoked_at"] = datetime.now().isoformat()
        return {"status": "revoked", "stream": stream_id, "action": "data_deleted"}


# ── Willow Consent Helpers ────────────────────────────────────────────────────

def get_consent_status(token=None):
    return False


def request_consent_url():
    return None



def send(to_app, subject, body, thread_id=None):
    return {"ok": False, "error": "messaging not available in portless mode"}


def check_inbox(unread_only=True):
    return []

