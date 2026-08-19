"""Intake staging — contribute content to the Willow intake queue.

Pattern: Protocol + set_client() injection + filesystem fallback.
With no client injected, stages to ~/.willow/apps/<app_id>/intake/ on disk.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class IntakeClient(Protocol):
    """Anything that can stage content to an intake queue."""

    def contribute(self, content: str, category: str,
                   metadata: dict, app_id: str) -> dict:
        ...


_client: Optional[IntakeClient] = None
_app_id: str = "unknown"


def set_intake_client(client: Optional[IntakeClient], app_id: str = "unknown") -> None:
    global _client, _app_id
    _client = client
    _app_id = app_id


def get_intake_client() -> Optional[IntakeClient]:
    return _client


def contribute(content: str, category: str = "note",
               metadata: Optional[dict] = None, *,
               app_id: Optional[str] = None) -> dict:
    """Stage a contribution. Uses injected client if available, else filesystem."""
    aid = app_id or _app_id
    meta = metadata or {}

    if _client is not None:
        try:
            return _client.contribute(content, category, meta, aid)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    try:
        intake_dir = Path(os.path.expanduser("~")) / ".willow" / "apps" / aid / "intake"
        intake_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        fname = intake_dir / f"{ts}_{uuid.uuid4().hex[:8]}.json"
        fname.write_text(json.dumps({
            "source_app": aid,
            "type": category,
            "content": content,
            "metadata": meta,
            "contributed_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2))
        return {"ok": True, "staged": str(fname)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
