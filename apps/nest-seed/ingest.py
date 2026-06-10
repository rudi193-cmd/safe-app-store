"""
nest-seed/ingest.py — walk a folder, OCR/extract, classify, write to Nest DB.
"""
from __future__ import annotations

import sys
from pathlib import Path

from apps.nest_seed import db as _db
from apps.nest_seed import ocr as _ocr
from apps.nest_seed import classify as _classify


def run(folder: Path, db_path: Path, owner: str, dry_run: bool = False,
        verbose: bool = False) -> dict:
    conn = None if dry_run else _db.open_db(db_path)
    if conn:
        _db.init_meta(conn, owner=owner, description=f"Seeded from {folder}")

    supported = _ocr.supported_suffixes()
    files = [p for p in sorted(folder.rglob("*"))
             if p.is_file() and p.suffix.lower() in supported]

    counts = {"files": 0, "extracted": 0, "failed": 0, "fragments": 0, "skipped": 0}

    for path in files:
        counts["files"] += 1
        if verbose:
            print(f"  [{counts['files']}/{len(files)}] {path.relative_to(folder)}", file=sys.stderr)

        text, method = _ocr.extract(path)

        if method.startswith("missing:") or method == "unsupported":
            counts["skipped"] += 1
            if conn:
                sid = _db.add_source(conn, path, mime_hint=path.suffix.lower())
                _db.update_source_status(conn, sid, "skipped", ocr_method=method)
            continue

        if any(method.startswith(p) for p in ("read_error", "ocr_error", "pdf_error", "docx_error")):
            counts["failed"] += 1
            if conn:
                sid = _db.add_source(conn, path, mime_hint=path.suffix.lower())
                _db.update_source_status(conn, sid, "failed", ocr_method=method, error=method)
            continue

        counts["extracted"] += 1
        frags = _classify.classify(text, filename=path.name)
        counts["fragments"] += len(frags)

        if verbose:
            print(f"    OK  {method} → {len(frags)} fragments", file=sys.stderr)

        if dry_run:
            for f in frags:
                print(f"  {f.fragment_type:12} [{f.confidence:12}] {f.content[:80]!r}")
            continue

        sid = _db.add_source(conn, path, mime_hint=path.suffix.lower())
        _db.update_source_status(conn, sid, "extracted", ocr_method=method, char_count=len(text))
        for f in frags:
            _db.add_fragment(conn, source_id=sid, fragment_type=f.fragment_type,
                             content=f.content, label=f.label, confidence=f.confidence,
                             date_ref=f.date_ref)

    if conn:
        counts["db_stats"] = _db.stats(conn)
        conn.close()

    return counts
