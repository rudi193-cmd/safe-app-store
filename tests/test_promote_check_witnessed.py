"""The `witnessed [M]` gate — floor + fail-closed shape, WITHOUT the cloud seam.

These are the branches of `_witnessed()` that resolve before it ever tries to
import forge.trust/willow-gate/nestor, so they run in the plain store suite (no
seam installed) and pin the two things that must hold everywhere:

  * the FLOOR is unchanged — a promotion with no `trust` block is judged by the
    same string check as before (verified_by set and ≠ author);
  * a promotion that DECLARES a seal but is malformed is DENIED, never quietly
    dropped back to the floor.

The real cryptographic verification (a valid seal passing, a tampered ledger
failing) needs the seam and lives in test_promote_check_seal.py.
"""
import importlib.util
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("promote_check", _REPO / "stores" / "promote_check.py")
promote_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(promote_check)


def _att(**over) -> dict:
    a = {"author": "vishwakarma", "verified_by": "loki", "app_id": "widget"}
    a.update(over)
    return a


# ── the floor: no seal declared, string check as before ───────────────────────

def test_floor_passes_when_verifier_set_and_differs(tmp_path):
    g, ok, detail = promote_check._witnessed(tmp_path, _att())
    assert g == "witnessed [M]" and ok is True
    assert "attested — no seal declared" in detail


def test_floor_fails_when_verifier_equals_author(tmp_path):
    _, ok, detail = promote_check._witnessed(tmp_path, _att(verified_by="vishwakarma"))
    assert ok is False and "differ from author" in detail


def test_floor_fails_when_verifier_empty(tmp_path):
    _, ok, _ = promote_check._witnessed(tmp_path, _att(verified_by=""))
    assert ok is False


# ── a declared seal that is malformed is DENIED, not dropped to the floor ──────

def test_declared_seal_with_broken_floor_is_denied(tmp_path):
    # author == verifier: the string floor already fails, and declaring a seal
    # must not paper over it.
    att = _att(verified_by="vishwakarma", trust={"verifier_id": "vishwakarma",
                                                 "author_id": "agent:x",
                                                 "custody": "c.jsonl", "checkpoint": "k.json"})
    _, ok, detail = promote_check._witnessed(tmp_path, att)
    assert ok is False and "floor fails" in detail


def test_trust_block_not_an_object_is_denied(tmp_path):
    _, ok, detail = promote_check._witnessed(tmp_path, _att(trust="yes-please"))
    assert ok is False and "not an object" in detail


def test_verifier_id_must_equal_verified_by(tmp_path):
    att = _att(trust={"verifier_id": "someone_else", "author_id": "agent:x",
                      "custody": "c.jsonl", "checkpoint": "k.json"})
    _, ok, detail = promote_check._witnessed(tmp_path, att)
    assert ok is False and "must equal verified_by" in detail


def test_missing_author_id_is_denied(tmp_path):
    att = _att(trust={"verifier_id": "loki", "custody": "c.jsonl", "checkpoint": "k.json"})
    _, ok, detail = promote_check._witnessed(tmp_path, att)
    assert ok is False and "author_id missing" in detail


def test_custody_path_escaping_candidate_is_denied(tmp_path):
    att = _att(trust={"verifier_id": "loki", "author_id": "agent:x",
                      "custody": "../../../etc/passwd", "checkpoint": "k.json"})
    _, ok, detail = promote_check._witnessed(tmp_path, att)
    assert ok is False and "escapes the candidate" in detail


def test_within_rejects_escape_and_empty(tmp_path):
    assert promote_check._within(tmp_path, "") is None
    assert promote_check._within(tmp_path, "../x") is None
    inside = promote_check._within(tmp_path, "trust/c.jsonl")
    assert inside is not None and str(inside).endswith("trust/c.jsonl")
