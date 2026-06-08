"""
SAFE Framework Integration
===========================
Session hooks and consent management for SAFE-compliant apps.
"""

from typing import Dict, List, Optional
from datetime import datetime


class SAFESession:
    """Manages SAFE session lifecycle and consent."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.started_at = datetime.now()
        self.consents = {}
        self.active = True

    def on_session_start(self) -> Dict:
        """
        Called when user opens the app.
        Returns authorization requests for each data stream.
        """
        return {
            "session_id": self.session_id,
            "authorization_requests": [
                {
                    "stream_id": "profiles",
                    "purpose": "Analyze dating profiles from screenshots or text",
                    "retention": "session",
                    "required": True,
                    "prompt": "May I analyze dating profiles this session?"
                },
                {
                    "stream_id": "patterns",
                    "purpose": "Learn your personal red flag patterns",
                    "retention": "permanent",
                    "required": False,
                    "prompt": "May I save pattern data to improve future analyses?"
                }
            ]
        }

    def on_consent_granted(self, stream_id: str, granted: bool):
        """
        Called when user grants or denies consent for a data stream.
        """
        self.consents[stream_id] = {
            "granted": granted,
            "timestamp": datetime.now().isoformat()
        }

        # If profiles denied, app cannot function
        if stream_id == "profiles" and not granted:
            return {
                "status": "consent_required",
                "message": "Profile analysis requires consent to process data this session."
            }

        # If patterns denied, can still analyze but won't learn
        if stream_id == "patterns" and not granted:
            return {
                "status": "limited_mode",
                "message": "Pattern learning disabled. Analyses will not improve over time."
            }

        return {"status": "ok"}

    def can_access_stream(self, stream_id: str) -> bool:
        """Check if app has consent to access a data stream."""
        return self.consents.get(stream_id, {}).get("granted", False)

    def on_session_end(self) -> Dict:
        """
        Called when user closes the app.
        Deletes session-retention data, keeps permanent data if consented.
        """
        self.active = False

        actions = []

        # Delete profile data (session retention)
        if self.can_access_stream("profiles"):
            actions.append({
                "action": "delete",
                "stream": "profiles",
                "reason": "session_ended"
            })

        # Keep pattern data (permanent retention, if consented)
        if self.can_access_stream("patterns"):
            actions.append({
                "action": "retain",
                "stream": "patterns",
                "reason": "permanent_consent"
            })

        return {
            "session_id": self.session_id,
            "ended_at": datetime.now().isoformat(),
            "duration_seconds": (datetime.now() - self.started_at).total_seconds(),
            "cleanup_actions": actions
        }

    def on_revoke(self, stream_id: str):
        """
        User revokes consent mid-session.
        Immediately delete associated data.
        """
        if stream_id in self.consents:
            self.consents[stream_id]["granted"] = False
            self.consents[stream_id]["revoked_at"] = datetime.now().isoformat()

        return {
            "status": "revoked",
            "stream": stream_id,
            "action": "data_deleted"
        }


# Example usage
if __name__ == "__main__":
    session = SAFESession("session-001")

    # 1. Session starts - request consent
    auth_requests = session.on_session_start()
    print("Authorization requests:", auth_requests)

    # 2. User grants consent
    session.on_consent_granted("profiles", granted=True)
    session.on_consent_granted("patterns", granted=True)

    # 3. Check access during session
    print("Can analyze profiles:", session.can_access_stream("profiles"))
    print("Can learn patterns:", session.can_access_stream("patterns"))

    # 4. Session ends - cleanup
    cleanup = session.on_session_end()
    print("Cleanup actions:", cleanup)


# ── Willow Consent Helpers ────────────────────────────────────────────────────

def _drop(topic: str, payload: dict) -> dict:
    return {"ok": False, "error": "portless mode — porch removed"}


def get_consent_status(token=None):
    return False


def request_consent_url():
    return None


def send(to_app, subject, body, thread_id=None):
    return {"ok": False, "error": "messaging not available in portless mode"}


def check_inbox(unread_only=True):
    return []

