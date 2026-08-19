"""UTETY Chat session — extends SAFESession with app-specific streams and save."""
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict

from safe_integration.session import SAFESession

_APP_ID = "utety-chat"
_APP_DATA = Path(os.path.expanduser("~")) / ".willow" / "apps" / _APP_ID

APP_STREAMS = [
    {
        "stream_id": "chat_history",
        "purpose": "Maintain conversation context during this session",
        "retention": "session",
        "required": True,
        "prompt": "May I remember our conversation while the app is open?",
    },
    {
        "stream_id": "saved_conversations",
        "purpose": "Save conversations you explicitly choose to keep",
        "retention": "permanent",
        "required": False,
        "prompt": "May I save conversations when you click 'Save'?",
    },
    {
        "stream_id": "persona_preferences",
        "purpose": "Remember which professors you talk to most",
        "retention": "permanent",
        "required": False,
        "prompt": "May I remember your professor preferences?",
    },
]


class UTETYSession(SAFESession):
    def __init__(self, session_id: str):
        super().__init__(session_id, app_streams=APP_STREAMS)
        self.chat_sessions: Dict = {}

    def save_conversation(self, professor_name: str, conversation_md: str) -> Dict:
        if not self.can_access_stream("saved_conversations"):
            return {"error": "No consent to save conversations", "status": "denied"}

        save_dir = _APP_DATA / "saved_conversations"
        save_dir.mkdir(parents=True, exist_ok=True)

        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '', professor_name)
        if not safe_name:
            safe_name = "conversation"

        filename = f"{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        filepath = (save_dir / filename).resolve()

        if filepath.parent != save_dir.resolve():
            return {"error": "Invalid conversation name", "status": "denied"}

        filepath.write_text(conversation_md, encoding="utf-8")
        return {"status": "saved", "filename": filename, "path": str(filepath)}
