"""the-table -- test_menu.py (box-build R12, C14, C15; rival T12).

The closed menu: a fake model may only pick a move id from ``legal_moves``.
Every other answer -- an invented move, an index, a bare stat, ESCALATE, a
crash -- is refused, code picks, and one ``escalate`` verdict row records it.
No model is reachable here; every model is a deterministic fake.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile

import pytest

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _APP_ROOT)

from the_table import menu
from the_table import onescript_sink as osk
from the_table.story_session import StorySession
from the_table.worlds import WorldError, load_world

WORLD = os.path.join(_APP_ROOT, "worlds", "hasbeen.json")
SEED = "7" * 64


class FakeRecord:
    def __init__(self):
        self.rows: list[dict] = []

    def write(self, row: dict) -> dict:
        body = {"n": len(self.rows), "kind": "verdict", "who": "table", "hash": f"h{len(self.rows)}", **row}
        self.rows.append(body)
        return {"row": body, "code": 0}


class Fake:
    """A deterministic fake model: ``answers`` are returned in order, the
    last one repeated; an Exception instance is raised."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, menu_ids):
        self.calls.append(list(menu_ids))
        a = self.answers[min(len(self.calls) - 1, len(self.answers) - 1)]
        if isinstance(a, Exception):
            raise a
        return a


def play(choose, world=WORLD, **kw):
    rec = FakeRecord()
    s = StorySession(world)
    sink = osk.OneScriptSink(rec.write)
    policy = menu.menu_policy(choose, sink=sink, **kw)
    pending = osk.play_to_decision(s, policy, sink, seed=SEED, session_id="s1")
    return s, sink, rec, policy, pending


def escalates(rec):
    return [r for r in rec.rows if r["what"] == "escalate"]


# ── the honest pick ──────────────────────────────────────────────────────────
def test_an_honest_pick_from_the_menu_is_taken_and_code_rolls():
    fake = Fake("act:Cool", {"path": "act:Grit", "claim": "grit it out", "cites": []})
    _, _, rec, policy, pending = play(fake)
    assert fake.calls[0] == ["act:Grit", "act:Weird", "act:Cute", "act:Cool"]
    rolls = [r for r in rec.rows if r["what"] == "roll"]
    assert [r["move"] for r in rolls] == [["act", "Cool"], ["act", "Grit"]]
    assert all(isinstance(r["total"], int) for r in rolls)  # code rolled
    assert policy.refusals == [] and escalates(rec) == []
    assert pending is not None  # stopped at the decision beat


def test_a_lying_claim_changes_nothing_the_pick_is_the_id_only():
    fake = Fake({"path": "act:Weird", "claim": "I rolled a 12", "cites": []})
    _, _, rec, policy, _ = play(fake)
    roll = next(r for r in rec.rows if r["what"] == "roll")
    assert roll["move"] == ["act", "Weird"]
    assert "I rolled" not in json.dumps(rec.rows)  # the claim is never a fact on record
    assert roll["total"] == roll["roll"]["result"]  # the total is code's roll, not the claim
    assert policy.refusals == []


# ── T12: outside legal_moves is refused ──────────────────────────────────────
@pytest.mark.parametrize("got", [
    "act:Fly",                       # an invented move
    "Grit",                          # a bare stat, not an id
    7,                               # an index out of range
    0,                               # an index in range is still not an id
    ("act", "Fly"),                  # a move tuple
    ["act", "Grit"],                 # a legal move, but not its id
    {"path": "act:Fly", "claim": "x", "cites": []},
])
def test_T12_off_menu_choice_falls_back_and_escalates(got):
    fake = Fake(got, "act:Grit")
    _, _, rec, policy, _ = play(fake)
    (ref,) = policy.refusals
    assert ref["reason"] in (menu.OFF_MENU, menu.UNREACHABLE) and ref["to"] == "human"
    assert ref["took"] == "act:Grit"  # the first legal move, by code
    (row,) = escalates(rec)
    assert row["verdict"] == "escalate" and row["took"] == "act:Grit"
    assert row["menu"] == ["act:Grit", "act:Weird", "act:Cute", "act:Cool"]
    assert row["beat"] == "b1" and "proof" not in row
    first = next(r for r in rec.rows if r["what"] == "roll")
    assert first["move"] == ["act", "Grit"]


