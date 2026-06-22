"""
nest-seed entry point.

Run from the store:   make run app=nest-seed        (needs args, see below)
Run directly:         python apps/nest-seed/app.py --folder ~/life-dump --owner "You"
Or from inside dir:   cd apps/nest-seed && python app.py --folder ~/life-dump

Seeds a portable SQLite Nest DB from a folder of personal files. Pass --llm
to classify content with a local Ollama daemon instead of filename regex.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:  # works both as a package (apps.nest_seed) and as a plain script dir
    from .ingest import run
    from . import llm as _llm
except ImportError:
    from ingest import run
    import llm as _llm


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
    parser.add_argument("--llm", action="store_true",
                        help="Use local AI (Ollama) to classify content, not just filenames. "
                             "Falls back to regex per-file if Ollama is unreachable.")
    parser.add_argument("--text-model", default=None,
                        help="Ollama text model (default: env NEST_TEXT_MODEL or llama3.2:3b)")
    parser.add_argument("--vision-model", default=None,
                        help="Ollama vision model (default: env NEST_VISION_MODEL or qwen2.5vl:7b)")
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
    print(f"[nest-seed] mode   : {'dry-run' if args.dry_run else 'live'}", file=sys.stderr)
    if args.llm:
        models = _llm.installed_models()
        tm = args.text_model or _llm.DEFAULT_TEXT_MODEL
        ok = _llm.available(tm)
        print(f"[nest-seed] llm    : {'ON' if ok else 'requested but Ollama/model unavailable — regex fallback'}"
              f" ({_llm.DEFAULT_HOST}, text={tm})", file=sys.stderr)
        if models and args.verbose:
            print(f"[nest-seed] models : {sorted(models)}", file=sys.stderr)
    print("", file=sys.stderr)

    counts = run(folder, db_path, owner=owner, dry_run=args.dry_run, verbose=args.verbose,
                 use_llm=args.llm, text_model=args.text_model, vision_model=args.vision_model)

    print(f"\n[nest-seed] files    : {counts['files']}", file=sys.stderr)
    print(f"[nest-seed] extracted: {counts['extracted']}", file=sys.stderr)
    print(f"[nest-seed] failed   : {counts['failed']}", file=sys.stderr)
    print(f"[nest-seed] skipped  : {counts['skipped']}", file=sys.stderr)
    print(f"[nest-seed] fragments: {counts['fragments']}", file=sys.stderr)
    if "db_stats" in counts:
        print(f"[nest-seed] db stats : {json.dumps(counts['db_stats'])}", file=sys.stderr)


if __name__ == "__main__":
    main()
