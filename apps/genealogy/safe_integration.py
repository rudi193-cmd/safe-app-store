"""SAFE integration stub for the Aionic Genealogy Project."""

import json
import os as _os
import sqlite3 as _sqlite3
_STORE_ROOT = _os.environ.get(
    "WILLOW_STORE_ROOT",
    _os.path.join(_os.path.expanduser("~"), ".willow", "store")
)
import uuid
from pathlib import Path
from datetime import datetime, timezone

APP_ID = "safe-app-genealogy"
_APP_DATA = Path(_os.path.expanduser("~")) / ".willow" / "apps" / APP_ID


def get_manifest():
    manifest_path = Path(__file__).parent / "safe-app-manifest.json"
    return json.loads(manifest_path.read_text())


def contribute(data, stream_id="file_writes"):
    """Stage genealogy data to the Willow intake queue (filesystem, portless)."""
    content = json.dumps(data) if not isinstance(data, str) else data
    try:
        intake_dir = _APP_DATA / "intake"
        intake_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        fname = intake_dir / f"{ts}_{uuid.uuid4().hex[:8]}.json"
        fname.write_text(json.dumps({
            "source_app": APP_ID,
            "type": stream_id,
            "content": content,
            "metadata": {},
            "contributed_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2))
        return {"ok": True, "staged": str(fname)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
