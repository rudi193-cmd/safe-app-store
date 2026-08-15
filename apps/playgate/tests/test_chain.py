"""The disposition log is a hash chain, and Nestor is what walks it.

Two halves, deliberately split:

* The **writing** half is stdlib and always runs. `prev` is computed here, so
  the core stays third-party-free (`test_no_egress.py`).
* The **verifying** half needs Nestor. Those tests `importorskip`, which means
  they vanish silently on a host without it — and a skipped test still exits 0.
  This repo has already paid for that lesson once (`store-ci.yml`'s
  bureau-differential job: *"that leg reports green having compared nothing"*),
  so `test_the_verifier_actually_ran` fails rather than skips whenever
  `PLAYGATE_REQUIRE_NESTOR=1`, and CI sets it.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playgate import audit                                      # noqa: E402
from playgate.disposition import Log                            # noqa: E402

ROSTER = ("kid1",)


def _log(tmp_path: Path) -> Log:
    return Log(path=tmp_path / "requests.jsonl", roster=ROSTER)


def _lines(log: Log) -> "list[str]":
    return [ln for ln in log.path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _seed(tmp_path: Path) -> Log:
    log = _log(tmp_path)
    row = log.request("kid1", "sgt-puzzles", asked_by="kid1")
    log.answer(row["request_id"], granted=True, by="parent", reason="fine by me")
    log.record_install(row["request_id"], ok=True, detail="installed")
    return log


# -- the writing half: stdlib, always runs -----------------------------------

def test_every_line_carries_the_hash_of_the_one_before_it(tmp_path):
    log = _seed(tmp_path)
    lines = _lines(log)
    assert len(lines) == 3

    prev = Log.GENESIS
    for i, line in enumerate(lines, start=1):
        assert json.loads(line)["prev"] == prev, f"line {i}"
        prev = hashlib.sha256(line.encode("utf-8")).hexdigest()


def test_head_is_the_hash_of_the_last_line(tmp_path):
    log = _seed(tmp_path)
    assert log.head() == hashlib.sha256(
        _lines(log)[-1].encode("utf-8")).hexdigest()


def test_an_empty_or_absent_log_heads_at_genesis(tmp_path):
    log = _log(tmp_path)
    assert log.head() == Log.GENESIS          # nothing written yet
    log.request("kid1", "sgt-puzzles", asked_by="kid1")
    assert log.head() != Log.GENESIS


# -- the verifying half: Nestor ----------------------------------------------

def test_the_verifier_actually_ran():
    """A skipped verification test is a green tick over an unchecked chain."""
    if not os.environ.get("PLAYGATE_REQUIRE_NESTOR"):
        pytest.skip("set PLAYGATE_REQUIRE_NESTOR=1 to require the verifier (CI does)")
    import nestor.ledger                                        # noqa: F401


def test_an_untouched_chain_verifies(tmp_path):
    pytest.importorskip("nestor.ledger")
    log = _seed(tmp_path)
    result = audit.verify(log.path)
    assert result["status"] == audit.OK, result["detail"]
    assert "3 entries" in result["detail"]


def test_editing_a_past_line_is_detected(tmp_path):
    pytest.importorskip("nestor.ledger")
    log = _seed(tmp_path)
    lines = _lines(log)

    # Rewrite the middle line: flip a refusal-shaped decision into a grant.
    edited = json.loads(lines[1])
    edited["reason"] = "actually I never agreed to this"
    lines[1] = json.dumps(edited, sort_keys=True)
    log.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = audit.verify(log.path)
    assert result["status"] == audit.BROKEN
    assert "line 3" in result["detail"]      # the orphaned successor names it


def test_the_newest_line_is_unvouched_until_a_head_is_anchored(tmp_path):
    pytest.importorskip("nestor.ledger")
    log = _seed(tmp_path)
    anchored = log.head()                    # what an operator recorded elsewhere

    lines = _lines(log)
    tampered = json.loads(lines[-1])
    tampered["detail"] = "installed cleanly, honest"
    lines[-1] = json.dumps(tampered, sort_keys=True)
    log.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Nothing follows the last line, so the walk alone still passes...
    assert audit.verify(log.path)["status"] == audit.OK
    # ...and the externally-held head is the only thing that catches it.
    caught = audit.verify(log.path, expected_head=anchored)
    assert caught["status"] == audit.BROKEN
    assert "last entry was edited" in caught["detail"]


def test_a_log_written_before_the_chain_reads_as_unchained_not_tampered(tmp_path):
    pytest.importorskip("nestor.ledger")
    path = tmp_path / "requests.jsonl"
    # Two rows in the pre-chain shape: no `prev` anywhere.
    path.write_text(
        json.dumps({"kind": "request", "request_id": "a1", "at": "2026-01-01T00:00:00"})
        + "\n"
        + json.dumps({"kind": "answer", "request_id": "a1", "at": "2026-01-01T00:01:00"})
        + "\n",
        encoding="utf-8")

    assert audit.unchained_prefix(path) == 2
    result = audit.verify(path)
    # Not BROKEN: nobody edited anything, the lines simply predate the chain.
    assert result["status"] == audit.UNCHAINED
    assert result["unchained"] == 2
    assert "cannot be brought under it now" in result["detail"]


def test_appending_to_a_legacy_log_does_not_retro_chain_it(tmp_path):
    # Retro-chaining would make the whole file walk clean and vouch for lines
    # nothing ever protected. The fleet has this sealed: the migration and the
    # forgery are the same operation.
    path = tmp_path / "requests.jsonl"
    path.write_text(
        json.dumps({"kind": "request", "request_id": "a1", "at": "2026-01-01T00:00:00"})
        + "\n", encoding="utf-8")

    log = Log(path=path, roster=ROSTER)
    log.request("kid1", "sgt-puzzles", asked_by="kid1")

    lines = _lines(log)
    assert "prev" not in json.loads(lines[0])          # untouched
    assert json.loads(lines[1])["prev"] != Log.GENESIS  # chained onto what was there
    assert audit.unchained_prefix(path) == 1


def test_a_missing_verifier_reports_unverifiable_rather_than_ok(tmp_path, monkeypatch):
    log = _seed(tmp_path)

    def _absent():
        raise audit.VerifierUnavailable("nestor is not installed")

    monkeypatch.setattr(audit, "_nestor_verify", _absent)
    result = audit.verify(log.path)
    # The chain is genuinely intact here — the point is that without a verifier
    # this must not be reported as verified.
    assert result["status"] == audit.UNVERIFIABLE
    assert result["status"] != audit.OK


# -- the injection direction --------------------------------------------------

def test_the_core_does_not_import_the_verifier():
    """The host imports Nestor; the core never does — the promotion bar's shape.

    `test_no_egress.py` proves the core pulls in no third-party package. This
    proves the specific seam: `audit` is not reachable from `disposition`, so
    the log can always be written on a host with no Nestor.
    """
    import ast

    core = Path(__file__).resolve().parents[1] / "playgate"
    for module in ("disposition.py", "catalog.py", "install.py", "interruption.py"):
        tree = ast.parse((core / module).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                # level>0 is a relative import; node.module is the sibling name.
                imported.add((node.module or "").split(".")[0])
        # Prose may discuss Nestor — the docstrings do, at length. Only the
        # import graph is the seam, so only the import graph is asserted on.
        assert "nestor" not in imported, f"{module} imports nestor"
        assert "audit" not in imported, f"{module} imports the verifier"
