import os
import sys
import pytest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apps/story-timeline"))

TEST_UUID = "test-user-0000"


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
def edges(monkeypatch):
    import willow_edges
    import importlib
    importlib.reload(willow_edges)
    mock = _MockSoilClient()
    willow_edges._CLIENT = mock
    willow_edges._CLIENT_INIT_FAILED = False
    return willow_edges


def test_add_and_list_edge(edges):
    edges.add_edge("node-A", "node-B", "related_to", uuid=TEST_UUID)
    result = edges.edges_for("node-A", uuid=TEST_UUID)
    assert len(result) == 1
    assert result[0]["relation"] == "related_to"


def test_edges_for_returns_both_directions(edges):
    edges.add_edge("node-X", "node-Y", "causes", uuid=TEST_UUID)
    from_x = edges.edges_for("node-X", uuid=TEST_UUID)
    from_y = edges.edges_for("node-Y", uuid=TEST_UUID)
    assert len(from_x) == 1
    assert len(from_y) == 1
    assert from_x[0]["from_id"] == "node-X"


def test_delete_edge(edges):
    edge_id = edges.add_edge("A", "B", "knows", uuid=TEST_UUID)
    assert edges.delete_edge(edge_id, uuid=TEST_UUID) is True
    assert edges.edges_for("A", uuid=TEST_UUID) == []


def test_reconcile_orphans_removes_stale(edges):
    edges.add_edge("real-node", "ghost-node", "links_to", uuid=TEST_UUID)
    removed = edges.reconcile_orphans(["real-node"], uuid=TEST_UUID)
    assert removed == 1
    assert edges.edges_for("real-node", uuid=TEST_UUID) == []


def test_reconcile_orphans_keeps_valid(edges):
    edges.add_edge("node-1", "node-2", "mentions", uuid=TEST_UUID)
    removed = edges.reconcile_orphans(["node-1", "node-2"], uuid=TEST_UUID)
    assert removed == 0
    assert len(edges.edges_for("node-1", uuid=TEST_UUID)) == 1


def test_graceful_degradation_when_willow_unavailable(monkeypatch):
    import willow_edges
    import importlib
    importlib.reload(willow_edges)
    willow_edges._CLIENT = None
    willow_edges._CLIENT_INIT_FAILED = True
    result = willow_edges.add_edge("a", "b", "rel", uuid=TEST_UUID)
    assert result is None
    assert willow_edges.edges_for("a", uuid=TEST_UUID) == []