def test_a_models_ESCALATE_goes_to_the_human_and_code_plays_on():
    fake = Fake({"path": "ESCALATE", "claim": "no good move here", "cites": []}, "act:Cute")
    _, _, rec, policy, pending = play(fake)
    (ref,) = policy.refusals
    assert ref == {**ref, "reason": "escalate", "why": "no good move here", "to": "human"}
    (row,) = escalates(rec)
    assert row["to"] == "human" and "no good move here" in row["reason"]
    assert pending is not None  # the story still reached the decision beat


def test_an_unreachable_model_falls_back_to_code():
    fake = Fake(TimeoutError("ollama down"))
    _, _, rec, policy, pending = play(fake)
    assert [r["reason"] for r in policy.refusals] == ["unreachable", "unreachable"]
    assert all(r["took"] in ("act:Grit",) for r in policy.refusals)
    assert len(escalates(rec)) == 2 and pending is not None


# ── C14: a decision beat never reaches choose ────────────────────────────────
def test_decision_beat_never_reaches_choose():
    fake = Fake("act:Grit")
    s, _, _, policy, pending = play(fake)
    assert pending is not None and s.pending_seal() is not None
    assert len(fake.calls) == 2  # two action beats, then the decision stopped the loop
    with pytest.raises(RuntimeError, match="never on the menu"):
        policy(s, s.current_seat())
    assert len(fake.calls) == 2  # still: refused before any model was asked


# ── C15: set_piece ───────────────────────────────────────────────────────────
def set_piece_world(tmpdir, flag):
    w = load_world(WORLD)
    w = copy.deepcopy(w)
    if flag is not None:
        w["scenes"][0]["beats"][1]["set_piece"] = flag
    p = os.path.join(tmpdir, "w.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(w, fh)
    return p


def test_set_piece_loads_and_shows_in_the_view():
    with tempfile.TemporaryDirectory() as d:
        s = StorySession(set_piece_world(d, True))
        s.reset(1)
        assert s.observe(0).view["set_piece"] is False
        s.step(0, ("act", "Grit"))
        assert s.observe(0).view["set_piece"] is True
        with pytest.raises(WorldError, match="set_piece"):
            load_world(set_piece_world(d, "yes"))
    s = StorySession(WORLD)
    s.reset(1)
    assert s.observe(0).view["set_piece"] is False  # default false


def test_no_set_piece_no_model_when_the_policy_is_set_piece_only():
    fake = Fake("act:Cool")
    with tempfile.TemporaryDirectory() as d:
        _, _, rec, _, _ = play(fake, world=set_piece_world(d, None), set_piece_only=True)
        assert fake.calls == []
        assert [r["move"] for r in rec.rows if r["what"] == "roll"] == [["act", "Grit"]] * 2
        fake = Fake("act:Cool")
        _, _, rec, _, _ = play(fake, world=set_piece_world(d, True), set_piece_only=True)
        assert len(fake.calls) == 1  # only the set-piece beat asked
        assert [r["move"] for r in rec.rows if r["what"] == "roll"] == [["act", "Grit"], ["act", "Cool"]]


# ── the ids ──────────────────────────────────────────────────────────────────
def test_move_ids_round_trip_and_nothing_else_matches():
    legal = [("act", "Grit"), ("act", "Weird")]
    assert menu.move_ids(legal) == ["act:Grit", "act:Weird"]
    assert menu.move_of("act:Weird", legal) == ("act", "Weird")
    assert menu.move_of("act:Fly", legal) is None
    assert menu.move_of(1, legal) is None
    assert menu.move_of(("act", "Grit"), legal) is None
    assert menu.read_pick(None) == (None, "not a move id or a propose row: NoneType")
