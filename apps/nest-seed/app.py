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
import os
import sys
from pathlib import Path

from vault_paths import resolve as _vault_resolve  # shared resolver (box audit A5)

# Default output DB derives from the vault root (installer design D8);
# NEST_SEED_DB overrides, and --db still overrides per-invocation.
_DEFAULT_DB = str(_vault_resolve("nest-seed", "seed.db", env_vars=("NEST_SEED_DB",)))

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
    parser.add_argument("--folder", help="Path to the dump folder "
                        "(omit with --digest to just report on an existing --db)")
    parser.add_argument("--db", default=_DEFAULT_DB,
                        help="Output Nest SQLite DB (default: $WILLOW_STORE_ROOT/nest-seed/seed.db)")
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
    parser.add_argument("--digest", action="store_true",
                        help="Write/print a one-page Markdown map of the Nest DB "
                             "(runs after ingest, or standalone on an existing --db).")
    parser.add_argument("--ask", metavar="QUERY", default=None,
                        help="Semantic search: return the fragments most relevant to "
                             "QUERY (builds a cached index; standalone on an existing --db).")
    parser.add_argument("--reindex", action="store_true",
                        help="Rebuild the --ask embedding index from scratch.")
    parser.add_argument("--curate", action="store_true",
                        help="List the auto-discovered categories (store + live DB counts).")
    parser.add_argument("--curate-rename", nargs=2, metavar=("OLD", "NEW"), default=None,
                        help="Rename a discovered category and relabel its DB fragments.")
    parser.add_argument("--curate-prune", metavar="NAME", default=None,
                        help="Drop a discovered category and clear its fragment labels.")
    parser.add_argument("--bridge", action="store_true",
                        help="Emit a PII-safe fleet-KB manifest of the Nest's curated "
                             "structure (counts + category names, never content).")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.db).expanduser().resolve()
    curate_ops = args.curate or args.curate_rename or args.curate_prune or args.bridge
    report_only = (args.digest or args.ask or curate_ops) and not args.folder

    if not report_only:
        if not args.folder:
            sys.exit("ERROR: --folder is required (or use --digest / --ask / "
                     "--curate / --bridge on an existing --db)")
        _ingest(args, db_path)

    if curate_ops:
        _run_curate(db_path, args)

    if args.ask:
        _run_ask(db_path, args.ask, args.reindex)

    if args.digest:
        _write_digest(db_path)


def _run_curate(db_path: "Path", args) -> None:
    try:
        from . import curate as _curate
        from . import bridge as _bridge
    except ImportError:
        import curate as _curate
        import bridge as _bridge
    dbp = str(db_path)

    if args.curate_rename:
        old, new = args.curate_rename
        print(json.dumps(_curate.rename_category(dbp, old, new), indent=2))
    if args.curate_prune:
        print(json.dumps(_curate.prune_category(dbp, args.curate_prune), indent=2))
    if args.curate or (not args.curate_rename and not args.curate_prune and not args.bridge):
        res = _curate.list_categories(dbp)
        print(f'\n🗂️  Discovered categories ({res["count"]}) — rename the keepers, prune the junk:\n')
        for c in res["categories"]:
            coh = f"coh {c['cohesion']}" if c["cohesion"] is not None else "coh ?"
            print(f"  {c['name']}")
            print(f"      size {c['size']} · {coh} · {c['db_fragments']} DB fragments")
            if c["representative"]:
                print(f"      e.g. {c['representative']}")
    if args.bridge:
        res = _bridge.write_manifest(dbp)
        print(f'\n🌉 Bridge manifest: {len(res["atoms"])} PII-safe atoms '
              f'({res["sources"]} sources, {res["fragments"]:,} fragments)')
        if res.get("manifest"):
            print(f"   written to {res['manifest']}", file=sys.stderr)
        for a in res["atoms"]:
            print(f"   • {a['title']}")


def _run_ask(db_path: "Path", query: str, reindex: bool) -> None:
    try:
        from .ask import ask as _ask
    except ImportError:
        from ask import ask as _ask
    res = _ask(str(db_path), query, rebuild=reindex)
    if res.get("status") != "ok":
        print(f"[nest-seed] ask    : {res}", file=sys.stderr)
        return
    print(f'\n🔎 "{query}"  ({res["indexed"]} fragments indexed)\n')
    for h in res["hits"]:
        tag = f"{h['fragment_type']}/{h['label']}" if h['label'] else h['fragment_type']
        print(f"  [{h['score']:.3f}] {h['source']}  ({tag})")
        print(f"          {h['snippet'][:120].strip()}")


def _write_digest(db_path: "Path") -> None:
    try:
        from .digest import build_digest
    except ImportError:
        from digest import build_digest
    out = build_digest(str(db_path))
    target = db_path.parent / "NEST_DIGEST.md"
    try:
        target.write_text(out)
        print(f"\n[nest-seed] digest : {target}", file=sys.stderr)
    except OSError:
        pass
    print(out)


def _ingest(args, db_path: "Path") -> None:
    folder = Path(args.folder).expanduser().resolve()
    if not folder.is_dir():
        sys.exit(f"ERROR: {folder} is not a directory")

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
