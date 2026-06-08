"""Session-consented learning-event capture for Ask Jeles."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional


SCHEMA = "ask_jeles.learning_event.v1"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _event_dir() -> Path:
    root = Path.home() / ".willow" / "jeles_learning_events"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _event_path(day: Optional[date] = None) -> Path:
    d = day or _utc_now().date()
    return _event_dir() / f"{d.isoformat()}.jsonl"


def build_event(
    *,
    event_type: str,
    query: str,
    consent_granted_at: datetime,
    query_class: str = "",
    sources_used: Optional[list[str]] = None,
    backend: str = "",
    result_summary: Optional[dict[str, Any]] = None,
    pedagogy: Optional[dict[str, Any]] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build a single v1 learning event block (JSON-serializable)."""

    created_at = _utc_now()
    event: dict[str, Any] = {
        "schema": SCHEMA,
        "event_id": str(uuid.uuid4()),
        "created_at": _iso(created_at),
        "app_id": "ask-jeles",
        "consent": {"scope": "session", "granted_at": _iso(consent_granted_at)},
        "event_type": event_type,
        "query": (query or "").strip(),
    }
    if query_class:
        event["query_class"] = query_class
    if sources_used:
        event["sources_used"] = list(sources_used)
    if backend:
        event["backend"] = backend
    if result_summary:
        event["result_summary"] = result_summary
    if pedagogy:
        event["pedagogy"] = pedagogy
    if extra:
        event["extra"] = extra
    return event


def append_event(event: dict[str, Any]) -> Path:
    """Append a single event as one JSON line and return the file path."""
    path = _event_path()
    line = json.dumps(event, ensure_ascii=False) + "\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)
    return path


def stage_to_intake(event: dict[str, Any]) -> dict[str, Any]:
    """Stage the event to Willow intake queue via safe_integration (best effort)."""
    try:
        from safe_integration import contribute

        return contribute(
            json.dumps(event, ensure_ascii=False, indent=2),
            category="jeles_learning_event",
            metadata={
                "schema": event.get("schema"),
                "event_type": event.get("event_type"),
                "query": event.get("query", "")[:200],
            },
        )
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": str(exc)}


@dataclass(frozen=True)
class RecordResult:
    ok: bool
    local_path: Optional[str] = None
    intake: Optional[dict[str, Any]] = None
    error: str = ""


def record_event(event: dict[str, Any]) -> RecordResult:
    """Record event locally + stage to intake. Never raise."""
    try:
        p = append_event(event)
    except Exception as exc:
        return RecordResult(ok=False, error=f"local_write_failed: {exc}")

    intake = stage_to_intake(event)
    return RecordResult(ok=True, local_path=str(p), intake=intake)

