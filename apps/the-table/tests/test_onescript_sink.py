"""the-table -- test_onescript_sink.py (J4, box-build SPEC R10; SPEC-documented §9 (d)).

The sink is tested against an in-memory stand-in for one-script's
``table.verdict`` (the host injects the real one; the-table never imports
onescript). The cross-repo loop -- real record, real seals -- is
box-build/e2e/test_w2_rows.py.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import sys
import tempfile

import pytest

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _APP_ROOT)

from the_table import onescript_sink as osk
from the_table import peaks, registry
from the_table.dice_source import replay_roll
from the_table.gm import random_policy, run_session
from the_table.ledger_sink import LedgerSink
from the_table.story_session import StorySession
from the_table.worlds import load_world

WORLDS = os.path.join(_APP_ROOT, "worlds")
SUB = "proposal:" + "cd" * 32
SEED = hashlib.sha256(b"sink:hasbeen").hexdigest()


class FakeRecord:
    """Stands in for ``table.verdict`` bound to a box: a chained list."""

    def __init__(self, refuse_at: int | None = None):
        self.rows: list[dict] = []
        self.refuse_at = refuse_at

    def write(self, row: dict) -> dict:
        if self.refuse_at is not None and len(self.rows) == self.refuse_at:
            return {"refused": "no table key on this box", "code": 1}
        prev = self.rows[-1]["hash"] if self.rows else "0" * 64
        body = {"n": len(self.rows), "kind": "verdict", "who": "table", "prev": prev, **row}
        body["hash"] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        self.rows.append(body)
        return {"row": body, "code": 0}


def world(name="hasbeen"):
    return os.path.join(WORLDS, f"{name}.json")


def play(name="hasbeen", seed=SEED, forecast=None, path=None, check=None):
    rec = FakeRecord()
    s = StorySession(path or world(name))
    sink = osk.OneScriptSink(rec.write, check=check, forecast=forecast)
    pending = osk.play_to_decision(s, osk.suggested_policy(), sink, seed=seed, session_id="s1")
    return s, sink, rec, pending


def test_story_turns_become_verdict_rows():
    """One verdict row per action beat; replaying each roll from the seed and
    the seat's own sheet reproduces its total and counter."""
    _, _, rec, pending = play()
    w = load_world(world())
    beats = peaks.action_beats(w)
    rolls = [r for r in rec.rows if r["what"] == "roll"]
    assert pending is not None and len(rolls) == len(beats)
    assert [r["beat"] for r in rolls] == [b["id"] for b in beats]
    for r in rolls:
        sheet = peaks.engine_view(peaks.raw_sheets_for(w)[r["seat"]])
        replay_roll(SEED, r["roll"], sheet=sheet)  # raises on any mismatch
        assert r["total"] == r["roll"]["result"]
        assert r["verdict"] == peaks.bucket(r["total"])


def test_each_roll_row_carries_the_last_roll_and_the_path_so_far():
    _, sink, rec, _ = play()
    rolls = [r for r in rec.rows if r["what"] == "roll"]
    for i, r in enumerate(rolls):
        assert r["path"] == "-".join(x["verdict"] for x in rolls[: i + 1])
        assert {"seed_id", "counter", "result", "engine_hash"} <= set(r["roll"])
    assert sink.path == [r["verdict"] for r in rolls]


def test_the_seed_is_never_written_only_its_id():
    _, _, rec, _ = play()
    assert SEED not in json.dumps(rec.rows)
    opened = rec.rows[0]
    assert opened["what"] == "open" and opened["seed_id"] == rec.rows[1]["roll"]["seed_id"]


def test_the_open_row_names_the_forecast_it_plays_for():
    _, _, rec, _ = play(forecast="ab" * 32)
    assert rec.rows[0]["forecast"] == "ab" * 32
    assert all("forecast" not in r for r in rec.rows[1:])


def test_verdict_row_carries_no_person(tmp_path):
    """A world whose character is named like a player: rows hold the seat and
    the character id, never a name (forge-convergence §638)."""
    with open(world()) as fh:
        w = copy.deepcopy(json.load(fh))
    for i, c in enumerate(w["characters"]):
        c["name"] = f"Sean Campbell {i}"
    p = tmp_path / "named.json"
    p.write_text(json.dumps(w))
    _, _, rec, _ = play(path=str(p))
    text = json.dumps(rec.rows)
    assert "Sean" not in text and "character_name" not in text
    rolls = [r for r in rec.rows if r["what"] == "roll"]
    assert all(isinstance(r["seat"], int) and r["character"] for r in rolls)


