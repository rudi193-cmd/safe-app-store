"""python -m apps.nest_seed — portable Nest seed CLI."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from apps.nest_seed.ingest import run


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed a portable Nest SQLite DB from a folder of personal files."
    )
    parser.add_argument("--folder", required=True, help="Path to the dump folder")
    parser.add_argument("--db", default="~/Desktop/Nest/seed.db",
                        help="Output Nest SQLite DB (default: ~/Desktop/Nest/seed.db)")
    parser.add_argument("--owner", default="", help="Your name — stored in nest_meta")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print fragments only, do not write DB")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    folder = Path(args.folder).expanduser().resolve()
    if not folder.is_dir():
        sys.exit(f"ERROR: {folder} is not a directory")

    db_path = Path(args.db).expanduser().resolve()
    if not args.dry_run:
        db_path.parent.mkdir(parents=True, exist_ok=True)

    owner = args.owner or folder.parent.name

    print(f"[nest-seed] folder : {folder}", file=sys.stderr)
    if not args.dry_run:
        print(f"[nest-seed] db     : {db_path}", file=sys.stderr)
    print(f"[nest-seed] owner  : {owner}", file=sys.stderr)
    print(f"[nest-seed] mode   : {'dry-run' if args.dry_run else 'live'}\n", file=sys.stderr)

    counts = run(folder, db_path, owner=owner, dry_run=args.dry_run, verbose=args.verbose)

    print(f"\n[nest-seed] files    : {counts['files']}", file=sys.stderr)
    print(f"[nest-seed] extracted: {counts['extracted']}", file=sys.stderr)
    print(f"[nest-seed] failed   : {counts['failed']}", file=sys.stderr)
    print(f"[nest-seed] skipped  : {counts['skipped']}", file=sys.stderr)
    print(f"[nest-seed] fragments: {counts['fragments']}", file=sys.stderr)
    if "db_stats" in counts:
        print(f"[nest-seed] db stats : {json.dumps(counts['db_stats'])}", file=sys.stderr)


if __name__ == "__main__":
    main()
