import json
import os
import sys
import pytest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apps/story-timeline"))


@pytest.fixture()
def si(monkeypatch, tmp_path):
    monkeypatch.setenv("WILLOW_CORE", str(
        Path(__file__).parents[5] / "willow-1.9" / "core"
    ))
    import safe_integration
    import importlib
    importlib.reload(safe_integration)
    return safe_integration


def test_get_user_uuid_returns_uuid_when_file_exists(si, tmp_path, monkeypatch):
    identity_file = tmp_path / "user_identity.json"
    identity_file.write_text(json.dumps({"uuid": "abc-123"}))
    monkeypatch.setattr(si, "_IDENTITY_PATH", identity_file)
    assert si.get_user_uuid() == "abc-123"


def test_get_user_uuid_returns_none_when_missing(si, tmp_path, monkeypatch):
    monkeypatch.setattr(si, "_IDENTITY_PATH", tmp_path / "nonexistent.json")
    assert si.get_user_uuid() is None


def test_get_user_uuid_returns_none_on_malformed_json(si, tmp_path, monkeypatch):
    bad_file = tmp_path / "user_identity.json"
    bad_file.write_text("not json")
    monkeypatch.setattr(si, "_IDENTITY_PATH", bad_file)
    assert si.get_user_uuid() is None


def test_write_session_composite_succeeds(si, tmp_path, monkeypatch):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path / "willow"))
    import importlib
    importlib.reload(si)
    stats = {
        "nodes_created": 3,
        "edges_created": 2,
        "types_used": ["character", "event"],
        "session_duration_s": 120,
    }
    result = si.write_session_composite(stats=stats, uuid="test-uuid-0001")
    assert result is True


def test_write_session_composite_noop_without_willow(tmp_path, monkeypatch):
    monkeypatch.setenv("WILLOW_CORE", str(tmp_path / "nonexistent"))
    import safe_integration
    import importlib
    importlib.reload(safe_integration)
    result = safe_integration.write_session_composite(stats={}, uuid="test-uuid")
    assert result is False