def test_a_verdict_row_never_carries_a_seal_field():
    _, _, rec, _ = play()
    for r in rec.rows:
        assert not {"proof", "pair", "subject", "via", "verifier", "wager", "outcome"} & set(r)


def test_a_refused_row_stops_the_sink():
    rec = FakeRecord(refuse_at=2)
    s = StorySession(world())
    sink = osk.OneScriptSink(rec.write)
    with pytest.raises(osk.SinkRefused):
        osk.play_to_decision(s, osk.suggested_policy(), sink, seed=SEED, session_id="s1")
    assert len(rec.rows) == 2


# -- decision beats -----------------------------------------------------------
def test_a_decision_beat_is_proposed_never_sealed_here():
    s, sink, rec, pending = play()
    got = []

    def propose(p, cites):
        got.append((p, cites))
        return {"subject": "proposal:" + "cd" * 32, "code": 0}

    sub = sink.decision(pending, propose)
    assert sub == "proposal:" + "cd" * 32
    last = rec.rows[-1]
    assert last["what"] == "decision" and last["fact_id"] == pending["fact_id"]
    assert last["path"] == "-".join(sink.path)
    assert got == [({**pending, "world": "hasbeen-late-shift"}, [last["hash"]])]
    assert s.pending_seal() == pending  # proposing does not advance the story


def sealed_answer(pending, world_id="hasbeen-late-shift", **over):
    """What one-script's beat_seal says for a proof over THIS beat."""
    return {"state": "sealed", "by": "human",
            "path": f"world/{world_id}/{pending['fact_id']}.md",
            "data": pending["fact"], "fact_id": pending["fact_id"], **over}


@pytest.mark.parametrize("answer", [
    {"state": "unsealed", "why": "a seal row over this subject is on record, but no proof"},
    {"state": "unreachable", "why": "no Nestor store"},
    {"by": "Sean"},          # a name handed in alone
    "Sean",
    None,
])
def test_hand_written_seal_never_advances_story(answer):
    """A seal by a name instead of a proof is refused: pending_seal() stays set."""
    s, sink, _, pending = play(check=lambda sub: answer)
    with pytest.raises(osk.BeatNotSealed):
        sink.apply_beat_seal(s, pending, SUB)
    assert s.pending_seal() == pending


def test_a_sink_with_no_checker_seals_nothing():
    s, sink, _, pending = play()
    with pytest.raises(osk.BeatNotSealed, match="no seal checker"):
        sink.apply_beat_seal(s, pending, SUB)
    assert s.pending_seal() == pending


def test_a_verified_seal_advances_the_story_with_the_verifier_named():
    asked = []
    s, sink, _, pending = play(check=lambda sub: asked.append(sub) or sealed_answer(pending))
    sink.apply_beat_seal(s, pending, SUB)
    assert asked == [SUB]
    assert s.pending_seal() is None
    assert f"{pending['fact_id']} SEALED by human" in s.result().summary


@pytest.mark.parametrize("over", [
    {"path": "world/aetheris-the-waking-tide/s1::b3.md"},  # another world's s1::b3
    {"path": "world/hasbeen-late-shift/s2::b5.md"},        # another beat
    {"path": "world/s1::b3.md"},                           # no world named
    {"data": "The bridge is out."},                        # another fact
])
def test_B2_a_seal_over_another_beat_or_world_moves_nothing(over):
    s, sink, _, pending = play(check=lambda sub: sealed_answer(pending, **over))
    with pytest.raises(osk.BeatNotSealed, match="not this beat"):
        sink.apply_beat_seal(s, pending, SUB)
    assert s.pending_seal() == pending


def test_a_machine_name_on_a_verified_seal_is_still_refused_by_the_story():
    """The story's name check stays as a second gate behind the proof."""
    s, sink, _, pending = play(check=lambda sub: sealed_answer(pending, by="claude"))
    with pytest.raises(ValueError):
        sink.apply_beat_seal(s, pending, SUB)
    assert s.pending_seal() == pending


def test_S2_the_open_row_names_the_world_and_its_sheets():
    _, _, rec, _ = play()
    key = peaks.world_key(load_world(world()))
    opened = rec.rows[0]
    assert (opened["world"], opened["sheets_sha"]) == (key["world"], key["sheets_sha"])
    assert key["world"] == "hasbeen-late-shift" and len(key["sheets_sha"]) == 64


