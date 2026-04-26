"""Tests for squirrel_app.py — HTTP routes and Stories API."""
import threading
import http.client
import time
import json as _json
import pytest

TEST_PORT = 8426


@pytest.fixture(scope="module")
def server():
    import squirrel_app
    from responder.state import AppState
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        md = Path(tmpdir) / "Squirrel.md"
        md.write_text("# Test\n\n---\n")
        squirrel_app.SQUIRREL_MD = md
        squirrel_app._app_state = AppState(squirrel_md=md)
        squirrel_app._app_state.load_config()
        from http.server import HTTPServer
        srv = HTTPServer(("127.0.0.1", TEST_PORT), squirrel_app.SquirrelHandler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        time.sleep(0.1)
        yield srv
        srv.shutdown()


def _get(path, port=TEST_PORT):
    conn = http.client.HTTPConnection("127.0.0.1", port)
    conn.request("GET", path)
    r = conn.getresponse()
    body = r.read().decode()
    conn.close()
    return r.status, body


def _post(path, payload, port=TEST_PORT):
    conn = http.client.HTTPConnection("127.0.0.1", port)
    data = _json.dumps(payload).encode()
    conn.request("POST", path, data, {"Content-Type": "application/json"})
    r = conn.getresponse()
    body = r.read().decode()
    conn.close()
    return r.status, body


def test_home_has_nav(server):
    status, body = _get("/")
    assert status == 200
    assert 'id="nav"' in body


def test_people_route(server):
    status, body = _get("/people")
    assert status == 200
    assert 'id="nav"' in body


def test_tree_route(server):
    status, body = _get("/tree")
    assert status == 200
    assert "tree-search" in body


def test_stash_route(server):
    status, body = _get("/stash")
    assert status == 200
    assert 'id="nav"' in body


def test_sources_route(server):
    status, body = _get("/sources")
    assert status == 200
    assert "sources-search" in body


def test_stories_route(server):
    status, body = _get("/stories")
    assert status == 200
    assert "stories-chat" in body


def test_unknown_route(server):
    status, _ = _get("/doesnotexist")
    assert status == 404


def test_nav_has_all_links(server):
    _, body = _get("/")
    for href in ["/", "/people", "/tree", "/stash", "/sources", "/stories"]:
        assert f'href="{href}"' in body


def test_mtime_route(server):
    status, body = _get("/mtime")
    assert status == 200
    assert "mtime" in _json.loads(body)


def test_stories_chat_creates_session(server):
    status, body = _post("/api/stories/chat", {"message": "Hello"})
    assert status == 200
    d = _json.loads(body)
    assert "session_id" in d
    assert "reply" in d


def test_stories_chat_continues_session(server):
    _, body1 = _post("/api/stories/chat", {"message": "Hello Jeles"})
    sid = _json.loads(body1)["session_id"]
    status2, body2 = _post("/api/stories/chat", {"session_id": sid, "message": "Tell me more"})
    assert status2 == 200
    assert _json.loads(body2)["session_id"] == sid


def test_stories_save_empty(server):
    status, body = _post("/api/stories/save", {"session_id": "nonexistent", "subject": "Oscar"})
    assert status == 200
    assert _json.loads(body)["saved"] == 0


def test_person_invalid_id(server):
    status, _ = _get("/person/notanumber")
    assert status == 404
