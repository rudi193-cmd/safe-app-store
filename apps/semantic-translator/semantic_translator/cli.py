"""CLI entry point for semantic-translator."""
from __future__ import annotations

import argparse
import sys


def cmd_scrape(args: argparse.Namespace) -> None:
    from .scraper import scrape
    scrape(output_path=args.output, local_dir=args.local)


def cmd_ingest(args: argparse.Namespace) -> None:
    from .ingest import ingest
    ingest(corpus_path=args.corpus, log_path=args.log, delay=args.delay)


def cmd_demo(args: argparse.Namespace) -> None:
    from .demo import seed_demo
    try:
        seed_demo(output_path=args.output, force=args.force)
    except FileExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def cmd_play(args: argparse.Namespace) -> None:
    from .quiz import play
    play(rounds=args.rounds, reverse=args.reverse,
         learner_name=args.learner, seed=args.seed)


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
    from .nestor_wiring import configure_nestor
    from .tui import TranslatorApp
    configure_nestor()
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


# ── nestor (meaning infrastructure prototype) ───────────────────────────────

def cmd_nestor(args: argparse.Namespace) -> None:
    from nestor import glossary, langid, memory
    from nestor.cascade import translate_text

    from .nestor_wiring import configure_nestor
    configure_nestor()

    if args.nestor_cmd == "seed":
        # The bilingual loader is wired globally by configure_nestor(); the
        # corpus data comes from that loader. --corpus stays an existence gate,
        # matching the original seed_from_corpus(corpus_path=...) behavior.
        import pathlib
        n = memory.seed_from_corpus() if pathlib.Path(args.corpus).exists() else 0
        print(f"Sealed {n} pairs from corpus into the memory.")
        s = memory.stats()
        print(f"Memory: {s['total']} pairs ({s['sealed']} sealed, {s['draft']} draft)")

    elif args.nestor_cmd == "say":
        import pathlib
        text = args.text
        if text == "-":
            text = sys.stdin.read()
        elif pathlib.Path(text).is_file():
            text = pathlib.Path(text).read_text(encoding="utf-8")
        src = args.source or langid.detect(text)
        try:
            doc, passages = translate_text(text, target_lang=args.to, source_lang=src,
                                           engine_name=args.engine)
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        tier_names = {1: "memory", 2: "draft", 0: "none"}
        for p in passages:
            print(f"[{p.mark}] ({tier_names[p.tier]}"
                  f"{' · ' + p.engine if p.tier == 2 else ''}"
                  f"{f' · {p.confidence:.2f}' if p.confidence else ''})")
            print(f"    {src}: {p.source}")
            print(f"    {args.to}: {p.target or '(no candidate — needs a human)'}")
        pending = sum(1 for p in passages if p.tier != 1)
        if pending:
            print(f"\n{pending} segment(s) queued for review (doc {doc['id'][:8]}).")
            print("Seal them:  semantic-translator review")
        else:
            print("\nAll segments served sealed from memory. In medio, fides.")

    elif args.nestor_cmd == "status":
        s = memory.stats()
        print(f"Memory: {s['total']} pairs · {s['sealed']} sealed · {s['draft']} draft")
        for src, tgt, n in s["lang_pairs"]:
            print(f"  {src} -> {tgt}: {n}")
        import pathlib
        ledger = pathlib.Path("data/ledger.jsonl")
        if ledger.exists():
            entries = sum(1 for _ in ledger.open())
            print(f"Ledger: {entries} entries ({ledger})")
        g = glossary.load()
        if g:
            print("Glossary locks:")
            for key, terms in sorted(g.items()):
                print(f"  {key}: {len(terms)} term(s)")

    elif args.nestor_cmd == "glossary":
        if "=" not in args.entry:
            print("Format: term=translation", file=sys.stderr)
            sys.exit(1)
        term, translation = args.entry.split("=", 1)
        glossary.add_term(term.strip(), translation.strip(), args.source or "en", args.to)
        print(f'Locked: "{term.strip()}" -> "{translation.strip()}" '
              f"({args.source or 'en'} -> {args.to})")


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="semantic-translator",
        description="Semantic translation memory for lesson curricula",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("scrape", help="Pull lessons from GitHub → corpus JSONL")
    p.add_argument("--output", default="data/corpus.jsonl", metavar="PATH")
    p.add_argument("--local", default="", metavar="DIR",
                   help="Read lessons from a local clone instead of GitHub")
    p.set_defaults(func=cmd_scrape)

    p = sub.add_parser("ingest", help="Ingest corpus segments into Jeles")
    p.add_argument("--corpus", default="data/corpus.jsonl", metavar="PATH")
    p.add_argument("--log", default="data/ingest_log.jsonl", metavar="PATH")
    p.add_argument("--delay", type=float, default=0.15, metavar="SECS")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("demo", help="Seed a built-in bilingual demo corpus (no network needed)")
    p.add_argument("--output", default="data/corpus.jsonl", metavar="PATH")
    p.add_argument("--force", action="store_true", help="Overwrite an existing corpus")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("play", help="¿Cómo se dice? — bilingual match quiz game")
    p.add_argument("--rounds", type=int, default=10, metavar="N")
    p.add_argument("--reverse", action="store_true", help="Quiz ES → EN instead of EN → ES")
    p.add_argument("--learner", default="", metavar="NAME",
                   help="Record answers to this learner's SRS deck")
    p.add_argument("--seed", type=int, default=None, help="RNG seed (reproducible game)")
    p.set_defaults(func=cmd_play)

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

    p = sub.add_parser("nestor", help="Nestor cascade — memory → draft → seal")
    nsub = p.add_subparsers(dest="nestor_cmd", required=True)
    np_ = nsub.add_parser("seed", help="Seal corpus bilingual pairs into the memory")
    np_.add_argument("--corpus", default="data/corpus.jsonl", metavar="PATH")
    np_ = nsub.add_parser("say", help="Translate text/file through the cascade")
    np_.add_argument("text", help="Text, a file path, or - for stdin")
    np_.add_argument("--to", default="es", metavar="LANG")
    np_.add_argument("--source", default="", metavar="LANG", help="Default: auto-detect")
    np_.add_argument("--engine", default="auto", choices=["auto", "claude", "offline"])
    np_ = nsub.add_parser("status", help="Memory, ledger, and glossary state")
    np_ = nsub.add_parser("glossary", help="Lock a term: 'term=translation'")
    np_.add_argument("entry")
    np_.add_argument("--to", default="es", metavar="LANG")
    np_.add_argument("--source", default="", metavar="LANG")
    p.set_defaults(func=cmd_nestor)

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
