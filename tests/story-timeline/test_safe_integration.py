import json
import os
import sys
import pytest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apps/story-timeline"))


class _MockIdentityClient:
    def __init__(self):
        self._composites = []

    def get_user_uuid(self):
        return None

    def write_session_composite(self, stats, uuid, app_id, collection):
        self._composites.append({"stats": stats, "uuid": uuid})
        return True


@pytest.fixture()
def ident():
    from safe_integration import identity as _ident
    import importlib
    importlib.reload(_ident)
    return _ident


def test_get_user_uuid_returns_uuid_when_file_exists(ident, tmp_path, monkeypatch):
    identity_file = tmp_path / "user_identity.json"
    identity_file.write_text(json.dumps({"uuid": "abc-123"}))
    monkeypatch.setattr(ident, "_identity_path", identity_file)
    assert ident.get_user_uuid() == "abc-123"


def test_get_user_uuid_returns_none_when_missing(ident, tmp_path, monkeypatch):
    monkeypatch.setattr(ident, "_identity_path", tmp_path / "nonexistent.json")
    assert ident.get_user_uuid() is None


def test_get_user_uuid_returns_none_on_malformed_json(ident, tmp_path, monkeypatch):
    bad_file = tmp_path / "user_identity.json"
    bad_file.write_text("not json")
    monkeypatch.setattr(ident, "_identity_path", bad_file)
    assert ident.get_user_uuid() is None


def test_write_session_composite_succeeds(ident):
    mock = _MockIdentityClient()
    ident._client = mock
    stats = {
        "nodes_created": 3,
        "edges_created": 2,
        "types_used": ["character", "event"],
        "session_duration_s": 120,
    }
    result = ident.write_session_composite(stats=stats, uuid="test-uuid-0001")
    assert result is True


def test_write_session_composite_noop_without_client(ident):
    ident._client = None
    result = ident.write_session_composite(stats={}, uuid="test-uuid")
    assert result is False
