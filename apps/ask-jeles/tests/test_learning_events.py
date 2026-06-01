"""Learning event schema and local write."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from askjeles.learning_events import append_event, build_event, record_event


def test_build_event_has_schema():
    ev = build_event(
        event_type="search",
        query="vespa scooters",
        consent_granted_at=datetime.now(timezone.utc),
        query_class="general",
    )
    assert ev["schema"] == "ask_jeles.learning_event.v1"
    assert ev["event_type"] == "search"
    assert ev["consent"]["scope"] == "session"


def test_record_event_writes_jsonl(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("askjeles.learning_events._event_dir", lambda: tmp_path)
    ev = build_event(
        event_type="trivia",
        query="demo",
        consent_granted_at=datetime.now(timezone.utc),
        result_summary={"score": 10, "total": 4},
    )
    result = record_event(ev)
    assert result.ok
    path = Path(result.local_path)
    assert path.exists()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    loaded = json.loads(lines[0])
    assert loaded["event_type"] == "trivia"
