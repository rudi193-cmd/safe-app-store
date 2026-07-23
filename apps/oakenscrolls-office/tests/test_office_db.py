import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("OAKENSCROLL_DB", str(tmp_path / "office.db"))
    import office_db
    return office_db


def test_state_and_derive(db):
    pid = db.state_claim("it rains tomorrow", 0.7, due=int(time.time()) + 60)
    r = db.current(pid)
    assert r["status"] == "open" and r["confidence"] == 0.7 and r["revisions"] == 0


def test_confidence_convention_enforced(db):
    with pytest.raises(ValueError):
        db.state_claim("hedged backwards", 0.3)
    with pytest.raises(ValueError):
        db.state_claim("false prophet", 1.0)
    with pytest.raises(ValueError):
        db.state_claim("   ", 0.7)


def test_revision_is_append_only(db):
    pid = db.state_claim("the PR merges this week", 0.6)
    db.revise(pid, 0.8)
    r = db.current(pid)
    assert r["confidence"] == 0.8
    assert r["stated_confidence"] == 0.6  # the original never mutates
    assert r["revisions"] == 1


def test_resolve_void_reopen_lifecycle(db):
    pid = db.state_claim("the demo works first try", 0.55)
    db.resolve(pid, False)
    assert db.current(pid)["status"] == "resolved"
    with pytest.raises(ValueError):
        db.resolve(pid, True)  # only open predictions resolve
    db.reopen(pid, "graded too early")
    assert db.current(pid)["status"] == "open"
    db.void(pid, "claim was ambiguous")
    r = db.current(pid)
    assert r["status"] == "voided" and r["outcome"] is None  # record kept


def test_due_now_and_scoring_pairs(db):
    past = db.state_claim("already due", 0.9, due=int(time.time()) - 10)
    db.state_claim("due later", 0.6, due=int(time.time()) + 9999)
    db.state_claim("open-ended", 0.7)
    assert [d["id"] for d in db.due_now()] == [past]

    db.revise(past, 0.75)
    db.resolve(past, True)
    voided = db.state_claim("ambiguous thing", 0.8, due=int(time.time()) - 5)
    db.void(voided)
    assert db.resolved_pairs() == [(0.75, True)]  # latest confidence; void never scores


def test_resolve_with_evidence_round_trips(db):
    pid = db.state_claim("global temps set a record this year", 0.8)
    cite = {"kind": "almanac-data", "vertical": "climate-almanac",
            "entry_id": "berkeley-earth-temperature", "catalog_commit": "b" * 40}
    db.resolve(pid, True, evidence=cite)
    r = db.current(pid)
    assert r["evidence"]["entry_id"] == "berkeley-earth-temperature"
    assert r["evidence"]["catalog_commit"] == "b" * 40
    # evidence rides the resolving event: reopen clears it from derived state
    db.reopen(pid)
    assert db.current(pid)["evidence"] is None


def test_resolve_without_evidence_still_fine(db):
    pid = db.state_claim("plain grading works", 0.6)
    db.resolve(pid, True)
    assert db.current(pid)["evidence"] is None


def test_unknown_id_raises(db):
    with pytest.raises(KeyError):
        db.current("nope1234")
    with pytest.raises(KeyError):
        db.resolve("nope1234", True)