def test_S2_the_sheets_hash_moves_with_a_stat(tmp_path):
    w = load_world(world())
    with open(world()) as fh:
        raw = json.load(fh)
    raw["characters"][0]["stats"] = {k: v + 1 for k, v in raw["characters"][0]["stats"].items()}
    p = tmp_path / "w.json"
    p.write_text(json.dumps(raw))
    assert peaks.world_key(load_world(str(p)))["sheets_sha"] != peaks.world_key(w)["sheets_sha"]


# -- gm.run_session, unchanged, and the Tee ------------------------------------
def test_result_row_after_terminal_through_run_session():
    rec = FakeRecord()
    game = registry.make("scene")
    res = run_session(game, random_policy(__import__("random").Random(3)), seed=7,
                      sink=osk.OneScriptSink(rec.write, game_name="scene"))
    results = [r for r in rec.rows if r["what"] == "result"]
    assert len(results) == 1 and results[0]["reason"] == res.summary
    assert results[0]["scores"] == res.scores and rec.rows[0]["what"] == "open"


def test_ledger_and_record_both_written_through_a_tee():
    box = tempfile.mkdtemp(prefix="the-table-tee-")
    try:
        ledger, rec = LedgerSink(box_dir=box), FakeRecord()
        game = registry.make("scene")
        run_session(game, random_policy(__import__("random").Random(3)), seed=7,
                    sink=osk.Tee(ledger, osk.OneScriptSink(rec.write, game_name="scene")))
        assert ledger.verify() is True, ledger._last_verify_output
        n = ledger._con.execute("SELECT COUNT(*) FROM ledger").fetchone()[0]
        assert n == len(rec.rows)
        ledger.close()
    finally:
        shutil.rmtree(box, ignore_errors=True)


@pytest.mark.parametrize("edit", ["suggests", "beat_id", "stats", "add_beat"])
def test_round3_N2_world_key_moves_with_every_input_the_odds_read(edit):
    """probe_r2b: a world edited after the forecast (a beat's suggested stat,
    its id, the world's stats, another action beat) is another key."""
    w = load_world(world())
    w2 = copy.deepcopy(w)
    beat = next(b for b in w2["scenes"][0]["beats"] if b["kind"] == "action")
    if edit == "suggests":
        beat["suggests"] = next(s for s in w2["stats"] if s != beat["suggests"])
    elif edit == "beat_id":
        beat["id"] = beat["id"] + "x"
    elif edit == "stats":
        w2["stats"] = list(reversed(w2["stats"]))
    else:
        w2["scenes"][0]["beats"].insert(0, copy.deepcopy(beat) | {"id": "b0"})
    assert peaks.world_key(w2) != peaks.world_key(w)
    assert peaks.world_key(copy.deepcopy(w)) == peaks.world_key(w)  # and stable


# -- W4 break 1: a forecast's session is seeded by its beacon round ------------
def test_a_beacon_session_names_its_round_and_randomness_on_the_open_row():
    rec = FakeRecord()
    sink = osk.OneScriptSink(rec.write, forecast="ab" * 32, beacon_round=6558999)
    osk.play_to_decision(StorySession(world()), osk.suggested_policy(), sink,
                         seed=SEED, session_id="s1")
    opened, rolls = rec.rows[0], [r for r in rec.rows if r["what"] == "roll"]
    assert (opened["beacon_round"], opened["randomness"]) == (6558999, SEED)
    assert opened["seed_id"] == hashlib.sha256(bytes.fromhex(SEED)).hexdigest()[:16]
    assert all(r["roll"]["seed_id"] == opened["seed_id"] for r in rolls)
    assert all(SEED not in json.dumps(r) for r in rec.rows[1:])  # the open row only
    assert rolls[0]["roll"]["counter_before"] == 0


def test_a_beacon_session_on_a_seed_that_is_not_randomness_is_refused():
    rec = FakeRecord()
    sink = osk.OneScriptSink(rec.write, beacon_round=6558999)
    with pytest.raises(osk.SinkRefused, match="round's randomness"):
        osk.play_to_decision(StorySession(world()), osk.suggested_policy(), sink,
                             seed=7, session_id="s1")
    assert rec.rows == []
