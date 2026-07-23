#!/usr/bin/env python3
"""
stupid_tests.py — the stupid-test harness. b17: OAKOF

Not the unit suite (that's tests/, run with pytest and CI-serious). This is
the playground: end-to-end "does the whole silly thing actually work" checks
that run against the disposable sandbox and tell a story out loud. Add more
by appending an @stupid function — each returns (ok, one_line_story).

    ./sandbox.sh --seed-only      # plant the sandbox first
    OAKENSCROLL_DB=./.sandbox/office.db \
    ALMANAC_DATA_ROOT=./.sandbox/almanac-data \
    python3 stupid_tests.py

The first stupid test is the one the sandbox seed itself predicted at 50%:
"the sandbox survives the stupid test." We grade it by whether this run does.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

_TESTS = []


def stupid(story_if_pass):
    """Register a stupid test. The wrapped fn returns True/False (or raises =
    fail). `story_if_pass` is what we print when it holds."""
    def wrap(fn):
        _TESTS.append((fn.__name__, story_if_pass, fn))
        return fn
    return wrap


# --- imports deferred until env (OAKENSCROLL_DB) is set by the caller ---
import office_db as db          # noqa: E402
import calibration             # noqa: E402
import almanac_seam            # noqa: E402
import web                     # noqa: E402
from app import OfficeApp      # noqa: E402


@stupid("the sandbox survives the stupid test — app boots, seed loads, scorecard renders")
def sandbox_survives():
    async def drive():
        app = OfficeApp()
        async with app.run_test(size=(110, 32)) as pilot:
            await pilot.pause()
            assert app.active_due() is not None, "no dew surfaced"
            await pilot.press("tab"); await pilot.press("tab"); await pilot.pause()
            assert "Graded:" in app.scorecard_text()
        return True
    return asyncio.run(drive())


@stupid("Oakenscroll has notes — the seeded record is provably overconfident")
def overconfident_on_purpose():
    s = calibration.summary(db.resolved_pairs())
    assert s["n"] >= 10, f"only {s['n']} graded"
    assert s["overconfidence"] > 0.15, f"overconfidence only {s['overconfidence']:.2f}"
    return True


@stupid("the receipts survive — a graded claim still names the almanac commit that vouched")
def citation_persists():
    cited = [r for r in db.ledger("resolved") if r["evidence"]]
    assert len(cited) == 1, f"{len(cited)} cited grades, expected 1"
    ev = cited[0]["evidence"]
    assert ev["vertical"] == "climate-almanac" and ev["catalog_commit"]
    return True


@stupid("the mirror doesn't flatter you — the web scorecard says 'overconfident' out loud")
def mirror_is_honest():
    page = web.handle("GET", "/")[2]
    assert "overconfident" in page and "<svg" in page
    ledger = json.loads(web.handle("GET", "/ledger.json")[2])
    assert any(r["evidence"] for r in ledger)
    return True


def main() -> int:
    if not os.environ.get("OAKENSCROLL_DB"):
        print("refusing to run outside a sandbox — set OAKENSCROLL_DB (use ./sandbox.sh)")
        return 2
    print("═══ stupid tests ═══  (sandbox: %s)\n" % os.environ["OAKENSCROLL_DB"])
    passed = 0
    for i, (name, story, fn) in enumerate(_TESTS):
        try:
            ok = fn()
        except Exception as err:  # a raise is a fail, loudly
            ok, story = False, f"{type(err).__name__}: {err}"
        mark = "✓" if ok else "✗"
        print(f"  {mark} [{i}] {name}")
        print(f"      {story}\n")
        passed += bool(ok)
    n = len(_TESTS)
    print(f"═══ {passed}/{n} stupid tests survived ═══")

    # close the loop: grade the sandbox's self-referential seed by this run
    for r in db.ledger("open"):
        if "survives the stupid test" in r["claim"]:
            db.resolve(r["id"], passed == n, note=f"stupid_tests.py: {passed}/{n}")
            verdict = "TRUE" if passed == n else "FALSE"
            print(f"    → graded the seed's own prediction {verdict} "
                  f"(it said {r['confidence']:.0%})")
            break
    return 0 if passed == n else 1


if __name__ == "__main__":
    sys.exit(main())
