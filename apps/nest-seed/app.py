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
    from . import embed as _embed
except ImportError:
    from ingest import run
    import llm as _llm
    import embed as _embed


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
    parser.add_argument("--no-embed", action="store_true",
                        help="Disable the semantic embedding tier (nomic-embed-text). "
                             "On by default when the model is available.")
    parser.add_argument("--embed-model", default=None,
                        help="Ollama embedding model (default: env NEST_EMBED_MODEL or nomic-embed-text)")
    parser.add_argument("--learn", action="store_true",
                        help="Self-learning: fold this run's confidently-classified files "
                             "into the category centroids so the Nest adapts to your data.")
    parser.add_argument("--discover", type=int, metavar="K", default=0,
                        help="Cluster the uncertain tail into K groups to surface "
                             "candidate categories the exemplars miss (report only).")
    parser.add_argument("--promote", action="store_true",
                        help="Persist qualifying tail clusters as new categories "
                             "(big, cohesive, novel) so future runs classify into them.")
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
    use_embed = not args.no_embed
    if use_embed:
        em = args.embed_model or _embed.DEFAULT_EMBED_MODEL
        ok = _embed.available(em)
        print(f"[nest-seed] embed  : {'ON' if ok else 'requested but model unavailable — tier off'}"
              f" ({em})", file=sys.stderr)
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
                 use_llm=args.llm, use_embed=use_embed, text_model=args.text_model,
                 vision_model=args.vision_model, embed_model=args.embed_model,
                 learn=args.learn, discover=args.discover, promote=args.promote)

    print(f"\n[nest-seed] files    : {counts['files']}", file=sys.stderr)
    print(f"[nest-seed] extracted: {counts['extracted']}", file=sys.stderr)
    print(f"[nest-seed] failed   : {counts['failed']}", file=sys.stderr)
    print(f"[nest-seed] skipped  : {counts['skipped']}", file=sys.stderr)
    print(f"[nest-seed] fragments: {counts['fragments']}", file=sys.stderr)
    if "db_stats" in counts:
        print(f"[nest-seed] db stats : {json.dumps(counts['db_stats'])}", file=sys.stderr)
    if "learned" in counts:
        print(f"[nest-seed] learned  : {json.dumps(counts['learned'])}", file=sys.stderr)
    if "discovery" in counts:
        print(f"[nest-seed] discovery: {json.dumps(counts['discovery'])}", file=sys.stderr)
    if "promotion" in counts:
        print(f"[nest-seed] promotion: {json.dumps(counts['promotion'])}", file=sys.stderr)


if __name__ == "__main__":
    main()
