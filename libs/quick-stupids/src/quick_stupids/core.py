"""The pattern behind ``qstupid``, factored out for a second subject app.

A subject app is: a fixed set of ``{question: answer}`` principles from a
named source, filed as jeles nuggets under a per-app id prefix and tag, with
three subcommands — ``seed`` (upsert), ``list`` (show what's on file), and
``check <claim>`` (search the app's own nuggets for ones that bear on a
claim). Deterministic sha1 ids over the question mean ``seed`` upserts; the
id prefix keeps every app's nuggets separable from every other's inside the
shared jeles corpus.

A caller builds the ``principles`` dict however it likes — parsed out of a
doc, hardcoded, generated — and passes it in with the app's identity.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from typing import Mapping

import jeles.corpus as corpus


def _principle_key(answer: str) -> str:
    """The natural key of a principle: its leading sentence."""
    head, _, _ = answer.partition(".")
    return (head + ".").strip()


def _nugget_id(id_prefix: str, answer: str) -> str:
    digest = hashlib.sha1(_principle_key(answer).encode("utf-8")).hexdigest()[:12]
    return f"{id_prefix}{digest}"


def subject_app(
    *,
    prog: str,
    id_prefix: str,
    tags: list[str],
    source: str,
    verified_by: str,
    written_by: str,
    principles: Mapping[str, str],
    description: str = "",
    no_hits_message: str = "Nothing in the corpus bears on that.",
    hits_header: str = "That would be filed under:",
    hits_footer: str = "",
    argv: list[str] | None = None,
) -> int:
    """Run a subject app's CLI. Returns an exit code.

    ``principles`` maps question → answer. The question is the primary key
    within this app; two apps may share a question because ``id_prefix``
    keeps them apart.
    """
    parser = argparse.ArgumentParser(prog=prog, description=description or None)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed", help="upsert this app's principles into jeles")
    sub.add_parser("list", help="show what's filed for this app")
    check = sub.add_parser("check", help="search this app's principles for a claim")
    check.add_argument("claim", nargs=argparse.REMAINDER)
    check.add_argument("--limit", type=int, default=8)

    args = parser.parse_args(argv)

    if args.cmd == "seed":
        return _seed(id_prefix, tags, source, verified_by, written_by, principles)
    if args.cmd == "list":
        return _list(id_prefix)
    if args.cmd == "check":
        return _check(
            id_prefix,
            claim=" ".join(args.claim).strip(),
            limit=args.limit,
            no_hits_message=no_hits_message,
            hits_header=hits_header,
            hits_footer=hits_footer,
        )
    return 2


def _seed(
    id_prefix: str,
    tags: list[str],
    source: str,
    verified_by: str,
    written_by: str,
    principles: Mapping[str, str],
) -> int:
    if not principles:
        print("no principles supplied — nothing to seed", file=sys.stderr)
        return 1
    for question, answer in principles.items():
        result = corpus.put_nugget(
            question=question,
            answer=answer,
            sources=[source],
            verified_by=verified_by,
            tags=list(tags),
            nugget_id=_nugget_id(id_prefix, answer),
            written_by=written_by,
        )
        action = result.get("action", "?")
        head = answer.split(".", 1)[0] + "."
        print(f"[{action:8}] {head}")
    print(f"\n{len(principles)} principles filed under tags={list(tags)}")
    return 0


def _list(id_prefix: str) -> int:
    nuggets = corpus.list_nuggets(limit=500)
    ours = [n for n in nuggets if n.get("_id", "").startswith(id_prefix)]
    if not ours:
        print(f"nothing filed under {id_prefix!r} yet — run: seed")
        return 0
    for n in ours:
        answer = n["answer"]
        print(f"- {n['_id']}")
        print(f"    Q: {n['question']}")
        print(f"    A: {answer[:120]}{'…' if len(answer) > 120 else ''}")
    print(f"\n{len(ours)} nuggets on file.")
    return 0


def _check(
    id_prefix: str,
    *,
    claim: str,
    limit: int,
    no_hits_message: str,
    hits_header: str,
    hits_footer: str,
) -> int:
    if not claim:
        print("usage: <app> check <claim>", file=sys.stderr)
        return 2
    hits = corpus.search_nuggets(claim, limit=limit)
    hits = [h for h in hits if h.get("_id", "").startswith(id_prefix)]
    if not hits:
        print(no_hits_message)
        return 0
    print(f'Claim: "{claim}"\n')
    print(hits_header + "\n")
    for hit in hits:
        head = hit.get("answer", "").split(".", 1)[0] + "."
        print(f"  - {head}")
        print(f"    ({hit.get('_id', '?')})")
    if hits_footer:
        print(f"\n{hits_footer}")
    return 0
