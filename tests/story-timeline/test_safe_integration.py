import json
import os
import sys
import pytest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apps/story-timeline"))


class _MockSoilClient:
    """In-memory SoilClient for tests — no MCP server required."""
    _available = True

    def __init__(self):
        self._store: dict[str, dict] = {}

    def put(self, collection, record, record_id=None):
        key = record_id or record.get("id")
        self._store[key] = dict(record)
        return key

    def list(self, collection):
        return list(self._store.values())

    def delete(self, collection, record_id):
        if record_id in self._store:
            del self._store[record_id]
            return True
        return False


@pytest.fixture()
def si():
    import safe_integration
    import importlib
    importlib.reload(safe_integration)
    mock = _MockSoilClient()
    safe_integration._CLIENT = mock
    safe_integration._CLIENT_INIT_FAILED = False
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


def test_write_session_composite_succeeds(si):
    stats = {
        "nodes_created": 3,
        "edges_created": 2,
        "types_used": ["character", "event"],
        "session_duration_s": 120,
    }
    result = si.write_session_composite(stats=stats, uuid="test-uuid-0001")
    assert result is True


def test_write_session_composite_noop_without_willow(monkeypatch):
    import safe_integration
    import importlib
    importlib.reload(safe_integration)
    safe_integration._CLIENT = None
    safe_integration._CLIENT_INIT_FAILED = True
    result = safe_integration.write_session_composite(stats={}, uuid="test-uuid")
    assert result is False
