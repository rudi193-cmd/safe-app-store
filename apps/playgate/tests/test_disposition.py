"""The disposition log: reasoned both ways, append-only, and honest about no."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from playgate.disposition import (
    EXPIRED,
    GRANTED,
    OPEN,
    REFUSED,
    DispositionError,
    Log,
)
from playgate.interruption import Interruption

ROSTER = ("kid1", "kid2")
START = datetime(2026, 8, 2, 9, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self, now: datetime):
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture()
def log(tmp_path):
    made = Log(path=tmp_path / "requests.jsonl", roster=ROSTER)
    made.clock = Clock(START)
    counter = iter(f"r{n:03d}" for n in range(1, 999))
    made.new_id = lambda: next(counter)
    return made


# -- identity --------------------------------------------------------------

def test_subject_must_be_on_the_roster(log):
    """The kid UI offers a fixed list rather than a text box. A consent log
    whose subject is a name the requester typed records an assertion, not an
    identity."""
    with pytest.raises(DispositionError, match="not on the roster"):
        log.request(subject_id="kid9", app_id="sgt-puzzles", asked_by="Maya")


def test_an_empty_roster_is_refused(tmp_path):
    with pytest.raises(DispositionError, match="roster is empty"):
        Log(path=tmp_path / "r.jsonl", roster=())


# -- asking ----------------------------------------------------------------

def test_a_request_opens_with_a_due_date(log):
    row = log.request("kid1", "sgt-puzzles", "Maya", within_hours=48)
    assert row["disposition"] == OPEN
    assert row["due_by"] == (START + timedelta(hours=48)).isoformat()
    assert log.open_requests() == [log.current(row["request_id"])]


# -- answering -------------------------------------------------------------

def test_a_reason_is_required_to_refuse(log):
    row = log.request("kid1", "sgt-puzzles", "Maya")
    with pytest.raises(DispositionError, match="reason is required"):
        log.answer(row["request_id"], granted=False, by="Parent", reason="   ")


def test_a_reason_is_required_to_grant_as_well(log):
    """The asymmetry every app store has: installs are logged, reasons are not.
    A grant with no reason is indistinguishable from no decision six months on.
    """
    row = log.request("kid1", "sgt-puzzles", "Maya")
    with pytest.raises(DispositionError, match="reason is required"):
        log.answer(row["request_id"], granted=True, by="Parent", reason="")


def test_an_unnamed_parent_cannot_answer(log):
    row = log.request("kid1", "sgt-puzzles", "Maya")
    with pytest.raises(DispositionError, match="unnamed"):
        log.answer(row["request_id"], granted=True, by="  ", reason="fine by me")


def test_a_refusal_is_a_row_not_a_silence(log):
    """A refused request and a request nobody ever made are different facts."""
    row = log.request("kid1", "sgt-puzzles", "Maya")
    log.answer(row["request_id"], granted=False, by="Parent", reason="not before homework")
    state = log.current(row["request_id"])
    assert state["disposition"] == REFUSED
    assert state["reason"] == "not before homework"
    assert log.open_requests() == []


def test_an_unasked_app_has_no_row_at_all(log):
    """The other half of the same distinction: absence of a decision is not a
    refusal, and the log must not manufacture one."""
    log.request("kid1", "sgt-puzzles", "Maya")
    assert log.current("nonexistent") is None


def test_an_unanswered_request_expires_without_being_rewritten(log):
    """Expiry is derived on read, never appended. An unanswered request must not
    become an answered one on disk just because time passed."""
    row = log.request("kid1", "sgt-puzzles", "Maya", within_hours=1)
    log.clock.advance(hours=2)
    assert log.current(row["request_id"])["disposition"] == EXPIRED
    kinds = [r["kind"] for r in log.history(row["request_id"])]
    assert kinds == ["request"], "expiry wrote a row"


# -- the record cannot be edited ------------------------------------------

def test_answering_twice_is_refused(log):
    row = log.request("kid1", "sgt-puzzles", "Maya")
    log.answer(row["request_id"], granted=False, by="Parent", reason="not today")
    with pytest.raises(DispositionError, match="already refused"):
        log.answer(row["request_id"], granted=True, by="Parent", reason="changed my mind")


def test_history_keeps_every_row_while_current_folds_them(log):
    row = log.request("kid1", "sgt-puzzles", "Maya")
    rid = row["request_id"]
    log.answer(rid, granted=True, by="Parent", reason="ok for the weekend")
    log.record_install(rid, ok=False, detail="adb not on PATH")

    assert [r["kind"] for r in log.history(rid)] == ["request", "answer", "install"]
    # The fold reports the latest state; the rows behind it are still there.
    assert log.current(rid)["disposition"] == "install_failed"
    assert log.current(rid)["reason"] == "ok for the weekend"


def test_a_failed_install_is_written_down(log):
    """A grant that never installed and a grant that installed cleanly are
    different facts. Leaving the failure unwritten would make the log agree with
    the optimistic reading by default."""
    row = log.request("kid1", "sgt-puzzles", "Maya")
    rid = row["request_id"]
    log.answer(rid, granted=True, by="Parent", reason="fine")
    log.record_install(rid, ok=False, detail="sha256 mismatch")
    detail = [r for r in log.history(rid) if r["kind"] == "install"][0]
    assert detail["disposition"] == "install_failed"
    assert detail["detail"] == "sha256 mismatch"


# -- evidence at the time of the decision ---------------------------------

def test_the_answer_snapshots_the_evidence_the_parent_had(log):
    """The catalog will change under this row — someone will measure an app
    that was assumed, a new build will demote a measurement. A log holding only
    the current value can confirm the present state but cannot be used to ask
    whether the reasoning was sound."""
    row = log.request("kid1", "sgt-puzzles", "Maya")
    log.answer(
        row["request_id"], granted=True, by="Parent", reason="looks quiet",
        interruption=Interruption(provenance="assumed", note="nobody has looked"),
    )
    answer = [r for r in log.history(row["request_id"]) if r["kind"] == "answer"][0]
    assert answer["interruption_at_decision"]["provenance"] == "assumed"


def test_rows_survive_a_reopen(log, tmp_path):
    row = log.request("kid1", "sgt-puzzles", "Maya")
    log.answer(row["request_id"], granted=False, by="Parent", reason="no")
    reopened = Log(path=log.path, roster=ROSTER)
    assert len(reopened.rows()) == 2


# -- who asked, and what they can see back --------------------------------

def test_an_unchosen_subject_is_refused_as_its_own_case(tmp_path):
    # A picker that defaults to the first child satisfies "the name came from a
    # list" and still records the wrong person. "" means nobody chose, and it
    # gets a message that says so rather than a roster miss.
    log = Log(path=tmp_path / "d.jsonl", roster=("mira", "theo"))
    with pytest.raises(DispositionError, match="a default is not a choice"):
        log.request("", "sgt-puzzles", asked_by="mira")


def test_for_subject_returns_that_childs_requests_folded(tmp_path):
    log = Log(path=tmp_path / "d.jsonl", roster=("mira", "theo"))
    a = log.request("theo", "sgt-puzzles", asked_by="theo")
    log.request("mira", "frozen-bubble", asked_by="mira")
    b = log.request("theo", "vector-pinball", asked_by="theo")
    log.answer(b["request_id"], granted=False, by="parent", reason="school night")

    theo = log.for_subject("theo")
    assert {r["app_id"] for r in theo} == {"sgt-puzzles", "vector-pinball"}
    by_app = {r["app_id"]: r for r in theo}
    assert by_app["sgt-puzzles"]["disposition"] == OPEN
    assert by_app["sgt-puzzles"]["request_id"] == a["request_id"]
    # The refusal is returned, not filtered out: a child who only sees pending
    # rows is told that a request they made was never made at all.
    assert by_app["vector-pinball"]["disposition"] == REFUSED
    assert by_app["vector-pinball"]["reason"] == "school night"


def test_for_subject_does_not_leak_a_siblings_requests(tmp_path):
    log = Log(path=tmp_path / "d.jsonl", roster=("mira", "theo"))
    log.request("mira", "frozen-bubble", asked_by="mira")
    assert log.for_subject("theo") == []
    assert [r["app_id"] for r in log.for_subject("mira")] == ["frozen-bubble"]


def test_for_subject_reports_an_expiry_the_child_can_act_on(tmp_path):
    log = Log(path=tmp_path / "d.jsonl", roster=("theo",))
    log.request("theo", "sgt-puzzles", asked_by="theo", within_hours=1)
    log.clock = staticmethod(
        lambda: datetime.now(timezone.utc) + timedelta(hours=2))
    assert log.for_subject("theo")[0]["disposition"] == EXPIRED
