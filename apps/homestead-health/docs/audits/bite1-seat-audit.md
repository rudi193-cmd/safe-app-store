# Bite 1 audit — the seat, attacked and remediated

**Audited 2026-08-11**, same day the bite landed (PR #173), by an independent
adversarial pass that did not write the implementation (`verified_by ≠
author`). The audit ran the suite both ways on the exact CI sequence, planted
violations in scratch copies to prove every scan fires, planted bypasses to
find the ones that don't, and exercised the xfail-strict machinery with three
synthetic `roster.py` variants. The report arrived after the merge; this
document and the remediation commit it describes are the follow-up.

**Verdict as delivered: would not merge as-is — one fix required.** The fix
is made; findings and dispositions below.

## Findings

### 1 · CONFIRMED, the blocker — the path scan was a weakened copy that missed the Desktop leak — **fixed**

`test_invariants_seat.py` advertised *"the engine's own scans … the same
checks"* and shipped a call-name subset instead. The engine's
`tests/test_invariants_paths.py` was itself rewritten after its Phase 0 audit
because a call-name scan let `Path(os.environ["HOME"]) / "Desktop" / "Nest"`
— F-1, the Desktop leak, in idiomatic pathlib — pass the whole suite:
`os.environ[...]` is a Subscript, not a call, and `/ "Desktop"` contains no
slash. The copy reintroduced exactly that defect. The audit planted the
engine's own regression payload in a scratch copy of this package: **this
suite stayed green (9 passed / 6 xfailed); the engine's caught it twice.**
Same result for `os.getenv("HOME")` and for a bare `/ "Desktop"` literal.

**Remediation:** the engine's mechanism scan ported whole — home-reaching
calls, `environ[...]` subscripts against `HOME`/`USERPROFILE`/`HOMEPATH`/
`HOMEDRIVE`, and user-directory literals in path context (segment-wise, with
the docstring exclusion) — plus the engine's `test_i19_regression_desktop_leak`
kept verbatim, so the scans are held to the payload by their own suite. One
deliberate difference, now stated instead of implied: the engine exempts its
resolver file; this package has no resolver file to exempt, so *nothing* here
may reach home — the resolver is `homestead.keep.paths`, one dependency over
(`paths.home(...)` calls stay legal).

### 2 · CONFIRMED — H-1's pending assertion accepted a reversible id — **fixed**

`assert "Synthetic" not in str(ref)` passes for
`subj-01-<base64("Synthetic Child")>`: no fragment survives, the whole name
does. Not silent drift — the strict-xfail machinery still forces a human to
look when the module lands — but the test as worded would not have held H-1
if promoted verbatim. **Remediation:** the test now also asserts the id is
independent of the name (two fresh rosters, same position, different names,
same id), which kills any deterministic derivation from the datum. An
implementation wanting non-deterministic ids must come back to the test with
a mechanism argument — the conversation H-1 exists to force.

### 3 · CONFIRMED, low — the store never cross-checks `version` — recorded, not fixed here

`catalog_lint`'s generated-fields gate compares `tier`/`majors`/`status`
against the keeping record; `version` (catalog entry, manifest, pyproject)
is compared to nothing. The three agree today by hand. A store-wide gap, not
this app's to patch from inside; recorded for the store's own ledger.

### 4 · Shared limitation, inherited knowingly — recorded

Dynamic imports (`importlib.import_module("urllib.request")`,
`__import__("socket")`), function-body imports, and aliased calls
(`from os.path import expanduser as e`) evade this package's scans **and the
engine's own, identically** — verified by planting each in scratch copies of
both. An inherited property of the top-level-AST approach, copied rather
than introduced. The honest bound on what a green scan means.

### 5 · Minor, pre-existing — CI cache key omits the shared libs

The `app-tests` cache key is the app's `requirements.txt`, but the job also
installs three `libs/` editables that don't participate in the key. Every
matrix leg shares this; not introduced here.

### 6 · Deviation examined and accepted

The plan says *"H-1 through H-5 land as xfail(strict=True)"*; the shipped
`UNBUILT` carries six entries — the five invariants plus bite 5's export
claim, the same discipline extended, documented in the file.

## What was attacked and held

Suite green on the exact CI sequence (Python 3.12, libs installed, app
uninstalled, `conftest.py` path insertion doing the work) and installed
editable — 9 passed / 6 xfailed both ways. All eight planted violations flip
their specific test red (network import ×2, `expanduser`, `Path.home()`,
`listen()`, undeclared-but-installed import ×2, shadowed basename).
`Path("~").expanduser()` split across lines is caught. The promotion
machinery is honest: a correct `roster.py` fails the suite twice (liveness by
name, H-1 by strict XPASS); a violating one still fails liveness; a
`packs/__init__.py`-only tree leaves baseline unchanged — the
`find_spec`-raises adaptation works as documented. Store wiring: catalog
lint 0/0, vault lint PASS, the six catalog suites 49 passed, `pip check`
clean. Not run: a real GitHub Actions execution (reproduced locally instead).

## Remediation verification

The regression payload that beat the first version — planted again in a
scratch copy after the fix — now fails the suite three ways
(`test_i19_i20_nothing_here_reaches_home`, `test_i19_no_user_directory_literals`
on the planted file, and the in-suite regression test guards the scans
themselves). The full suite on the remediated tree: 12 passed / 6 xfailed.
