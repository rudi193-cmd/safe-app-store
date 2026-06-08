import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apps/story-timeline"))

TEST_UUID = "test-user-0000"


class _MockSoilClient:
    _available = True

    def __init__(self):
        self._store: dict[str, dict] = {}
        self.collections: dict[str, list[dict]] = {}

    def put(self, collection, record, record_id=None):
        key = record_id or record.get("id")
        self._store[key] = dict(record)
        self.collections.setdefault(collection, []).append(dict(record))
        return key

    def list(self, collection):
        return list(self.collections.get(collection, []))

    def delete(self, collection, record_id):
        if record_id in self._store:
            del self._store[record_id]
            return True
        return False


@pytest.fixture(autouse=True)
def reset_db(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(tmp_path / "timeline.db"))
    for name in ("timeline_db", "willow_edges", "story_protocol", "soil_protocol", "promote"):
        sys.modules.pop(name, None)


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(tmp_path / "timeline.db"))
    import importlib
    import timeline_db
    importlib.reload(timeline_db)
    return timeline_db


@pytest.fixture()
def proto(db):
    import importlib
    import story_protocol
    importlib.reload(story_protocol)
    return story_protocol


@pytest.fixture()
def edges(monkeypatch):
    import importlib
    import willow_edges
    importlib.reload(willow_edges)
    mock = _MockSoilClient()
    willow_edges._CLIENT = mock
    willow_edges._CLIENT_INIT_FAILED = False
    return willow_edges


@pytest.fixture()
def soil(monkeypatch):
    import importlib
    import soil_protocol
    importlib.reload(soil_protocol)
    mock = _MockSoilClient()
    soil_protocol._CLIENT = mock
    soil_protocol._CLIENT_INIT_FAILED = False
    return soil_protocol


def test_collection_path(proto):
    path = proto.collection_path("abc-123", proto.COLLECTION_TIMELINES)
    assert path == "user-abc-123/story-timeline/timelines/"


def test_create_writing_project(proto):
    project = proto.create_writing_project("Novel Draft", summary="Epic fantasy")
    assert project["type"] == proto.WRITING_PROJECT
    assert project["fields"]["title"] == "Novel Draft"


def test_create_timeline_requires_project(proto):
    project = proto.create_writing_project("Novel Draft")
    timeline = proto.create_timeline(project["id"], "World chronology")
    assert timeline["type"] == proto.TIMELINE
    assert timeline["fields"]["project_id"] == project["id"]
    assert timeline["fields"]["name"] == "World chronology"


def test_create_timeline_rejects_missing_project(proto):
    with pytest.raises(ValueError, match="writing project not found"):
        proto.create_timeline("missing-id", "World chronology")


def test_create_commonplace_item(proto):
    item = proto.create_commonplace_item("Opening image", content="Fog on the river")
    assert item["type"] == proto.COMMONPLACE_ITEM
    assert item["fields"]["title"] == "Opening image"


def test_list_timelines_by_project(proto):
    project = proto.create_writing_project("Novel Draft")
    proto.create_timeline(project["id"], "World")
    proto.create_timeline(project["id"], "Draft beats")
    other = proto.create_writing_project("Essay")
    proto.create_timeline(other["id"], "Process")

    timelines = proto.list_timelines(project_id=project["id"])
    names = {t["fields"]["name"] for t in timelines}
    assert names == {"World", "Draft beats"}


def test_find_timeline_by_name(proto):
    project = proto.create_writing_project("Novel Draft")
    created = proto.create_timeline(project["id"], "World chronology")
    found = proto.find_timeline_by_name(project["id"], "world chronology")
    assert found["id"] == created["id"]


def test_promote_note_to_timeline(proto, edges):
    project = proto.create_writing_project("Novel Draft")
    timeline = proto.create_timeline(project["id"], "World")
    note_id = proto.create_commonplace_item("River fog", content="Mist at dawn")["id"]

    result = proto.promote_to_timeline(note_id, timeline["id"], uuid=TEST_UUID, mirror=False)

    entry = result["entry"]
    assert entry["type"] == proto.TIMELINE_ENTRY
    assert entry["fields"]["timeline_id"] == timeline["id"]
    assert result["provenance"]["source_id"] == note_id

    edge_records = edges.edges_for(entry["id"], uuid=TEST_UUID)
    relations = {e["relation"] for e in edge_records}
    assert proto.REL_DERIVED_FROM in relations
    assert proto.REL_APPEARS_ON_TIMELINE in relations


def test_promote_book_preserves_title(proto, edges):
    import timeline_db as db
    book_id = db.add_node(type_="book", fields={"title": "The Left Hand of Darkness", "author": "Le Guin"})
    project = proto.create_writing_project("Novel Draft")
    timeline = proto.create_timeline(project["id"], "Inspirations")

    result = proto.promote_to_timeline(book_id, timeline["id"], uuid=TEST_UUID, mirror=False)
    assert result["entry"]["fields"]["title"] == "The Left Hand of Darkness"


