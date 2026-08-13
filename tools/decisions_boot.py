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

CLAUDE.md rule 11's other half — "check Nestor (has a human checked this —
seal, durable rejection, ledger)" — was prose only until this file grew
`_consult_nestor` (stores/decisions/README.md, "Consulting Nestor," fleet
give-back 2026-08-13): a best-effort SECOND read of "has a human checked
this," over the real MCP protocol against whatever Nestor vault the operator
has running (`.mcp.json`'s "nestor" entry), alongside this file's own
`verified_by` field. It is fail-open by construction — no `nestor` on PATH,
no reply inside the timeout, or a malformed reply all report `unknown`,
never a false "clean," and never a reason to fail `--strict`. See
`_consult_nestor`'s docstring for the covenant this keeps.

Usage:
  tools/decisions_boot.py              # render the boot readout
  tools/decisions_boot.py --strict     # exit 1 on any covenant violation (CI)
  tools/decisions_boot.py --no-nestor  # skip the best-effort Nestor cross-check
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

RECORD = Path(__file__).resolve().parents[1] / "stores" / "decisions" / "fleet.json"

# ── the Nestor MCP cross-check (best-effort, fail-open) ─────────────────────
#
# All three are env-overridable so a caller can point this at a different
# vault (or a fake one, for tests) without editing this file — the same
# override pattern scripts/nestor_decisions_probe.py uses for NESTOR_PATH.
NESTOR_CMD = os.environ.get("NESTOR_CMD", "nestor")
NESTOR_DECISIONS_DB = os.environ.get(
    "NESTOR_DECISIONS_DB",
    str(RECORD.parent / ".nestor" / "vault.db"),
)
NESTOR_MCP_TIMEOUT = float(os.environ.get("NESTOR_MCP_TIMEOUT", "5"))


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


def _live_questions(record: dict) -> list[str]:
    """Questions with a current answer — same filter `render` uses for the
    standing-law section, so the cross-check asks about exactly what the
    reader just saw rendered as live, not superseded history."""
    return [d["question"] for d in record.get("decisions", [])
            if not d.get("superseded_by") and d.get("question")]


def _consult_nestor(record: dict, timeout: float = NESTOR_MCP_TIMEOUT,
                    nestor_cmd: "str | None" = None,
                    db_path: "str | None" = None) -> dict:
    """Ask the real Nestor MCP server (`nestor serve`, over its actual
    stdio JSON-RPC protocol — the same one `.mcp.json`'s "nestor" entry
    speaks to a model) whether each live decision in ``record`` is already
    known to the operator's Nestor vault. A second, independent read of
    "has a human checked this," alongside this file's own `verified_by`.

    The covenant this keeps (terpsi-music CLAUDE.md §13, restated for this
    repo): **absence surfaces as `unknown`, never as a result.** Every path
    that cannot produce a real answer — `nestor` missing from PATH, the
    subprocess not replying inside `timeout`, a reply that fails to parse —
    returns ``{"available": False, "reason": ...}``, not an empty/silent
    `{"available": True, "entries": {}}` that would misreport "asked Nestor,
    it found nothing" when what actually happened is "never reached
    Nestor at all." Those are different facts; conflating them is exactly
    the "no findings" vs "unknown" defect this function's own tests
    (tests/test_decisions_boot_nestor.py) are pinned against.

    Never raises. Never makes `--strict` fail on Nestor's absence — this
    directory's own sealed decision is warn-mode only for the covenant gate
    above, and Nestor being unreachable is a weaker signal than that: this
    function is not even part of `validate()`.

    One subprocess for the whole record, not one per question: every
    question is sent as a separate JSON-RPC `tools/call` request over the
    same stdin batch (`nestor serve`'s `Server.run` reads newline-delimited
    requests until EOF and answers each in turn — see its own `run()`), so
    N questions cost one process spawn, not N.
    """
    nestor_cmd = nestor_cmd if nestor_cmd is not None else NESTOR_CMD
    db_path = db_path if db_path is not None else NESTOR_DECISIONS_DB

    resolved = shutil.which(nestor_cmd)
    if resolved is None:
        return {"available": False,
                "reason": f"{nestor_cmd!r} not found on PATH — Nestor is "
                          f"not installed here (stores/decisions/README.md, "
                          f"'Consulting Nestor', has the install line)"}

    questions = _live_questions(record)
    if not questions:
        return {"available": True, "entries": {}}

    # id 1 is the handshake; questions start at 2 so a reply's id maps back
    # to `questions[id - 2]` with no separate id->question table to keep in
    # sync.
    requests: list[dict] = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18",
                    "clientInfo": {"name": "decisions_boot"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
    ]
    for i, question in enumerate(questions, start=2):
        requests.append({
            "jsonrpc": "2.0", "id": i, "method": "tools/call",
            "params": {"name": "nestor_ask",
                       "arguments": {"text": question,
                                    "source_lang": "decision",
                                    "target_lang": "decision"}},
        })
    payload = "\n".join(json.dumps(r) for r in requests) + "\n"

    cmd = [resolved, "serve", "--db", db_path,
           "--source-lang", "decision", "--target-lang", "decision"]
    try:
        proc = subprocess.run(cmd, input=payload, capture_output=True,
                              text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False,
                "reason": f"nestor serve did not respond within {timeout}s "
                          f"({type(exc).__name__}: {exc})"}

    entries: dict[str, dict] = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue                     # not a JSON-RPC line; ignore it
        rid = msg.get("id")
        if not isinstance(rid, int) or not (2 <= rid < 2 + len(questions)):
            continue                     # the handshake reply, or unrelated
        question = questions[rid - 2]
        result = msg.get("result")
        if not isinstance(result, dict) or result.get("isError"):
            entries[question] = {"state": "unknown",
                                 "detail": _error_text(result)}
            continue
        try:
            answer = json.loads(result["content"][0]["text"])
        except (KeyError, IndexError, TypeError, ValueError):
            entries[question] = {"state": "unknown",
                                 "detail": "reply did not parse as the "
                                          "expected nestor_ask payload"}
            continue
        entries[question] = {
            "state": answer.get("passage", {}).get("state", "unknown"),
            "verified": bool(answer.get("verified")),
            "verifier": (answer.get("matches") or [{}])[0].get("verifier", ""),
        }

    if not entries:
        # A process that ran and exited but produced nothing usable is the
        # same "could not actually ask" fact as never starting it — a wrong
        # --db, a crash before the handshake, a protocol version neither
        # side agreed on. Reported the same way, not as a silent empty
        # `entries`, for the same reason this whole function exists.
        return {"available": False,
                "reason": "nestor serve produced no usable replies "
                          f"(stderr: {proc.stderr.strip()[:200]!r})"}
    return {"available": True, "entries": entries}


def _error_text(result: "dict | None") -> str:
    try:
        return result["content"][0]["text"]
    except (KeyError, IndexError, TypeError):
        return "no detail in reply"


def render_nestor_crosscheck(nestor_result: dict, out=None) -> None:
    """Print `_consult_nestor`'s result. `unavailable` is its own line, never
    silently folded into "0 entries" — see `_consult_nestor`'s docstring.

    ``out`` defaults to the CURRENT ``sys.stdout`` at call time (resolved
    inside the function body, not as a parameter default) so a caller that
    swaps ``sys.stdout`` after import — a test's ``capsys``, a context
    manager — is honored, the same way ``render()``'s own callers always
    pass ``out`` explicitly rather than relying on the default for that
    reason.
    """
    if out is None:
        out = sys.stdout
    if not nestor_result.get("available"):
        print(f"nestor cross-check: unknown - {nestor_result.get('reason', '')}",
              file=out)
        return
    entries = nestor_result.get("entries", {})
    if not entries:
        print("nestor cross-check: available, no live decisions to ask",
              file=out)
        return
    print("nestor cross-check (independent of this file's own verified_by):",
          file=out)
    for question, entry in entries.items():
        state = entry.get("state", "unknown")
        if state == "sealed":
            tag = f"confirmed by Nestor (verifier: {entry.get('verifier') or '?'})"
        elif state == "unknown":
            tag = f"unknown - {entry.get('detail', '')}"
        else:
            tag = f"Nestor state: {state}"
        print(f"  {question}: {tag}", file=out)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--strict", action="store_true",
                   help="exit 1 on covenant violations (CI gate)")
    p.add_argument("--record", default=str(RECORD),
                   help="path to fleet.json (default: the repo's)")
    p.add_argument("--no-nestor", action="store_true",
                   help="skip the best-effort Nestor MCP cross-check")
    p.add_argument("--nestor-timeout", type=float, default=NESTOR_MCP_TIMEOUT,
                   help=f"seconds to wait for nestor serve (default "
                        f"{NESTOR_MCP_TIMEOUT})")
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
    if not args.no_nestor:
        # Fail-open: nothing this call can do reaches `return 1` above, by
        # construction (see _consult_nestor's docstring) — it always
        # returns a dict, never raises.
        render_nestor_crosscheck(_consult_nestor(record, timeout=args.nestor_timeout))
    return 0


if __name__ == "__main__":
    sys.exit(main())
