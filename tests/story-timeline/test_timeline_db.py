import json
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apps/story-timeline"))

@pytest.fixture(autouse=True)
def reset_module(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(tmp_path / "timeline.db"))
    if "timeline_db" in sys.modules:
        del sys.modules["timeline_db"]

@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(tmp_path / "timeline.db"))
    import importlib
    import timeline_db
    importlib.reload(timeline_db)
    return timeline_db

def test_add_and_get_node(db):
    node_id = db.add_node(type_="character", fields={"name": "Alice", "age": "30"})
    node = db.get_node(node_id)
    assert node["type"] == "character"
    assert node["fields"]["name"] == "Alice"

def test_get_nodes_by_type(db):
    db.add_node(type_="character", fields={"name": "Alice"})
    db.add_node(type_="location", fields={"name": "Castle"})
    chars = db.get_nodes(type_="character")
    assert len(chars) == 1
    assert chars[0]["fields"]["name"] == "Alice"

def test_get_all_nodes(db):
    db.add_node(type_="character", fields={"name": "Alice"})
    db.add_node(type_="event", fields={"summary": "Battle"})
    all_nodes = db.get_nodes()
    assert len(all_nodes) == 2

def test_update_node(db):
    node_id = db.add_node(type_="character", fields={"name": "Alice"})
    db.update_node(node_id, fields={"name": "Alice Liddell", "age": "10"})
    node = db.get_node(node_id)
    assert node["fields"]["name"] == "Alice Liddell"

def test_delete_node(db):
    node_id = db.add_node(type_="character", fields={"name": "Temp"})
    assert db.delete_node(node_id) is True
    assert db.get_node(node_id) is None

def test_search_nodes(db):
    db.add_node(type_="character", fields={"name": "Gandalf", "role": "wizard"})
    db.add_node(type_="character", fields={"name": "Frodo", "role": "hobbit"})
    results = db.search_nodes("wizard")
    assert len(results) == 1
    assert results[0]["fields"]["name"] == "Gandalf"

def test_get_types(db):
    db.add_node(type_="character", fields={})
    db.add_node(type_="location", fields={})
    db.add_node(type_="character", fields={})
    types = db.get_types()
    assert set(types) == {"character", "location"}

def test_node_id_is_uuid_format(db):
    import re
    node_id = db.add_node(type_="event", fields={"summary": "Test"})
    assert re.match(r"[0-9a-f-]{36}", node_id)

def test_get_all_node_ids(db):
    db.add_node(type_="character", fields={"name": "Alice"})
    db.add_node(type_="location", fields={"name": "Forest"})
    ids = db.get_all_node_ids()
    assert len(ids) == 2
    assert all(isinstance(i, str) for i in ids)
