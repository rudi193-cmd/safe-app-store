#!/usr/bin/env python3
"""
commit_package.py — Write a law_gazelle_commit.json manifest to Nest.

Signals to nest_watcher that a legal build session is ready for fleet pickup.
Writes to ~/Desktop/Nest/ (or $NEST_SOURCE).

b17: LGCP1  ΔΣ=42

Usage:
    commit_package.py [--summary "text"] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

NEST_SOURCE = Path(os.environ.get("NEST_SOURCE", Path.home() / "Desktop" / "Nest"))

CASE_FILES = [
    "coparent.db",
    "bankruptcy.db",
    "workers_comp.db",
    "session_meta.db",
    "coparent_db_export.json",
]

LETTER_GLOB = "Campbell_Letter*.docx"
# Dated filename ensures nest_watcher re-detects each session (queue tracks by path).
MANIFEST_NAME_TEMPLATE = "legal_commit_{date}.json"


def _find_artifacts(nest: Path) -> list[str]:
    present = []
    for name in CASE_FILES:
        if (nest / name).exists():
            present.append(name)
    for p in sorted(nest.glob(LETTER_GLOB)):
        present.append(p.name)
    return present


def build_manifest(nest: Path, summary: str, session_date: str) -> dict:
    files = _find_artifacts(nest)
    return {
        "kind": "law_gazelle_commit",
        "status": "prepared",
        "committed_at": datetime.now(timezone.utc).isoformat(),
        "session_date": session_date,
        "case_number": "D-000-DM-0000-00000",
        "files": files,
        "summary": summary,
    }


def write_manifest(manifest: dict, nest: Path, session_date: str, dry_run: bool = False) -> Path:
    name = MANIFEST_NAME_TEMPLATE.format(date=session_date)
    dest = nest / name
    payload = json.dumps(manifest, indent=2)
    if dry_run:
        print("[dry-run] Would write to:", dest)
        print(payload)
    else:
        dest.write_text(payload, encoding="utf-8")
        print(f"Manifest written: {dest}")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description="Commit law-gazelle Nest package")
    parser.add_argument("--summary", default="", help="One-line session summary")
    parser.add_argument("--session-date", default="", help="Session date e.g. 2026-05-24")
    parser.add_argument("--dry-run", action="store_true", help="Print manifest, don't write")
    parser.add_argument("--nest", default=str(NEST_SOURCE), help="Nest directory override")
    args = parser.parse_args()

    nest = Path(args.nest)
    if not nest.exists():
        print(f"[error] Nest not found: {nest}", file=sys.stderr)
        sys.exit(1)

    session_date = args.session_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    summary = args.summary or f"Law Gazelle session {session_date}"

    manifest = build_manifest(nest, summary, session_date)
    write_manifest(manifest, nest, session_date=session_date, dry_run=args.dry_run)

    files_found = manifest["files"]
    print(f"Files included: {len(files_found)}")
    for f in files_found:
        print(f"  {f}")

    if not args.dry_run:
        print()
        print("nest_watcher will pick up law_gazelle_commit.json → #heimdallr")
        print("Then run: ./dev.sh  (syncs Nest → cases/ on launch)")


if __name__ == "__main__":
    main()
