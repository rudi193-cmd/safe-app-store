#!/usr/bin/env python3
"""
tools/readiness_drift.py — the upstream-drift guard for the Forge's readiness
seam (`stores/readiness_corpus.py`)

`BEARINGS` and `GATE_BEARINGS` are a small, hand-authored set of claims —
"this instrument's finding bears on control PRC-07-015" — pinned to specific
IDs in an EXTERNAL corpus that re-syncs upstream (`stores/readiness_corpus.py`
D-R1/D-R2). If upstream renumbers or retires a control, a bearing silently
points at nothing: `assess()` skips it, coverage shrinks rather than lying,
and `bearings --corpus` exits non-zero the next time someone happens to run
it by hand. Nothing PROACTIVELY says so. That gap is named in
`docs/design/the-forge-readiness.md`'s Open/next: *"Upstream drift is
undetected … nothing runs that on a schedule."* This tool is the thing that
runs.

It does one job: read every `control_id` referenced across `BEARINGS` AND
`GATE_BEARINGS`, and check each one still resolves in the injected corpus via
`ReadinessCorpus.get()`. It answers nothing else — not whether a bearing's
`why`/`limit` still reads true, not whether the corpus's TEXT for a control
changed shape, only whether the ID is still there to point at.

Exit contract — fail-closed and honest, same as the seam it guards:

  0  every referenced control ID resolves in the corpus.
  1  at least one referenced ID is missing — drift. Each drifted ID is
     printed with every table/key that references it, so the fix (repoint
     the bearing, or accept the coverage loss) is obvious without re-deriving
     which bearing broke.
  2  the corpus could not be opened (`CorpusUnavailable`) — not injected,
     wrong shape, empty, self-contradicting. A guard that cannot reach its
     corpus must not report a false all-clear: that is the module's own
     fail-closed philosophy (`readiness_corpus.CorpusUnavailable`'s docstring,
     word for word), and this guard inherits it rather than papering over a
     missing corpus with exit 0.

`--strict` is accepted for consistency with this repo's other `tools/`
gates (`catalog_lint.py`, `vault_leak_lint.py`) — CI documentation reaching
for the house convention should not error on it. It does not change
behavior: unlike those two, which default to report-only and need
`--strict` to turn a finding into a failing exit code, this guard is
fail-closed by construction (bullet list above) and stays that way with or
without the flag.

Stdlib only, same discipline as `readiness_corpus.py` itself: its top-level
imports are stdlib-only (measure_panel is imported lazily, only inside its
own CLI) specifically so a tool can spec-load it with plain `python3` — no
venv, no fleet deps. This tool preserves that: it spec-loads
`stores/readiness_corpus.py` the same `_REPO`-relative way
`readiness_corpus.py`'s own `_cmd_assess` and `tests/test_readiness_corpus.py`
do, and touches nothing else in the corpus or the panel.

Usage:
    tools/readiness_drift.py [--corpus PATH] [--json] [--strict]

Corpus resolution matches `ReadinessCorpus.open()`: `--corpus PATH`, else
`$FORGE_READINESS_CORPUS`, else `CorpusUnavailable` (exit 2).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent


def _load_readiness_corpus():
    """Spec-load `stores/readiness_corpus.py`, the `_REPO`-relative pattern
    that module's own CLI (`_cmd_assess`) and `tests/test_readiness_corpus.py`
    both use. Never a plain `import` — this tool lives in `tools/`, and the
    module it needs lives in `stores/`, which is not on `sys.path` by
    default. Checked against `sys.modules` first so a second call in the same
    process (tests spec-loading both this tool and the corpus module) does
    not re-exec it."""
    name = "readiness_corpus"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _REPO / "stores" / "readiness_corpus.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _collect_sites(rc) -> dict[str, set[tuple[str, str]]]:
    """Every control ID referenced anywhere in `BEARINGS` or `GATE_BEARINGS`,
    mapped to the (table, key) sites that reference it — `key` is the
    instrument name for `BEARINGS`, the gate's base name for `GATE_BEARINGS`.

    A `set` per ID, not a list: two bearings under the same key naming the
    same control (not that either table does this today) would otherwise
    duplicate the same site in a drift report, which is noise, not a second
    fact. IDs referenced by more than one bearing collapse to one entry here
    — deduplicated, per the exit contract — while every distinct site that
    named it is still kept, so the drift report loses no referencing key."""
    sites: dict[str, set[tuple[str, str]]] = {}
    for table_name, table in (("BEARINGS", rc.BEARINGS), ("GATE_BEARINGS", rc.GATE_BEARINGS)):
        for key, bearings in table.items():
            for b in bearings:
                sites.setdefault(b.control_id, set()).add((table_name, key))
    return sites


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="readiness_drift.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--corpus", default=None,
                    help="corpus root (default: $FORGE_READINESS_CORPUS)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--strict", action="store_true",
                    help="accepted for consistency with other tools/ gates; this guard "
                         "is fail-closed by default (see module docstring), so this flag "
                         "does not change behavior")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rc = _load_readiness_corpus()

    try:
        corpus = rc.ReadinessCorpus.open(args.corpus)
    except rc.CorpusUnavailable as e:
        reason = str(e)
        if args.json:
            print(json.dumps({"status": "unavailable", "reason": reason}, indent=2))
        else:
            print(f"readiness drift guard: corpus unavailable (fail-closed): {reason}",
                  file=sys.stderr)
        return 2

    sites = _collect_sites(rc)
    missing = sorted(cid for cid in sites if corpus.get(cid) is None)

    if not missing:
        if args.json:
            print(json.dumps({
                "status": "clean",
                "corpus": corpus.cite(),
                "verified": len(sites),
            }, indent=2))
        else:
            print(f"readiness drift guard: clean — {corpus.cite()} — "
                  f"{len(sites)} referenced control ID(s) verified present")
        return 0

    if args.json:
        print(json.dumps({
            "status": "drift",
            "corpus": corpus.cite(),
            "verified": len(sites) - len(missing),
            "missing": [
                {
                    "control_id": cid,
                    "referenced_by": sorted(f"{t}[{k}]" for t, k in sites[cid]),
                }
                for cid in missing
            ],
        }, indent=2))
    else:
        print(f"readiness drift guard: DRIFT against {corpus.cite()}")
        for cid in missing:
            refs = ", ".join(sorted(f"{t}[{k}]" for t, k in sites[cid]))
            print(f"  DRIFT {cid} — missing from corpus, referenced by {refs}")
        print(f"\n{len(missing)} of {len(sites)} referenced control ID(s) drifted")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
