#!/usr/bin/env python3
"""Probe the fleet decision record through real Nestor.

The experiment of 2026-08-05, kept runnable: seed a SCRATCH Nestor store with
``stores/decisions/fleet.json`` — decisions sealed with their reasons (N4),
rejections recorded with their reopen conditions (N5) — then ask it questions
and report what it SERVES (matched standing law, with the reason), what it
QUEUES (no law within reach: a proposal for the operator), and which
rejections a question brushes, split never / not-yet.

The first run of this probe is on the record at safe-app-store PR #168: it
found that the fleet's most load-bearing principle ("a model may propose;
only a person may verify") existed everywhere as prose and nowhere as sealed
law, and its six-question queue became five sealed decisions the same night.
The default PIECES below are that run's probes, kept as the experiment's
provenance; pass your own questions as arguments to probe anything else.

Requirements: Nestor (not on PyPI - a sibling repo). Either `pip install -e`
it, or set NESTOR_PATH to a checkout. Everything this writes is scratch:
in-memory store, ledger in a temp dir (or --ledger). The seal key defaults
to a throwaway because nothing sealed here outlives the run - the REAL
record's witness is git, and its gate is tools/decisions_boot.py.

Usage:
  python scripts/nestor_decisions_probe.py                 # the 2026-08-05 set
  python scripts/nestor_decisions_probe.py "May a build widen its own reach?"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RECORD = REPO / "stores" / "decisions" / "fleet.json"

#: The probes of the first run (2026-08-05) - the other sessions' new pieces,
#: asked against standing law. Kept verbatim as provenance; see PR #168.
PIECES = [
    ("intake-desk spec 4.1",
     "May a model verify, rule, seal, or publish?"),
    ("intake-desk spec 4.1 (the failure it names)",
     "May a model state that corroboration occurred?"),
    ("homestead I-13",
     "Must a declared purpose be checkable rather than a label?"),
    ("homestead R-7 / nestor#32 / willow#280",
     "May the field recording why a boundary was crossed be free text?"),
    ("subject-consent testimony_publication",
     "May a subject's testimony be published attributed under their name?"),
    ("willow#280",
     "Must the governance chain head be anchored outside the database?"),
    ("standing law, verbatim",
     "Which store should hold the fleet's decision graph?"),
    ("standing law, reworded (the N1 blindness check)",
     "Where does the fleet keep its graph of decisions?"),
]


def _import_nestor():
    try:
        import nestor  # noqa: F401
    except ImportError:
        extra = os.environ.get("NESTOR_PATH", "")
        if extra:
            sys.path.insert(0, extra)
        try:
            import nestor  # noqa: F401
        except ImportError:
            print("Nestor is not importable. It is not on PyPI - "
                  "`pip install -e` a checkout of rudi193-cmd/nestor, or "
                  "set NESTOR_PATH to one.", file=sys.stderr)
            raise SystemExit(2)
    from nestor import cascade, ledger, memory, storage
    from nestor.sqlite_store import SqliteStore
    return cascade, ledger, memory, storage, SqliteStore


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("questions", nargs="*",
                   help="probe questions; default is the 2026-08-05 set")
    p.add_argument("--record", default=str(RECORD),
                   help="decision record to seed (default: the repo's)")
    p.add_argument("--ledger", default="",
                   help="ledger path (default: a temp dir - scratch)")
    args = p.parse_args(argv)

    cascade, ledger, memory, storage, SqliteStore = _import_nestor()
    os.environ.setdefault("NESTOR_SEAL_KEY", "probe-scratch")
    ledger_path = args.ledger or str(
        Path(tempfile.mkdtemp(prefix="decisions-probe-")) / "ledger.jsonl")
    cascade.set_ledger_path(ledger_path)
    store = SqliteStore(":memory:")
    store.init_db()
    store.memory_init()
    storage.set_store(store)

    fleet = json.loads(Path(args.record).read_text())
    print(f"seeding {len(fleet['decisions'])} decisions, "
          f"{len(fleet['rejections'])} rejections from {args.record}")
    for d in fleet["decisions"]:
        if d.get("superseded_by"):
            continue                      # history seeds nothing; law does
        memory.add_pair(d["question"], d["commitment"], "decision", "law",
                        status="sealed", verifier=d["verified_by"],
                        reason=d["reason"], store=store)
    for r in fleet["rejections"]:
        # pair_id deliberately EMPTY: reject_match(pair_id=X) means "pair X
        # is the wrong answer for this query", and the sealed decision is
        # not the wrong answer - the rejected OPTION is. Passing the sealed
        # pair's id here suppresses the law for its own question (the first
        # run's shim had exactly that bug; it surfaced the moment a probed
        # question became sealed law with a riding rejection).
        memory.reject_match(r["question"], "decision", "law",
                            pair_id="", target_text=r["option"],
                            verifier=r["verified_by"], reason=r["reason"],
                            reopen_when=r.get("reopen_when", ""), store=store)

    probes = ([("cli", q) for q in args.questions] if args.questions
              else PIECES)
    queued = []
    for src, q in probes:
        hits = memory.lookup(q, "decision", "law", store=store,
                             context_threshold=0.4)
        best = hits[0] if hits else None
        print(f"\n[{src}]\nQ: {q}")
        if best and best["similarity"] >= memory.SEAL_THRESHOLD:
            pr = best["pair"]
            print(f"SERVED  ({best['similarity']:.2f}): {pr['target_text']!r}")
            print(f"        reason: {pr.get('reason', '')}")
        elif best:
            pr = best["pair"]
            print(f"context ({best['similarity']:.2f}): nearest law is "
                  f"{pr['source_text'][:48]!r} -> {pr['target_text'][:40]!r}")
            queued.append((src, q))
        else:
            print("QUEUED  - no standing law within reach; this is a "
                  "proposal for the operator")
            queued.append((src, q))
        for r in store.memory_rejections(memory._norm(q), "decision", "law"):
            tag = (f"not yet - reopen when: {r['reopen_when']}"
                   if r.get("reopen_when") else "never")
            print(f"brushes rejection: {r['target_text']!r} [{tag}]")

    ok, detail = ledger.verify()
    print(f"\nledger: {'intact' if ok else detail} at {ledger_path}")
    print(f"queue for the operator ({len(queued)}):")
    for src, q in queued:
        print(f"  - [{src}] {q}")
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