def test_promote_rejects_invalid_source(proto):
    import timeline_db as db
    loc_id = db.add_node(type_="location", fields={"name": "Forest"})
    project = proto.create_writing_project("Novel Draft")
    timeline = proto.create_timeline(project["id"], "World")

    with pytest.raises(ValueError, match="not promotable"):
        proto.promote_to_timeline(loc_id, timeline["id"], uuid=TEST_UUID, mirror=False)


def test_mirror_protocol_record(soil, proto):
    project = proto.create_writing_project("Novel Draft")
    assert soil.mirror_protocol_record(project, uuid=TEST_UUID) is False

    timeline = proto.create_timeline(project["id"], "World")
    assert soil.mirror_protocol_record(timeline, uuid=TEST_UUID) is True
    collection = proto.collection_path(TEST_UUID, proto.COLLECTION_TIMELINES)
    records = soil._CLIENT.list(collection)
    assert any(r["id"] == timeline["id"] for r in records)


def test_multiple_timelines_same_source(proto, edges):
    import timeline_db as db
    note_id = db.add_node(type_="note", fields={"title": "Shared beat", "content": "Reveal"})
    project = proto.create_writing_project("Novel Draft")
    world = proto.create_timeline(project["id"], "World")
    draft = proto.create_timeline(project["id"], "Draft")

    first = proto.promote_to_timeline(note_id, world["id"], uuid=TEST_UUID, mirror=False)
    second = proto.promote_to_timeline(note_id, draft["id"], uuid=TEST_UUID, mirror=False)

    assert first["entry"]["id"] != second["entry"]["id"]
    assert proto.list_timeline_entries(world["id"]) == [first["entry"]]
    assert proto.list_timeline_entries(draft["id"]) == [second["entry"]]


def test_list_timeline_entries_sorted(proto):
    project = proto.create_writing_project("Novel Draft")
    timeline = proto.create_timeline(project["id"], "World")
    e2 = proto.create_timeline_entry(timeline["id"], "Second", order_index=2)
    e0 = proto.create_timeline_entry(timeline["id"], "First", order_index=0)
    e1 = proto.create_timeline_entry(timeline["id"], "Middle", order_index=1)

    ordered = proto.list_timeline_entries(timeline["id"])
    assert [n["id"] for n in ordered] == [e0["id"], e1["id"], e2["id"]]


def test_mirror_provenance(soil, proto):
    ok = soil.mirror_provenance(
        entry_id="entry-1",
        provenance={"source_id": "note-1", "timeline_id": "tl-1"},
        uuid=TEST_UUID,
    )
    assert ok is True
    collection = proto.collection_path(TEST_UUID, proto.COLLECTION_ATOMS).rstrip("/")
    # atoms path has no trailing slash in mirror_provenance
    records = soil._CLIENT.list(f"user-{TEST_UUID}/story-timeline/atoms")
    assert records[0]["type"] == "provenance"
    assert records[0]["entry_id"] == "entry-1"


def test_protocol_record_payload(proto):
    project = proto.create_writing_project("Novel Draft")
    payload = proto.protocol_record_payload(project)
    assert payload["app_id"] == proto.APP_ID
    assert payload["type"] == proto.WRITING_PROJECT
    assert "fields" in payload


def test_library_project_remains_commonplace_record(proto, db):
    project_id = db.add_node(type_="project", fields={"title": "Library project"})
    node = db.get_node(project_id)
    assert node["type"] == "project"
    assert proto.is_writing_project(node) is False
    assert proto.list_writing_projects() == []


def test_writing_setup_status(proto):
    assert proto.writing_setup_status() == {
        "ready": False,
        "needs_project": True,
        "needs_timeline": False,
    }
    project = proto.create_writing_project("Novel")
    assert proto.writing_setup_status() == {
        "ready": False,
        "needs_project": False,
        "needs_timeline": True,
    }
    proto.create_timeline(project["id"], "World")
    assert proto.writing_setup_status() == {
        "ready": True,
        "needs_project": False,
        "needs_timeline": False,
    }


def test_sources_and_entries_roundtrip(proto, db, edges):
    project = proto.create_writing_project("Novel")
    timeline = proto.create_timeline(project["id"], "World")
    note_id = db.add_node(type_="note", fields={"title": "Beat", "content": "Reveal"})
    result = proto.promote_to_timeline(note_id, timeline["id"], uuid=TEST_UUID, mirror=False)
    entry_id = result["entry"]["id"]
    sources = proto.sources_for_entry(entry_id, uuid=TEST_UUID)
    assert len(sources) == 1
    assert sources[0]["id"] == note_id
    entries = proto.entries_from_source(note_id, uuid=TEST_UUID)
    assert len(entries) == 1
    assert entries[0]["id"] == entry_id


def test_standard_relations_enforced(proto, edges):
    import timeline_db as db
    a = db.add_node(type_="note", fields={"title": "A"})
    b = db.add_node(type_="note", fields={"title": "B"})
    with pytest.raises(ValueError, match="unknown relation"):
        proto._link(a, b, "custom_only", uuid=TEST_UUID)
