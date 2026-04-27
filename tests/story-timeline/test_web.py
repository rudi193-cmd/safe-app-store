import json
import os
import sys
import threading
import time
import urllib.request
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apps/story-timeline"))


@pytest.fixture()
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(tmp_path / "timeline.db"))
    import timeline_db
    import importlib
    importlib.reload(timeline_db)
    timeline_db.add_node(type_="character", fields={"name": "Alice"})
    timeline_db.add_node(type_="location", fields={"name": "Forest"})

    import web
    importlib.reload(web)
    srv = web.TimelineHTTPServer(port=19876)
    t = threading.Thread(target=srv.start, daemon=True)
    t.start()
    for _ in range(20):
        try:
            urllib.request.urlopen("http://localhost:19876/")
            break
        except OSError:
            time.sleep(0.05)
    yield srv
    srv.stop()


def test_root_serves_html(server):
    resp = urllib.request.urlopen("http://localhost:19876/")
    assert resp.status == 200
    content = resp.read().decode()
    assert "<canvas" in content


def test_api_nodes_returns_json_list(server):
    resp = urllib.request.urlopen("http://localhost:19876/api/nodes")
    assert resp.status == 200
    data = json.loads(resp.read())
    assert isinstance(data, list)
    assert len(data) == 2
    types = {n["type"] for n in data}
    assert types == {"character", "location"}
    # fields should be a dict (not a raw JSON string)
    assert isinstance(data[0]["fields"], dict)


def test_api_edges_returns_json_list(server):
    resp = urllib.request.urlopen("http://localhost:19876/api/edges")
    assert resp.status == 200
    data = json.loads(resp.read())
    assert isinstance(data, list)


def test_api_node_by_id(server):
    import timeline_db
    nodes = timeline_db.get_nodes()
    node_id = nodes[0]["id"]
    resp = urllib.request.urlopen(f"http://localhost:19876/api/node/{node_id}")
    assert resp.status == 200
    data = json.loads(resp.read())
    assert data["id"] == node_id
    assert isinstance(data["fields"], dict)


def test_unknown_path_returns_404(server):
    try:
        urllib.request.urlopen("http://localhost:19876/nonexistent")
        assert False, "Should have raised"
    except urllib.error.HTTPError as e:
        assert e.code == 404
