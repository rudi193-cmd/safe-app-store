import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def modules(tmp_path, monkeypatch):
    monkeypatch.setenv("OAKENSCROLL_DB", str(tmp_path / "office.db"))
    monkeypatch.setenv("WILLOW_HOME", str(tmp_path / "willow"))
    import office_db, willow_bridge
    return office_db, willow_bridge


def test_dew_is_off_by_default(modules, monkeypatch):
    db, bridge = modules
    monkeypatch.delenv("OAKENSCROLL_PROACTIVE", raising=False)
    db.state_claim("due thing", 0.7, due=int(time.time()) - 10)
    assert bridge.surface_due() is False
    assert not bridge.signal_path().exists()


def test_dew_publishes_facts_when_enabled(modules, monkeypatch):
    db, bridge = modules
    monkeypatch.setenv("OAKENSCROLL_PROACTIVE", "1")
    pid = db.state_claim("due thing", 0.7, due=int(time.time()) - 10)
    assert bridge.surface_due() is True
    payload = json.loads(bridge.signal_path().read_text())
    assert payload["due"][0]["id"] == pid
    assert set(payload["due"][0]) == {"id", "claim", "confidence", "due"}


def test_promote_builds_atom_and_injects(modules):
    db, bridge = modules
    pid = db.state_claim("the world is round", 0.99)
    with pytest.raises(ValueError):
        bridge.promote_resolved(pid)  # not resolved yet
    db.resolve(pid, True)
    sent = []
    atom = bridge.promote_resolved(pid, ingest=sent.append)
    assert sent == [atom]
    assert atom["domain"] == "calibration" and "TRUE" in atom["content"]
