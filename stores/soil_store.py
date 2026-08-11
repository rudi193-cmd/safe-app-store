#!/usr/bin/env python3
"""stores/soil_store.py — a minimal FilesystemSoilStore backing the vendored
`human_loop` (docs/design/the-forge-human-loop.md, D-HL-2).

`human_loop` (stores/human_loop.py, vendored from willow-mcp) is written over an
INJECTED store with a tiny interface — `put(collection, record, record_id=)`,
`all(collection)`, `get(collection, id)`. willow-mcp homes it in its SOIL store;
Nestor's `SqliteStore` can't (verified: it exposes a document/segment/memory
API, no generic key-value), so the Forge supplies this: one JSON file per
builder, `<root>/<builder_id>.soil.json`, holding `{collection: {id: record}}`.

Same one-file-per-builder isolation and 0700/0600 permission discipline
`checkpoint_memory` (the Nestor db) and `checkpoint_schedule` (the FSRS sidecar)
already use (D6) — a builder's governance records live in that builder's own
file and nowhere else, by construction, not by a domain string a caller could
mis-scope. `builder_id` is validated through `checkpoint_memory._check_builder_id`
(itself principal.py's charset) before it ever becomes a path component, exactly
as `checkpoint_schedule.schedule_path` does.

Store-side (D1): `apps/the-forge/` never imports this; a build's governance
record is not something a sandboxed build writes about itself.

Not a general database: no query language, no indexes, no concurrency control
beyond last-writer-wins on the whole file (a torn write is the same dev-only
risk the sibling `.checkpoints/` JSON stores carry — matched, not widened). It
exists to satisfy `human_loop`'s contract, nothing more.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent.parent

# Reuse checkpoint_memory's validated builder-id check and shared root — one
# source for the charset and the checkpoint root, same as checkpoint_schedule.
# checkpoint_memory is soft-Nestor at import, so this pulls in no Nestor.
_cm_spec = importlib.util.spec_from_file_location(
    "checkpoint_memory", _REPO / "stores" / "checkpoint_memory.py"
)
checkpoint_memory = importlib.util.module_from_spec(_cm_spec)
sys.modules["checkpoint_memory"] = checkpoint_memory
_cm_spec.loader.exec_module(checkpoint_memory)

DEFAULT_CHECKPOINT_ROOT = checkpoint_memory.DEFAULT_CHECKPOINT_ROOT


class SoilStoreError(Exception):
    """Bad builder_id, a symlinked root, an unreadable store file, or a `put`
    with no id to key on. Fail-closed, like the sibling stores."""


class FilesystemSoilStore:
    """One builder's SOIL store — the injected store `human_loop` writes to.

    Construct per builder; pass it to `human_loop.create_attestation` /
    `enqueue` / etc. Records are stored verbatim under `(collection, id)`; this
    store injects no metadata of its own (`human_loop` sets its own `id` and
    `created_at`), so a round trip returns exactly what was put.
    """

    def __init__(self, builder_id: str, root: Path = DEFAULT_CHECKPOINT_ROOT):
        try:
            self.builder_id = checkpoint_memory._check_builder_id(builder_id)
        except checkpoint_memory.CheckpointMemoryError as e:
            raise SoilStoreError(f"builder_id rejected: {e}") from e
        self.root = Path(root)
        if self.root.is_symlink():
            raise SoilStoreError(f"refusing to use a symlinked SOIL root: {self.root}")
        self.path = self.root / f"{self.builder_id}.soil.json"

    # -- the injected-store interface human_loop calls ----------------------

    def put(self, collection: str, record: dict, record_id: str | None = None) -> dict:
        rid = record_id or (record.get("id") if isinstance(record, dict) else None)
        if not rid or not isinstance(rid, str):
            raise SoilStoreError("put needs a record_id (or a record with a str 'id')")
        # A record carrying its own 'id' that disagrees with the key it's stored
        # under is a caller bug that would make get(record_id) and
        # get(record['id']) diverge — refuse it rather than store the footgun.
        inner = record.get("id") if isinstance(record, dict) else None
        if isinstance(inner, str) and inner != rid:
            raise SoilStoreError(f"record_id {rid!r} disagrees with record['id'] {inner!r}")
        data = self._load()
        data.setdefault(collection, {})[rid] = record
        self._save(data)
        return record

    def get(self, collection: str, record_id: str) -> Any | None:
        return self._load().get(collection, {}).get(record_id)

    def all(self, collection: str) -> list:
        return list(self._load().get(collection, {}).values())

    # -- storage ------------------------------------------------------------

    def _reject_symlinked_file(self) -> None:
        """A symlinked leaf file would let builder A's `<a>.soil.json` point at
        builder B's file, so a read or write would cross the one-file-per-builder
        boundary the root-symlink guard alone doesn't close — `write_text`
        follows the link. Checked before every read and write. (Gap named by the
        adversarial audit; the root-symlink guard in __init__ missed the leaf.)"""
        if self.path.is_symlink():
            raise SoilStoreError(f"refusing a symlinked SOIL file: {self.path}")

    def _load(self) -> dict:
        self._reject_symlinked_file()
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError) as e:
            raise SoilStoreError(f"SOIL store for {self.builder_id!r} is unreadable: {e}") from e
        if not isinstance(data, dict):
            raise SoilStoreError(f"SOIL store for {self.builder_id!r} is not a JSON object")
        return data

    def _save(self, data: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        self._reject_symlinked_file()
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True))
        os.chmod(self.path, 0o600)
