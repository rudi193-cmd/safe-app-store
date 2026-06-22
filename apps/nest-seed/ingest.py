"""
nest-seed/ingest.py — walk a folder, OCR/extract, classify, write to Nest DB.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:  # works both as a package (apps.nest_seed) and as a plain script dir
    from . import db as _db
    from . import ocr as _ocr
    from . import classify as _classify
except ImportError:
    import db as _db
    import ocr as _ocr
    import classify as _classify

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"}


def run(folder: Path, db_path: Path, owner: str, dry_run: bool = False,
        verbose: bool = False, use_llm: bool = False,
        text_model: str | None = None, vision_model: str | None = None) -> dict:
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
        is_image = path.suffix.lower() in _IMAGE_EXTS

        # When OCR is unavailable for an image but local vision is on, we can
        # still classify it from pixels — don't skip it.
        vision_rescue = use_llm and is_image and method.startswith("missing:")

        if (method.startswith("missing:") or method == "unsupported") and not vision_rescue:
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
        frags = _classify.classify(text, filename=path.name, path=path,
                                   use_llm=use_llm, text_model=text_model,
                                   vision_model=vision_model)
        counts["fragments"] += len(frags)

        if verbose:
            tag = "vision" if vision_rescue else method
            print(f"    OK  {tag} → {len(frags)} fragments", file=sys.stderr)

        if dry_run:
            for f in frags:
                lab = f" «{f.label}»" if f.label else ""
                print(f"  {f.fragment_type:10}{lab:14} [{f.confidence:11}] {f.content[:80]!r}")
            continue

        sid = _db.add_source(conn, path, mime_hint=path.suffix.lower())
        ocr_label = "vision" if vision_rescue else method
        _db.update_source_status(conn, sid, "extracted", ocr_method=ocr_label, char_count=len(text))
        for f in frags:
            _db.add_fragment(conn, source_id=sid, fragment_type=f.fragment_type,
                             content=f.content, label=f.label, confidence=f.confidence,
                             date_ref=f.date_ref)

    if conn:
        counts["db_stats"] = _db.stats(conn)
        conn.close()

    return counts
