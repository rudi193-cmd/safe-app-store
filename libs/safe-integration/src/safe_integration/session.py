"""SAFE session lifecycle — consent management for data streams.

Each app defines its own APP_STREAMS list. SAFESession manages the
consent state machine: start -> grant/deny per stream -> revoke -> end.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List


class SAFESession:
    """Manages SAFE session lifecycle and consent for data streams."""

    def __init__(self, session_id: str, app_streams: List[Dict] = None):
        self.session_id = session_id
        self.started_at = datetime.now()
        self.consents: Dict[str, Dict] = {}
        self.active = True
        self.app_streams = app_streams or []

    def on_session_start(self) -> Dict:
        return {
            "session_id": self.session_id,
            "authorization_requests": self.app_streams,
        }

    def on_consent_granted(self, stream_id: str, granted: bool) -> Dict:
        self.consents[stream_id] = {
            "granted": granted,
            "timestamp": datetime.now().isoformat(),
        }
        stream = next((s for s in self.app_streams if s["stream_id"] == stream_id), None)
        if stream and stream.get("required") and not granted:
            return {
                "status": "consent_required",
                "message": f"This app requires consent for '{stream_id}' to function.",
            }
        if not granted:
            return {"status": "limited_mode", "message": f"'{stream_id}' disabled."}
        return {"status": "ok"}

    def can_access_stream(self, stream_id: str) -> bool:
        return self.consents.get(stream_id, {}).get("granted", False)

    def on_session_end(self) -> Dict:
        self.active = False
        actions = []
        for stream in self.app_streams:
            sid = stream["stream_id"]
            if not self.can_access_stream(sid):
                continue
            retention = stream.get("retention", "session")
            if retention == "session":
                actions.append({"action": "delete", "stream": sid, "reason": "session_ended"})
            else:
                actions.append({"action": "retain", "stream": sid, "reason": "permanent_consent"})
        return {
            "session_id": self.session_id,
            "ended_at": datetime.now().isoformat(),
            "duration_seconds": (datetime.now() - self.started_at).total_seconds(),
            "cleanup_actions": actions,
        }

    def on_revoke(self, stream_id: str) -> Dict:
        if stream_id in self.consents:
            self.consents[stream_id]["granted"] = False
            self.consents[stream_id]["revoked_at"] = datetime.now().isoformat()
        return {"status": "revoked", "stream": stream_id, "action": "data_deleted"}
