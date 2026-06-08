"""
session.py — JSONL session writer, compatible with session_reader.py format.
b17: 2CB01  ΔΣ=42
"""
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

_SESSION_DIR_ENV = "RATATOSK_SESSION_DIR"

VERSION = "ratatosk-1.0"


def _default_session_dir() -> Path:
    # Mirror Claude Code's project-dir convention: cwd path with separators
    # collapsed to dashes, under ~/.claude/projects/.
    slug = str(Path.cwd()).replace("/", "-")
    return Path.home() / ".claude" / "projects" / slug


def _session_dir() -> Path:
    env = os.environ.get(_SESSION_DIR_ENV)
    d = Path(env) if env else _default_session_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


class SessionWriter:
    def __init__(self, cwd: str = ""):
        self.session_id = str(uuid.uuid4())
        self.cwd = cwd or str(Path.cwd())
        self.path = _session_dir() / f"{self.session_id}.jsonl"
        self._last_uuid: str | None = None

    def _entry(self, etype: str, **extra) -> dict:
        entry_uuid = str(uuid.uuid4())
        entry = {
            "uuid": entry_uuid,
            "parentUuid": self._last_uuid,
            "type": etype,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "isSidechain": False,
            "sessionId": self.session_id,
            "cwd": self.cwd,
            "version": VERSION,
        }
        entry.update(extra)
        return entry

    def write(self, entry: dict) -> None:
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        self._last_uuid = entry["uuid"]

    def write_user(self, text: str) -> None:
        self.write(self._entry("user", message={"role": "user", "content": text}))

    def write_assistant(self, text: str) -> None:
        self.write(self._entry("assistant", message={"role": "assistant", "content": text}))
