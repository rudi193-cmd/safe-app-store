"""
safe_integration.py — Law Gazelle SAFE Session Hooks

SAFE framework integration. Manages consent, session lifecycle, and data access
gating for Law Gazelle legal assistant.
"""

import sys
from pathlib import Path

# Add gazelle engine
sys.path.insert(0, str(Path(__file__).parent))
from gazelle_engine import create_session, delete_session, get_session

class SAFESession:
    """Law Gazelle SAFE session. Enforces consent before any data is stored."""

    def __init__(self, user_name: str):
        self.user_name = user_name
        self.session_id = None
        self.consent_given = False

    def on_session_start(self) -> dict:
        """Called when user opens Law Gazelle. Returns consent prompt."""
        return {
            "status": "awaiting_consent",
            "message": (
                "Law Gazelle helps you understand your legal situation and prepare documents. "
                "Your conversation is stored locally on your device only. "
                "No data is sent to external servers except anonymized legal questions "
                "to a free AI service for plain-language explanations. "
                "You can delete all your data at any time."
            ),
            "data_streams": [
                {"id": "conversation", "retention": "session", "description": "Your legal issue description and Q&A"},
                {"id": "documents", "retention": "session", "description": "Generated documents (demand letters, forms)"},
                {"id": "patterns", "retention": "permanent", "description": "Issue type patterns (anonymized) for improving classification"},
            ],
            "user_name": self.user_name,
        }

    def on_consent_granted(self) -> dict:
        """Called when user accepts data policy. Creates session."""
        self.consent_given = True
        result = create_session(self.user_name)
        self.session_id = result["session_id"]
        return {
            "status": "active",
            "session_id": self.session_id,
            "message": "Session started. Describe your legal situation and I'll help you understand your options and prepare any needed documents.",
        }

    def can_access_stream(self, stream_id: str) -> bool:
        """Gate data access by consent."""
        if not self.consent_given:
            return False
        # patterns stream always allowed after consent (anonymized only)
        return True

    def on_session_end(self, keep_documents: bool = False) -> dict:
        """Called when user closes the app. Deletes session data unless keep requested."""
        if self.session_id and not keep_documents:
            delete_session(self.session_id)
            return {"status": "deleted", "message": "All session data deleted."}
        return {"status": "retained", "message": "Documents retained locally."}

    def on_revoke(self) -> dict:
        """User explicitly revokes consent. Full cascade delete."""
        if self.session_id:
            delete_session(self.session_id)
        self.consent_given = False
        self.session_id = None
        return {"status": "revoked", "message": "All Law Gazelle data has been deleted."}


# ── Willow Consent Helpers ────────────────────────────────────────────────────

def get_consent_status(token=None):
    return False


def request_consent_url():
    return None



def send(to_app, subject, body, thread_id=None):
    return {"ok": False, "error": "messaging not available in portless mode"}


def check_inbox(unread_only=True):
    return []

