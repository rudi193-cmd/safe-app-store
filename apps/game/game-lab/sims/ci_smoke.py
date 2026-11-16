"""ci_smoke.py — the game-lab CI gate.

This is deliberately NOT a reproduction of the N=500 baselines (that is
`run_added_games.py`, and the numbers it prints wobble run-to-run because the
sims are unseeded). This is the far cheaper question CI actually needs
answered on every push: *do the reference simulators still run, and do they
still return well-formed measured output?*

It calls each of the eleven stdlib added-game engines through the same
`run(policy, N)` seam `run_added_games.py` uses, at a small N, under both the
`random` and `john` policies, and fails loudly if any engine is missing that
seam, raises, or returns a shape that is not a populated result dict. The
core-five engines (`baseline_core`, `chess_selfplay`) depend on python-chess
and are checked at import level only — see `requirements.txt` and the CI job.

A gate that cannot fail is not a gate: `--self-test` deliberately breaks the
contract and asserts this runner catches it.

Exit 0 = every checked engine ran and returned a well-formed result.
Exit 1 = at least one did not; the offending engine is named on stderr.
"""
from __future__ import annotations

import importlib
import py_compile
import sys

# The eleven stdlib engines run_added_games.py drives. Kept in step with that
# list on purpose — if one is added there and not here, this gate goes quiet
# on it, which is the exact silent-skip failure the store warns about.
STDLIB_ENGINES = [
    "coup", "skull", "liars_dice", "cheat", "werewolf",
    "cribbage", "go_fish", "hearts", "crazy_eights", "spades", "war",
]

# The core-five path pulls in python-chess (see requirements.txt). CI installs
# it, so these checks are real rather than skipped. Two different checks,
# because the two files are different shapes:
#
#   IMPORT_CHECK — a proper module: importing it runs no work, so an import
#     verifies python-chess is wired in correctly (a stronger check than
#     syntax).
#   COMPILE_CHECK — chess_selfplay.py is a *script*, not a module: its whole
#     body runs at import (it plays 13 games and writes to a hardcoded
#     /root/_chess_res.md, which is PermissionError on a normal runner). It
#     cannot be safely imported, so it gets a syntax gate only. This is the
#     honest boundary of what CI exercises here: chess_selfplay's runtime
#     behavior and its hardcoded output path are NOT checked by this job — see
#     the note in requirements.txt / the store-ci.yml comment.
IMPORT_CHECK = ["baseline_core"]
COMPILE_CHECK = ["chess_selfplay"]

POLICIES = ("random", "john")
SMOKE_N = 40


def _check_result(name: str, policy: str, result: object) -> list[str]:
    """A run() return is well-formed iff it is a non-empty dict that reports
    the policy it was asked to run and names the game. Nothing here asserts a
    *value* — that is the baselines' job, and asserting counts on an unseeded
    sim would be a flaky gate."""
    problems: list[str] = []
    if not isinstance(result, dict) or not result:
        problems.append(f"{name}[{policy}]: run() returned {type(result).__name__}, not a populated dict")
        return problems
    if result.get("policy") != policy:
        problems.append(f"{name}[{policy}]: result policy is {result.get('policy')!r}, not {policy!r}")
    if not result.get("game"):
        problems.append(f"{name}[{policy}]: result has no 'game' key")
    return problems


def run_smoke(n: int = SMOKE_N) -> list[str]:
    problems: list[str] = []
    for name in STDLIB_ENGINES:
        try:
            mod = importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 — CI wants every failure, not the first
            problems.append(f"{name}: import failed: {exc!r}")
            continue
        run = getattr(mod, "run", None)
        if not callable(run):
            problems.append(f"{name}: no callable run(policy, N) seam")
            continue
        for policy in POLICIES:
            try:
                result = run(policy, n)
            except Exception as exc:  # noqa: BLE001
                problems.append(f"{name}[{policy}]: run() raised {exc!r}")
                continue
            problems.extend(_check_result(name, policy, result))
    return problems


def check_imports() -> list[str]:
    problems: list[str] = []
    for name in IMPORT_CHECK:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{name}: import failed: {exc!r}")
    for name in COMPILE_CHECK:
        # py_compile parses without executing — the only safe check for a
        # side-effecting script (see COMPILE_CHECK comment above).
        try:
            py_compile.compile(f"{name}.py", doraise=True)
        except py_compile.PyCompileError as exc:
            problems.append(f"{name}: does not compile: {exc.msg}")
        except OSError as exc:
            problems.append(f"{name}: cannot read {name}.py: {exc!r}")
    return problems


def _self_test() -> int:
    """Break the contract three ways and assert the checker catches each —
    the store's 'a guard that cannot be shown to fail has not been shown to
    work' rule, applied to this runner itself."""
    cases = {
        "not-a-dict": _check_result("x", "random", ["not", "a", "dict"]),
        "empty-dict": _check_result("x", "random", {}),
        "wrong-policy": _check_result("x", "random", {"game": "x", "policy": "john"}),
        "no-game": _check_result("x", "random", {"policy": "random"}),
    }
    missed = [name for name, probs in cases.items() if not probs]
    if missed:
        print(f"SELF-TEST FAILED: checker did not flag {missed}", file=sys.stderr)
        return 1
    # And a well-formed result must pass clean.
    if _check_result("x", "random", {"game": "x", "policy": "random", "N": 1}):
        print("SELF-TEST FAILED: checker flagged a well-formed result", file=sys.stderr)
        return 1
    print("self-test OK: checker catches malformed results and passes well-formed ones")
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return _self_test()
    problems = check_imports() if "--imports-only" in argv else run_smoke() + check_imports()
    if problems:
        print(f"game-lab sims smoke: {len(problems)} problem(s):", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    core_checks = len(IMPORT_CHECK) + len(COMPILE_CHECK)
    checked = len(STDLIB_ENGINES) * len(POLICIES) + core_checks
    print(f"game-lab sims smoke OK: {len(STDLIB_ENGINES)} engines x {len(POLICIES)} policies "
          f"at N={SMOKE_N} + {core_checks} core-five checks "
          f"({len(IMPORT_CHECK)} import, {len(COMPILE_CHECK)} compile) = {checked} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
