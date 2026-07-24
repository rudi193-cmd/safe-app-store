"""journal.py — append-only JSONL audit log under the vault.

Every recommendation/decision is written with its provenance block (source_ids
+ fetch timestamps). The log is append-only: entries are never mutated or
deleted, and re-opening the journal preserves all prior history. This is the
"why did it do that?" record.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..paths import journal_path


@dataclass
class JournalEntry:
    kind: str                     # e.g. "recommend", "paper_fill", "kill", "live_refused"
    ts: str
    payload: dict
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "ts": self.ts,
            "payload": self.payload,
            "provenance": self.provenance,
        }


class Journal:
    """Append-only JSONL journal. One JSON object per line."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or journal_path()

    @property
    def path(self) -> Path:
        return self._path

    def append(self, kind: str, payload: dict, provenance: dict | None = None) -> JournalEntry:
        entry = JournalEntry(
            kind=kind,
            ts=datetime.now(timezone.utc).isoformat(),
            payload=payload,
            provenance=provenance or {},
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry.to_dict(), sort_keys=True)
        # Append mode + explicit flush/fsync: never rewrite existing content.
        with open(self._path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return entry

    def read_all(self) -> list[JournalEntry]:
        if not self._path.exists():
            return []
        out: list[JournalEntry] = []
        with open(self._path, "r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                d = json.loads(raw)
                out.append(
                    JournalEntry(
                        kind=d["kind"],
                        ts=d["ts"],
                        payload=d.get("payload", {}),
                        provenance=d.get("provenance", {}),
                    )
                )
        return out

    def count(self) -> int:
        return len(self.read_all())
