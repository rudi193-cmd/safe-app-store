#!/usr/bin/env python3
"""
commit_package.py — CLI wrapper for Nest commit manifest.

Usage:
    commit_package.py [--summary "text"] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as script from repo
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import case_store
import commit_package as cp


def main() -> None:
    parser = argparse.ArgumentParser(description="Commit law-gazelle Nest package")
    parser.add_argument("--summary", default="", help="One-line session summary")
    parser.add_argument("--session-date", default="", help="Session date e.g. 2099-05-24")
    parser.add_argument("--dry-run", action="store_true", help="Print manifest, don't write")
    parser.add_argument("--nest", default=str(case_store.DEFAULT_SOURCE), help="Nest directory override")
    args = parser.parse_args()

    result = cp.write_commit_manifest(
        summary=args.summary,
        session_date=args.session_date,
        nest=args.nest,
        dry_run=args.dry_run,
    )

    if not result.get("ok"):
        print(f"[error] {result.get('error')}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print("[dry-run] Would write to:", result["path"])
        print(json.dumps(result["manifest"], indent=2))
    else:
        print(f"Manifest written: {result['path']}")

    for f in result["manifest"]["files"]:
        print(f"  {f}")

    if not args.dry_run:
        print()
        print("nest_watcher should pick up legal_commit_*.json")
        print("Then run: ./dev.sh  (syncs Nest → cases/ on launch)")


if __name__ == "__main__":
    main()
