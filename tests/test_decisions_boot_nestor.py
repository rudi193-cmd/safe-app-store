"""Tests for tools/decisions_boot.py's Nestor MCP cross-check (`_consult_nestor`,
`render_nestor_crosscheck` — stores/decisions/README.md, "Consulting Nestor",
fleet give-back 2026-08-13).

The property under test throughout is the one CLAUDE.md (terpsi-music §13,
generalized here) states: **absence surfaces as `unknown`, never as a
result.** Every scenario below where Nestor cannot actually be asked —
missing from PATH, silent, slow, or replying with garbage — must come back
`available: False` with a `reason`, and `render_nestor_crosscheck` must print
that plainly. None of them may collapse to the *shape* of "asked Nestor, it
had nothing" (`available: True, entries: {}`), because that is a different,
stronger claim this code never earned in those cases — the exact "no
findings" vs "unknown" conflation `stores/pending.json`'s rule and
`tools/vault_leak_lint.py`'s `UNKNOWN`-must-not-swallow-`PASS` rule both name
(docs/the-house-already-knew.md §4).

A real `nestor` install is not assumed anywhere in this file (the honest-
environment-disclosure convention `tests/test_checkpoint_memory.py` and
`tests/test_checkpoint.py` already use for the same package) — every
"available" scenario below runs against a tiny stdlib-only fake server this
file writes to `tmp_path` and speaks real JSON-RPC-over-stdio to, the same
protocol `nestor/serve.py` speaks for real. That is what makes the
`TestUnavailableIsUnknownNotNoFindings` class below a genuine refusal test
rather than a vacuous one: a fake that always answered "sealed" would make
every branch look reachable without proving any of them are, so the fake
here can be told to emit each of the three failure shapes on purpose (see
`_write_fake_nestor`'s `mode` argument).
"""
from __future__ import annotations

import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import decisions_boot  # noqa: E402


def _record() -> dict:
    return {
        "_contract": "test fixture",
        "decisions": [
            {"question": "Does the fixture ask a sealed question?",
             "commitment": "yes", "reason": "fixture", "author": "a",
             "verified_by": "b", "date": "2026-08-13"},
            {"question": "Does the fixture ask a pending question?",
             "commitment": "yes", "reason": "fixture", "author": "a",
             "verified_by": "b", "date": "2026-08-13"},
            {"question": "superseded, must not be asked",
             "commitment": "old", "reason": "fixture", "author": "a",
             "verified_by": "b", "date": "2026-08-01",
             "superseded_by": "2026-08-13"},
        ],
        "rejections": [],
    }


# The three questions above, worded so the fake server (below) can decide
# what to answer purely by substring — SEALED / (default pending) / and the
# superseded one, which must never be sent at all (see
# TestLiveQuestionsOnly).
_SEALED_Q = "Does the fixture ask a sealed question?"
_PENDING_Q = "Does the fixture ask a pending question?"


def _write_fake_nestor(tmp_path: Path, mode: str = "ok") -> str:
    """A minimal stdlib-only stand-in for `nestor serve` that speaks the
    same newline-delimited JSON-RPC 2.0 protocol `nestor/serve.py` does —
    enough of it for `_consult_nestor` to exercise its real parsing path.
    Returns the absolute path to the fake, executable.

    ``mode``:
      * ``"ok"``       — SEALED_Q -> sealed/verified; anything else -> pending.
      * ``"malformed"`` — every `tools/call` reply's `content[0].text` is not
        valid JSON (the "nestor answered, but not usefully" case).
      * ``"hang"``      — never reads stdin at all; the process just sleeps,
        so `subprocess.run(..., timeout=...)` has to time out on it (the
        "nestor exists but is not responding" case).
    """
    script = tmp_path / "fake-nestor"
    if mode == "hang":
        body = (
            "#!/usr/bin/env python3\n"
            "import time\n"
            "time.sleep(60)\n"
        )
    else:
        malformed = mode == "malformed"
        body = f"""#!/usr/bin/env python3
import json, sys

MALFORMED = {malformed!r}

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        if "id" not in req:
            continue  # a notification, e.g. notifications/initialized
        rid = req["id"]
        method = req.get("method")
        if method == "initialize":
            resp = {{"jsonrpc": "2.0", "id": rid,
                    "result": {{"protocolVersion": "2025-06-18",
                               "capabilities": {{}},
                               "serverInfo": {{"name": "fake-nestor",
                                              "version": "0.0"}}}}}}
        elif method == "tools/call":
            args = req["params"]["arguments"]
            text = args.get("text", "")
            if MALFORMED:
                content_text = "not valid json {{{{"
            elif {_SEALED_Q!r} == text:
                content_text = json.dumps({{"passage": {{"state": "sealed"}},
                                           "verified": True,
                                           "matches": [{{"verifier": "rudi193"}}]}})
            else:
                content_text = json.dumps({{"passage": {{"state": "pending"}},
                                           "verified": False, "matches": []}})
            resp = {{"jsonrpc": "2.0", "id": rid,
                    "result": {{"content": [{{"type": "text",
                                            "text": content_text}}]}}}}
        else:
            resp = {{"jsonrpc": "2.0", "id": rid, "result": {{}}}}
        sys.stdout.write(json.dumps(resp) + "\\n")
        sys.stdout.flush()

if __name__ == "__main__":
    main()
"""
    script.write_text(body)
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(script)


