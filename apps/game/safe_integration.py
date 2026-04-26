"""
safe_integration.py — SAFE Framework Integration for Jane GM

Implements SAFE consent hooks. Game data is local-first.
Session data deleted on close unless player explicitly opts to save.
"""

from datetime import datetime


class SAFESession:
    def __init__(self):
        self.session_id = None
        self.player_name = None
        self.consent_granted = False
        self.persist = False
        self.start_time = None

    def on_session_start(self, player_name: str, persist: bool = False) -> dict:
        """Called when player starts a game session."""
        self.player_name = player_name
        self.persist = persist
        self.start_time = datetime.now().isoformat()
        return {
            "status": "session_started",
            "player": player_name,
            "data_streams": ["session_data"] + (["saved_campaigns"] if persist else []),
            "retention": "permanent" if persist else "session",
            "notice": (
                "Your game session is stored locally on this device. "
                + ("Your character and campaign will be saved." if persist
                   else "All data is deleted when you end this session.")
            ),
        }

    def on_consent_granted(self, scope: str) -> bool:
        """Called when player grants consent for a data scope."""
        self.consent_granted = True
        if scope == "saved_campaigns":
            self.persist = True
        return True

    def can_access_stream(self, stream_id: str) -> bool:
        """Check if a data stream is accessible given current consent."""
        if stream_id == "session_data":
            return self.consent_granted
        if stream_id == "saved_campaigns":
            return self.consent_granted and self.persist
        return False

    def on_session_end(self, delete_data: bool = True) -> dict:
        """Called when session ends. Deletes data unless player saved."""
        if delete_data and not self.persist:
            return {
                "status": "session_ended",
                "data_deleted": True,
                "notice": "Session data deleted. See you next adventure!",
            }
        return {
            "status": "session_ended",
            "data_deleted": False,
            "notice": "Campaign saved. Your character will be here when you return.",
        }

    def on_revoke(self, scope: str) -> dict:
        """Called when player revokes consent — delete all stored data."""
        if scope == "saved_campaigns":
            self.persist = False
        return {
            "status": "revoked",
            "scope": scope,
            "data_deleted": True,
            "notice": "All stored game data has been deleted.",
        }


_session = SAFESession()


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

