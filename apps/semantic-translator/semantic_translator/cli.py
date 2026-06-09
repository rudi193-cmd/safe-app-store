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
    corpus = pathlib.Path("data/corpus.jsonl")
    if not corpus.exists():
        print("No corpus found — run: semantic-translator scrape")
        return
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
        print(f"  {lang}       : {n}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="semantic-translator",
        description="Semantic translation memory for Emerging Rule curriculum",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("scrape", help="Pull lessons from GitHub and write corpus JSONL")
    p.add_argument("--output", default="data/corpus.jsonl", metavar="PATH")
    p.set_defaults(func=cmd_scrape)

    p = sub.add_parser("ingest", help="Ingest corpus segments into Jeles")
    p.add_argument("--corpus", default="data/corpus.jsonl", metavar="PATH")
    p.add_argument("--log", default="data/ingest_log.jsonl", metavar="PATH")
    p.add_argument("--delay", type=float, default=0.15, metavar="SECS",
                   help="Delay between extract calls (default 0.15)")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("query", help="Semantic search over ingested corpus")
    p.add_argument("text", help="Text to find semantic matches for")
    p.add_argument("--limit", type=int, default=5, metavar="N")
    p.set_defaults(func=cmd_query)

    p = sub.add_parser("serve", help="Start FastAPI web server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8432)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("tui", help="Launch Textual TUI")
    p.set_defaults(func=cmd_tui)

    p = sub.add_parser("stats", help="Show corpus statistics")
    p.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
