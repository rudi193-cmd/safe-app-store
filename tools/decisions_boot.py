#!/usr/bin/env python3
"""decisions_boot.py — render and validate the fleet decision record.

The boot half of N9's third chokepoint: a cold agent runs this at session
start and begins with the institutional memory it otherwise cannot have —
the standing law with its reasons, and the rejections split into closed
doors (never) and conditions to re-check (not yet).

Validation is the same covenant the record's README states, enforced:

  * every decision has question, commitment, a non-empty reason, and a
    verifier that differs from its author;
  * every rejection has a non-empty reason (an unexplained no is the
    Aristarchus bug), a verifier, and a reopen_when KEY — present even when
    empty, because "never" must be a written act, not an omission.

Usage:
  tools/decisions_boot.py            # render the boot readout
  tools/decisions_boot.py --strict   # exit 1 on any covenant violation (CI)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RECORD = Path(__file__).resolve().parents[1] / "stores" / "decisions" / "fleet.json"


def load(path: Path = RECORD) -> dict:
    return json.loads(path.read_text())


def validate(record: dict) -> list[str]:
    problems: list[str] = []
    for i, d in enumerate(record.get("decisions", [])):
        where = f"decisions[{i}] ({d.get('question', '?')!r})"
        for key in ("question", "commitment", "reason", "author",
                    "verified_by"):
            if not d.get(key):
                problems.append(f"{where}: missing or empty {key!r}")
        if d.get("author") and d.get("author") == d.get("verified_by"):
            problems.append(f"{where}: verified_by equals author - proposing "
                            "and ratifying never rest in the same hand")
    for i, r in enumerate(record.get("rejections", [])):
        where = f"rejections[{i}] ({r.get('question', '?')!r})"
        for key in ("question", "option", "reason", "verified_by"):
            if not r.get(key):
                problems.append(f"{where}: missing or empty {key!r}")
        if "reopen_when" not in r:
            problems.append(f"{where}: no reopen_when key - 'never' must be "
                            "written, not omitted")
    return problems


def render(record: dict, out=sys.stdout) -> None:
    decisions = [d for d in record.get("decisions", [])
                 if not d.get("superseded_by")]
    nevers = [r for r in record.get("rejections", [])
              if not r.get("reopen_when")]
    reopeners = [r for r in record.get("rejections", [])
                 if r.get("reopen_when")]

    print("standing law:", file=out)
    for d in decisions:
        print(f"  {d['question']}", file=out)
        print(f"    -> {d['commitment']}  (sealed by {d['verified_by']}; "
              f"reason: {d['reason']})", file=out)
    if nevers:
        print("closed doors [never]:", file=out)
        for r in nevers:
            print(f"  {r['question']} != {r['option']} - {r['reason']}",
                  file=out)
    if reopeners:
        print("open conditions [not yet - re-check these]:", file=out)
        for r in reopeners:
            print(f"  {r['question']} != {r['option']}", file=out)
            print(f"    reopen when: {r['reopen_when']}", file=out)
    print(f"({len(decisions)} standing, {len(nevers)} never, "
          f"{len(reopeners)} not-yet)", file=out)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--strict", action="store_true",
                   help="exit 1 on covenant violations (CI gate)")
    p.add_argument("--record", default=str(RECORD),
                   help="path to fleet.json (default: the repo's)")
    args = p.parse_args(argv)

    record = load(Path(args.record))
    problems = validate(record)
    if problems:
        print("decision record violates its covenant:", file=sys.stderr)
        for pr in problems:
            print(f"  {pr}", file=sys.stderr)
        if args.strict:
            return 1
    render(record)
    return 0


if __name__ == "__main__":
    sys.exit(main())
