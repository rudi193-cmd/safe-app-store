"""aristarchus.cli — the N9 warn-mode gate: `aristarchus check`.

The bench ruling this implements (bench/results/n1.json, 2026-08-05): the
sentence encoder has a viable 0.90-0.95 band, wrong_key 0 throughout, so
`constraints_on()` is fit for ADVISORY use - surfacing constraints, warn-mode
CI - via Nestor's serve/queue split. It is NOT fit to fail a build
fail-closed: 0.90 cries wolf one question in five, 0.95 sleeps through half.

So this command's contract, in warn-mode (the default):

  * exit 0, always - it speaks, it does not block;
  * a question resolving at >= CONFIDENT (0.95) to a stored key reports its
    constraints as findings;
  * one resolving in the CHECK band [0.85, 0.95) reports them as
    "possible match - check";
  * a tampered row or broken ledger is ALWAYS a finding, loudly - integrity
    is not subject to the matcher's accuracy.

`--strict` exists for experimentation only: exit 2 when any confident-tier
finding (or any integrity finding) fires. The bench has NOT earned this mode
- the README says what it would take - and the flag says so when used.

Paths are arguments, never defaults (vault rule): the caller says where the
db and ledger live. ARISTARCHUS_SEAL_KEY must be set for reads to verify -
without it nothing serves as sealed, which is the fail-closed direction.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Optional

from .memory import Constraints, DecisionMemory, StringMatcher
from .store import DecisionStore

CONFIDENT = 0.95
CHECK_FLOOR = 0.85


def _build_matcher(prefer_semantic: bool = True):
    """The bench falsified the string matchers, so advisory quality needs
    the sentence encoder. Fall back loudly, never silently."""
    if prefer_semantic:
        try:
            from fastembed import TextEmbedding

            class SemanticMatcher(StringMatcher):
                def __init__(self) -> None:
                    self.model = TextEmbedding()
                    self._cache: dict[str, Any] = {}

                def _embed(self, text: str):
                    key = self.normalize(text)
                    if key not in self._cache:
                        self._cache[key] = next(iter(self.model.embed([key])))
                    return self._cache[key]

                def score(self, a: str, b: str) -> float:
                    va, vb = self._embed(a), self._embed(b)
                    cos = float(va @ vb / ((va @ va) ** 0.5
                                           * (vb @ vb) ** 0.5))
                    return (cos + 1.0) / 2.0

            return SemanticMatcher(), "fastembed"
        except Exception as exc:
            print(f"warning: sentence encoder unavailable ({exc}); falling "
                  "back to StringMatcher - the bench FALSIFIED string "
                  "matching for rewording, so only exact/near-exact "
                  "questions will resolve", file=sys.stderr)
    return StringMatcher(), "string-fallback"


def check_question(mem: DecisionMemory, question: str) -> dict[str, Any]:
    """One question -> one report dict. Pure; the printing happens above."""
    c: Constraints = mem.constraints_on(question)
    if c.tampered:
        tier = "integrity"
    elif c.unconstrained:
        tier = "clear"
    elif c.match_score >= CONFIDENT:
        tier = "confident"
    else:
        tier = "check"
    return {"question": question, "tier": tier,
            "matched": c.matched_norm if tier not in ("clear",) else "",
            "score": round(c.match_score, 3), "constraints": c}


def _speak(report: dict[str, Any], out) -> None:
    q, tier, c = report["question"], report["tier"], report["constraints"]
    if tier == "clear":
        print(f"  clear     {q!r} - no standing law touches this", file=out)
        return
    label = {"confident": "constrained", "check": "check?    ",
             "integrity": "TAMPERED "}[tier]
    hdr = f"  {label} {q!r}"
    if tier == "check":
        hdr += (f" ~ {report['matched']!r} (score {report['score']}; "
                "possible match - check before proceeding)")
    print(hdr, file=out)
    if tier == "integrity":
        for t in c.tampered:
            print("      ! row claims sealed but the seal does not verify "
                  f"(id={t.get('id', '?')}) - surfaced, never served",
                  file=out)
        return
    if c.live is not None:
        print(f"      law: {c.live['commitment']!r} "
              f"(sealed by {c.live['verifier']}"
              + (f"; reason: {c.live['reason']}" if c.live['reason'] else "")
              + ")", file=out)
    for r in c.lineage:
        print(f"      was: {r['commitment']!r} - replaced because: "
              f"{r['reason'] or 'no reason recorded'}", file=out)
    for r in c.rejections:
        print(f"      rejected: {r['option']!r} - {r['reason']} [never]",
              file=out)
    for r in c.reopeners:
        print(f"      rejected: {r['option']!r} - {r['reason']} "
              f"[not yet - reopen when: {r['reopen_when']}]", file=out)


def run_check(mem: DecisionMemory, questions: list[str], strict: bool = False,
              json_out: bool = False, out=None) -> int:
    """The gate. Returns the exit code; warn-mode always returns 0 unless
    the ledger itself is broken (integrity outranks advisory)."""
    out = out or sys.stdout
    ledger_ok = mem.store.ledger_verify()
    reports = [check_question(mem, q) for q in questions]
    findings = [r for r in reports if r["tier"] in ("confident", "integrity")]
    checks = [r for r in reports if r["tier"] == "check"]

    if json_out:
        payload = {"ledger_ok": ledger_ok,
                   "results": [{k: v for k, v in r.items()
                                if k != "constraints"} for r in reports]}
        print(json.dumps(payload, indent=2), file=out)
    else:
        if not ledger_ok:
            print("  BROKEN ledger: hash chain does not verify - every "
                  "answer below is suspect", file=out)
        for r in reports:
            _speak(r, out)
        n = len(reports)
        print(f"\n  {n} question(s): {len(findings)} constrained, "
              f"{len(checks)} to check, "
              f"{n - len(findings) - len(checks)} clear", file=out)

    if not ledger_ok:
        return 2                      # integrity is never advisory
    if strict and findings:
        print("\n  strict mode: exiting 2 on constrained findings. NOTE: "
              "the N1 bench has not earned fail-closed enforcement "
              "(README: 0.90 cries wolf 1-in-5, 0.95 sleeps through half) "
              "- use knowingly.", file=out)
        return 2
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="aristarchus",
        description="decision memory - lineage and rejections both")
    sub = p.add_subparsers(dest="cmd", required=True)

    chk = sub.add_parser("check", help="warn-mode gate: do these questions "
                                       "brush standing law?")
    chk.add_argument("--db", required=True, help="decision store db path")
    chk.add_argument("--ledger", required=True, help="ledger jsonl path")
    chk.add_argument("--domain", default="decision")
    chk.add_argument("--strict", action="store_true",
                     help="exit 2 on constrained findings (EXPERIMENTAL - "
                          "the bench has not earned fail-closed)")
    chk.add_argument("--json", action="store_true", dest="json_out")
    chk.add_argument("--no-semantic", action="store_true",
                     help="skip the sentence encoder (testing only)")
    chk.add_argument("questions", nargs="*",
                     help="questions to check; reads stdin lines if empty")

    args = p.parse_args(argv)
    questions = args.questions or [ln.strip() for ln in sys.stdin
                                   if ln.strip()]
    if not questions:
        print("nothing to check", file=sys.stderr)
        return 0
    if not os.environ.get("ARISTARCHUS_SEAL_KEY"):
        print("warning: ARISTARCHUS_SEAL_KEY not set - nothing can verify, "
              "so nothing will serve as sealed (rows surface as tampered)",
              file=sys.stderr)

    matcher, kind = _build_matcher(prefer_semantic=not args.no_semantic)
    store = DecisionStore(args.db, args.ledger)
    try:
        mem = DecisionMemory(store, domain=args.domain, matcher=matcher,
                             threshold=CHECK_FLOOR)
        print(f"aristarchus check ({kind} matcher, confident>={CONFIDENT}, "
              f"check>={CHECK_FLOOR})")
        return run_check(mem, questions, strict=args.strict,
                         json_out=args.json_out)
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
