import json
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apps/story-timeline"))

TEST_UUID = "test-user-0000"

@pytest.fixture()
def edges(tmp_path, monkeypatch):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path / "willow"))
    monkeypatch.setenv("WILLOW_CORE", "/home/sean-campbell/github/willow-1.9/core")
    import willow_edges
    import importlib
    importlib.reload(willow_edges)
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

def test_graceful_degradation_when_willow_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("WILLOW_CORE", str(tmp_path / "nonexistent"))
    import willow_edges
    import importlib
    importlib.reload(willow_edges)
    result = willow_edges.add_edge("a", "b", "rel", uuid=TEST_UUID)
    assert result is None
    assert willow_edges.edges_for("a", uuid=TEST_UUID) == []