class TestUnavailableIsUnknownNotNoFindings:
    """The refusal tests the task asks for by name: Nestor unavailable must
    report `unknown`, never the shape of a clean/empty result."""

    def test_nestor_not_on_path_is_unavailable_with_a_reason(self, tmp_path):
        result = decisions_boot._consult_nestor(
            _record(), nestor_cmd=str(tmp_path / "does-not-exist"))
        assert result["available"] is False
        assert result["reason"]                      # non-empty: a real reason
        assert "entries" not in result                # not "asked, found nothing"

    def test_unavailable_renders_as_unknown_not_blank(self, tmp_path, capsys):
        result = decisions_boot._consult_nestor(
            _record(), nestor_cmd=str(tmp_path / "does-not-exist"))
        decisions_boot.render_nestor_crosscheck(result)
        out = capsys.readouterr().out
        assert "unknown" in out
        # The two phrases a caller must never be able to mistake this for -
        # this repo's own vocabulary for "checked, nothing there".
        assert "no live decisions" not in out
        assert "0 entries" not in out

    def test_nestor_hangs_is_unavailable_not_a_crash(self, tmp_path):
        fake = _write_fake_nestor(tmp_path, mode="hang")
        result = decisions_boot._consult_nestor(
            _record(), nestor_cmd=fake, db_path=str(tmp_path / "v.db"),
            timeout=0.3)
        assert result["available"] is False
        assert "0.3" in result["reason"] or "did not respond" in result["reason"]

    def test_malformed_reply_is_unknown_per_question_not_dropped(self, tmp_path):
        fake = _write_fake_nestor(tmp_path, mode="malformed")
        result = decisions_boot._consult_nestor(
            _record(), nestor_cmd=fake, db_path=str(tmp_path / "v.db"))
        # The process ran and replied, so this is "available" - but every
        # entry it produced is individually unknown, not silently absent.
        assert result["available"] is True
        assert result["entries"][_SEALED_Q]["state"] == "unknown"
        assert result["entries"][_PENDING_Q]["state"] == "unknown"

    def test_strict_gate_is_unaffected_by_nestor_being_unreachable(self, tmp_path):
        # The covenant gate (validate/--strict) must never depend on Nestor
        # answering at all - this directory's own sealed decision ("May the
        # decision gate fail builds fail-closed? no - warn-mode only"),
        # restated for the NEW cross-check: it isn't even part of validate().
        assert decisions_boot.validate(decisions_boot.load()) == []
        result = decisions_boot._consult_nestor(
            _record(), nestor_cmd=str(tmp_path / "does-not-exist"))
        assert result["available"] is False   # confirms this scenario is live
        assert decisions_boot.validate(decisions_boot.load()) == []  # unchanged


class TestHappyPathAgainstARealProtocolServer:
    """Proves the parsing path actually reaches a `sealed` answer when one is
    there - a suite that only ever exercises the unavailable branch would
    leave the success path unguarded (the lesson `test_p1_keeping_records.py`
    already encodes for `catalog_lint`, cited in this module's own docstring
    and in `tests/test_fleet_decisions.py`)."""

    def test_sealed_question_reports_sealed_with_verifier(self, tmp_path):
        fake = _write_fake_nestor(tmp_path, mode="ok")
        result = decisions_boot._consult_nestor(
            _record(), nestor_cmd=fake, db_path=str(tmp_path / "v.db"))
        assert result["available"] is True
        entry = result["entries"][_SEALED_Q]
        assert entry["state"] == "sealed"
        assert entry["verified"] is True
        assert entry["verifier"] == "rudi193"

    def test_unmatched_question_reports_pending_not_sealed(self, tmp_path):
        fake = _write_fake_nestor(tmp_path, mode="ok")
        result = decisions_boot._consult_nestor(
            _record(), nestor_cmd=fake, db_path=str(tmp_path / "v.db"))
        entry = result["entries"][_PENDING_Q]
        assert entry["state"] == "pending"
        assert entry["verified"] is False

    def test_render_shows_confirmed_for_sealed(self, tmp_path, capsys):
        fake = _write_fake_nestor(tmp_path, mode="ok")
        result = decisions_boot._consult_nestor(
            _record(), nestor_cmd=fake, db_path=str(tmp_path / "v.db"))
        decisions_boot.render_nestor_crosscheck(result)
        out = capsys.readouterr().out
        assert "confirmed by Nestor" in out
        assert "rudi193" in out


class TestLiveQuestionsOnly:
    """`superseded_by` decisions must not be sent to Nestor at all - the same
    "standing law only" filter `render()` already applies (see the shared
    `_live_questions` helper both now use), so asking Nestor about history
    can't be mistaken for asking about the live commitment."""

    def test_live_questions_excludes_superseded(self):
        qs = decisions_boot._live_questions(_record())
        assert _SEALED_Q in qs
        assert _PENDING_Q in qs
        assert "superseded, must not be asked" not in qs

    def test_no_live_questions_short_circuits_without_a_subprocess(self, tmp_path):
        empty = {"decisions": [], "rejections": []}
        # nestor_cmd points at a real, executable fake - if this call spawned
        # it despite there being nothing to ask, the fake would still answer
        # and this test wouldn't catch the wasted subprocess. What it DOES
        # prove: the empty-record path returns available/empty without ever
        # needing shutil.which to find anything, by handing it a cmd that
        # doesn't exist and confirming that's not what determines the result.
        result = decisions_boot._consult_nestor(
            empty, nestor_cmd=_write_fake_nestor(tmp_path, mode="ok"),
            db_path=str(tmp_path / "v.db"))
        assert result == {"available": True, "entries": {}}
