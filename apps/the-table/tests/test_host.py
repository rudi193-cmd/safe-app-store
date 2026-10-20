"""the-table -- test_host.py (flatten F2, F-7: a script finds the one-script beside it).

``host.reach`` says reachable or unreachable, never collapsed; a script with no
one-script beside says why and exits 2, never falling back to a chain of its
own. A ``Box`` writes ``verdict`` rows as the box's ``table`` identity, its
keys beside the box, never inside, and no human key ever; a decision beat is a
proposal code never seals; an edited copy of the record does not verify.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import sys

import pytest

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _APP_ROOT)

from the_table import host, proof  # noqa: E402
from the_table.onescript_sink import SinkRefused  # noqa: E402

needs_onescript = pytest.mark.skipif(
    host.reach()["state"] != "reachable",
    reason=f"the one-script is not beside the-table: {host.reach().get('why')}",
)


@pytest.fixture
def box():
    with host.Box() as b:
        yield b


# -- where, and the two states ---------------------------------------------


def test_it_looks_beside_safe_app_store_by_default(monkeypatch):
    monkeypatch.delenv("ONESCRIPT_HOME", raising=False)
    monkeypatch.delenv("ONESCRIPT_GROVE", raising=False)
    repos = os.path.dirname(os.path.dirname(os.path.dirname(_APP_ROOT)))
    w = host.where()
    assert str(w["onescript"]) == os.path.join(repos, "willow-bot", "one-script")
    assert str(w["grove"]) == os.path.join(repos, "willows-grove")


def test_the_env_names_where_instead(monkeypatch, tmp_path):
    monkeypatch.setenv("ONESCRIPT_HOME", str(tmp_path / "os"))
    monkeypatch.setenv("ONESCRIPT_GROVE", str(tmp_path / "g"))
    assert host.where() == {"onescript": tmp_path / "os", "grove": tmp_path / "g"}


def test_no_one_script_is_unreachable_and_says_where(monkeypatch, tmp_path):
    monkeypatch.setenv("ONESCRIPT_HOME", str(tmp_path / "nowhere"))
    got = host.reach()
    assert got["state"] == "unreachable" and "nowhere" in got["why"]
    with pytest.raises(host.Unreachable):
        host.onescript()


@needs_onescript
def test_no_law_is_unreachable_too(monkeypatch, tmp_path):
    monkeypatch.setenv("ONESCRIPT_GROVE", str(tmp_path / "no-grove"))
    got = host.reach()
    assert got["state"] == "unreachable" and "constitution" in got["why"]


def test_a_script_with_no_one_script_exits_2_and_says_why(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("ONESCRIPT_HOME", str(tmp_path / "nowhere"))
    with pytest.raises(SystemExit) as e:
        host.box_or_exit()
    assert e.value.code == host.UNREACHABLE == 2
    assert "unreachable" in capsys.readouterr().err


def test_the_proof_with_no_one_script_exits_2_not_0(monkeypatch, tmp_path, capsys):
    """Forbidden act: passing a proof that wrote nowhere."""
    monkeypatch.setenv("ONESCRIPT_HOME", str(tmp_path / "nowhere"))
    with pytest.raises(SystemExit) as e:
        proof.main()
    assert e.value.code == 2
    assert "PROOF PASSED" not in capsys.readouterr().out


# -- the box ---------------------------------------------------------------


@needs_onescript
def test_the_keys_sit_beside_the_box_0600_and_hold_no_human_key(box):
    keys = box.cfg.keys
    assert not keys.resolve().is_relative_to(box.cfg.box.resolve())
    assert stat.S_IMODE(keys.stat().st_mode) == 0o600
    assert stat.S_IMODE(keys.parent.stat().st_mode) == 0o700
    held = json.loads(keys.read_text())
    assert set(held) == {"desk", "table"}  # never a human key
    assert all(len(bytes.fromhex(v)) == 32 for v in held.values())


@needs_onescript
def test_two_boxes_never_share_keys():
    with host.Box() as a, host.Box() as b:
        assert a.cfg.keys.read_text() != b.cfg.keys.read_text()


@needs_onescript
def test_a_row_is_a_verdict_written_as_table_and_the_chain_holds(box):
    got = box.write({"what": "open", "session": "s1", "verdict": "open", "reason": "opened"})
    assert got["code"] == 0
    row = got["row"]
    assert row["kind"] == "verdict" and row["who"] == "table"
    assert box.rows()[-1] == row and box.head() == row["hash"]
    assert box.verify() == []


@needs_onescript
def test_a_refused_row_says_so(box):
    got = box.write({"what": "open", "session": "s1", "proof": "x"})
    assert got["code"] == 1 and "never a seal" in got["refused"]


@needs_onescript
def test_an_edited_copy_does_not_verify_and_the_original_still_does(box):
    st = host.StateSink(box, "test")
    st.open_session("s1", {})
    st.snapshot({"kind": "check", "total": 12}, note="a check")
    st.close_session({"summary": "done"})

    def edit(rows):
        i = next(i for i, r in enumerate(rows) if r.get("what") == "step")
        rows[i] = {**rows[i], "state": {**rows[i]["state"], "total": 20}}
        return rows

    before = box.record_path.read_bytes()
    copy = box.tampered_copy(edit)
    try:
        assert copy.resolve() != box.cfg.box.resolve()
        assert box.verify(copy) and "chain broken" in box.verify(copy)[0]
        assert box.record_path.read_bytes() == before
        assert box.verify() == []
    finally:
        shutil.rmtree(os.path.dirname(copy), ignore_errors=True)


@needs_onescript
def test_a_kept_box_keeps_its_keys_and_carries_its_chain_on(tmp_path):
    a = host.Box(tmp_path / "campaign")
    keys = a.cfg.keys.read_text()
    a.write({"what": "open", "session": "c", "verdict": "open", "reason": "opened"})
    n = len(a.rows())
    a.close()
    assert (tmp_path / "campaign" / "box" / "record.jsonl").exists()  # a kept box is not removed

    b = host.Box(tmp_path / "campaign")
    assert b.cfg.keys.read_text() == keys
    st = host.StateSink(b, "test")
    st.resume("c")
    st.snapshot({"kind": "roll", "total": 3}, note="later")
    assert len(b.rows()) > n and b.verify() == []


@needs_onescript
def test_a_throwaway_box_is_removed_on_close():
    b = host.Box()
    d = b.dir
    b.close()
    assert not d.exists()


# -- the state sink ----------------------------------------------------------


@needs_onescript
def test_the_state_sink_needs_an_open_session(box):
    n = len(box.rows())
    with pytest.raises(RuntimeError, match="open_session first") as e:
        host.StateSink(box, "test").snapshot({"x": 1})
    assert type(e.value) is RuntimeError  # stopped here, not by a refusal on record
    assert len(box.rows()) == n


@needs_onescript
def test_the_state_sink_carries_the_state_as_given(box):
    st = host.StateSink(box, "aetheris5e")
    st.open_session("tide", {"pc": "Sena"})
    st.snapshot({"kind": "check", "nat": 14, "total": 19}, note="b1 -> weak")
    st.close_session({"outcome": "party"})
    assert [r["what"] for r in st.rows] == ["open", "step", "result"]
    assert st.rows[1]["state"] == {"kind": "check", "nat": 14, "total": 19}
    assert st.rows[1]["reason"] == "b1 -> weak" and st.rows[2]["reason"] == "party"
    assert all(r["game"] == "aetheris5e" and r["session"] == "tide" for r in st.rows)


@needs_onescript
def test_the_state_sink_stops_at_a_refusal(box):
    st = host.StateSink(box, "test")
    with pytest.raises(SinkRefused):
        st.open_session("ab" * 32, {})  # a hash-shaped session id is refused


@needs_onescript
def test_a_decision_is_a_proposal_code_never_seals(box):
    st = host.StateSink(box, "aetheris5e")
    st.open_session("tide", {})
    subject = st.decision({"fact_id": "s2::b5", "fact": "Maunder is a person.",
                           "world": "aetheris"})
    assert subject.startswith("proposal:")
    assert st.rows[-1]["what"] == "decision"
    assert box.beat_seal(subject)["state"] == "unsealed"
    assert not [r for r in box.rows() if r["kind"] == "seal"]


@needs_onescript
def test_a_decision_with_no_world_is_not_proposed(box):
    st = host.StateSink(box, "test")
    st.open_session("s", {})
    with pytest.raises(SinkRefused):
        st.decision({"fact_id": "s1::b1", "fact": "x"})


# -- the proof, on the record --------------------------------------------------


@needs_onescript
def test_the_proof_passes_on_the_record(capsys):
    assert proof.main() == 0
    out = capsys.readouterr().out
    assert "chain:        HOLDS" in out and "tampered:     REFUSED" in out
    assert "PROOF PASSED" in out


@needs_onescript
def test_the_proof_fails_when_the_chain_does_not_hold(monkeypatch, capsys):
    """Forbidden act: a proof that passes over a broken chain."""
    monkeypatch.setattr(host.Box, "verify", lambda self, box=None: ["row 1: chain broken"])
    assert proof.main() == 1
    assert "PROOF PASSED" not in capsys.readouterr().out


@needs_onescript
def test_the_proof_fails_when_an_edited_copy_verifies(monkeypatch, capsys):
    """Forbidden act: a proof that cannot tell an edited record."""
    real = host.Box.verify
    monkeypatch.setattr(host.Box, "verify",
                        lambda self, box=None: [] if box is not None else real(self))
    assert proof.main() == 1
    assert "tampered:     NOT REFUSED" in capsys.readouterr().out


def test_the_tables_randomness_with_no_one_script_says_so_and_stops(tmp_path):
    """F-16: the games import the one script's randomness; with none beside,
    importing it fails, saying where it looked, never falling back."""
    import subprocess

    got = subprocess.run(
        [sys.executable, "-c", "import the_table.stream"], cwd=_APP_ROOT,
        env={**os.environ, "ONESCRIPT_HOME": str(tmp_path / "nowhere")},
        capture_output=True, text=True)
    assert got.returncode != 0
    assert "Unreachable" in got.stderr and "nowhere" in got.stderr


@needs_onescript
def test_the_tables_stream_is_the_one_scripts():
    from the_table import stream

    one = host.onescript_module("stream")
    assert stream.StreamRandom is one.StreamRandom and stream.replay is one.replay
