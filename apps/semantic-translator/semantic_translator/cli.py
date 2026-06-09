"""CLI entry point for semantic-translator."""
from __future__ import annotations

import argparse
import sys


def cmd_scrape(args: argparse.Namespace) -> None:
    from .scraper import scrape
    scrape(output_path=args.output)


def cmd_ingest(args: argparse.Namespace) -> None:
    from .ingest import ingest
    ingest(corpus_path=args.corpus, log_path=args.log, delay=args.delay)


def cmd_query(args: argparse.Namespace) -> None:
    from .search import search, format_result
    print(f"Searching: {args.text!r}\n")
    try:
        results = search(args.text, limit=args.limit)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    if not results:
        print("No results found.")
        return
    for i, r in enumerate(results, 1):
        print(format_result(r, i))
        print()


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn
    from .server import app
    print(f"Starting server at http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)


def cmd_tui(_args: argparse.Namespace) -> None:
    from .tui import TranslatorApp
    TranslatorApp().run()


def cmd_stats(_args: argparse.Namespace) -> None:
    import json
    import pathlib
    from . import db as _db
    _db.init_db()

    corpus = pathlib.Path("data/corpus.jsonl")
    if corpus.exists():
        lessons: set[str] = set()
        langs: dict[str, int] = {}
        count = 0
        with open(corpus, encoding="utf-8") as f:
            for line in f:
                seg = json.loads(line)
                lessons.add(seg["lesson"])
                langs[seg["lang"]] = langs.get(seg["lang"], 0) + 1
                count += 1
        print(f"Corpus: {corpus}")
        print(f"  segments : {count}")
        print(f"  lessons  : {len(lessons)}")
        for lang, n in sorted(langs.items()):
            print(f"  {lang:<8}: {n}")

    docs = _db.list_documents()
    if docs:
        print(f"\nDocuments: {len(docs)}")
        for d in docs:
            segs = _db.get_segments(d["id"])
            verified = sum(1 for s in segs if s["status"] == "verified")
            print(f"  [{d['status']:<14}] {d['title']!r}  {verified}/{len(segs)} verified")

    pending = _db.pending_count()
    print(f"\nReview queue: {pending} segments pending")


# ── translate ────────────────────────────────────────────────────────────────

def cmd_translate(args: argparse.Namespace) -> None:
    from .translator import translate_document
    translate_document(
        path=args.file,
        source_lang=args.source,
        target_lang=args.target,
    )


# ── export ───────────────────────────────────────────────────────────────────

def cmd_export(args: argparse.Namespace) -> None:
    from .translator import export_document
    text = export_document(args.doc_id, output_path=args.output)
    if not args.output:
        print(text)


# ── learner management ───────────────────────────────────────────────────────

def cmd_learner(args: argparse.Namespace) -> None:
    from . import db
    db.init_db()

    if args.learner_cmd == "add":
        learner = db.create_learner(
            name=args.name,
            native_lang=args.native,
            target_lang=args.target,
        )
        print(f"Learner created: {learner['name']}  id={learner['id']}")
    elif args.learner_cmd == "list":
        learners = db.list_learners()
        if not learners:
            print("No learners yet.  Run: semantic-translator learner add <name>")
            return
        for l in learners:
            stats = db.card_stats(l["id"])
            print(
                f"  {l['name']:<20} id={l['id'][:8]}  "
                f"cal={l['calibration_score']:.2f}  "
                f"cards={stats['total']}  due={stats['due']}"
            )


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="semantic-translator",
        description="Semantic translation memory for Emerging Rule curriculum",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("scrape", help="Pull lessons from GitHub → corpus JSONL")
    p.add_argument("--output", default="data/corpus.jsonl", metavar="PATH")
    p.set_defaults(func=cmd_scrape)

    p = sub.add_parser("ingest", help="Ingest corpus segments into Jeles")
    p.add_argument("--corpus", default="data/corpus.jsonl", metavar="PATH")
    p.add_argument("--log", default="data/ingest_log.jsonl", metavar="PATH")
    p.add_argument("--delay", type=float, default=0.15, metavar="SECS")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("query", help="Semantic search over ingested corpus")
    p.add_argument("text", help="Text to find semantic matches for")
    p.add_argument("--limit", type=int, default=5, metavar="N")
    p.set_defaults(func=cmd_query)

    p = sub.add_parser("translate", help="Translate a document via Jeles semantic search")
    p.add_argument("file", help="Path to source document (.txt)")
    p.add_argument("--source", default="en", metavar="LANG")
    p.add_argument("--target", default="es", metavar="LANG")
    p.set_defaults(func=cmd_translate)

    p = sub.add_parser("export", help="Export a verified document")
    p.add_argument("doc_id", help="Document ID (from translate output)")
    p.add_argument("--output", default="", metavar="PATH",
                   help="Write to file (default: stdout)")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("review", help="Launch TUI review queue")
    p.set_defaults(func=cmd_tui)

    p = sub.add_parser("tui", help="Launch full TUI")
    p.set_defaults(func=cmd_tui)

    p = sub.add_parser("serve", help="Start FastAPI web server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8432)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("stats", help="Show corpus + document statistics")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("learner", help="Manage learners")
    lsub = p.add_subparsers(dest="learner_cmd", required=True)
    la = lsub.add_parser("add", help="Register a new learner")
    la.add_argument("name")
    la.add_argument("--native", default="en", metavar="LANG")
    la.add_argument("--target", default="es", metavar="LANG")
    lsub.add_parser("list", help="List all learners")
    p.set_defaults(func=cmd_learner)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
