import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apps/story-timeline"))

TEST_UUID = "test-user-intel"


@pytest.fixture(autouse=True)
def reset_db(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(tmp_path / "timeline.db"))
    for name in (
        "timeline_db",
        "willow_edges",
        "story_protocol",
        "soil_protocol",
        "mcp_client",
        "suggestion_store",
        "intelligence",
    ):
        sys.modules.pop(name, None)


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(tmp_path / "timeline.db"))
    import importlib
    import timeline_db
    importlib.reload(timeline_db)
    return timeline_db


@pytest.fixture()
def edges(monkeypatch):
    import importlib
    import willow_edges
    importlib.reload(willow_edges)

    class Client:
        _available = True

        def __init__(self):
            self._store: dict = {}

        def put(self, collection, record, record_id=None):
            key = record_id or record.get("id")
            self._store[key] = dict(record)
            return key

        def list(self, collection):
            return list(self._store.values())

        def delete(self, collection, record_id):
            return False

    client = Client()
    willow_edges._CLIENT = client
    willow_edges._CLIENT_INIT_FAILED = False
    return willow_edges


@pytest.fixture()
def modules(db, edges):
    import importlib
    import mcp_client
    import story_protocol
    import suggestion_store
    import intelligence
    importlib.reload(mcp_client)
    importlib.reload(story_protocol)
    importlib.reload(suggestion_store)
    importlib.reload(intelligence)
    mcp_client.reset_for_tests()
    return {
        "mcp": mcp_client,
        "proto": story_protocol,
        "store": suggestion_store,
        "intel": intelligence,
    }


def _mock_handler(mapping: dict):
    def handler(name, inputs):
        val = mapping.get(name)
        if callable(val):
            return val(inputs)
        if val is not None:
            return val
        raise RuntimeError(f"unexpected tool: {name}")
    return handler


def test_suggest_promotion_offline_heuristic(modules, db, monkeypatch):
    intel = modules["intel"]
    proto = modules["proto"]
    monkeypatch.setenv("STORY_TIMELINE_DISABLE_MCP", "1")
    note_id = db.add_node(type_="note", fields={"title": "Fog scene", "content": "Mist at dawn"})
    project = proto.create_writing_project("Novel")
    timeline = proto.create_timeline(project["id"], "World")

    bundle = intel.suggest_promotion(db.get_node(note_id))
    assert bundle["offline"] is True
    suggestion = bundle["suggestion"]
    assert suggestion["type"] == "slm_suggestion"
    assert suggestion["fields"]["proposed_fields"]["timeline_id"] == timeline["id"]
    assert suggestion["fields"]["status"] == "pending"


def test_suggest_promotion_with_mock_mcp(modules, db):
    intel = modules["intel"]
    proto = modules["proto"]
    mcp = modules["mcp"]

    mcp.set_test_override(_mock_handler({
        "mem_jeles_ask": {
            "answer": "Fog often signals liminality.",
            "sources": [{"title": "Source A"}],
        },
        "kb_search": {"knowledge": [{"title": "Prior note"}]},
        "infer_7b": lambda inputs: (
            {"one_line": "A misty opening beat"}
            if inputs.get("task_type") == "summarize"
            else {"category": "Novel / World", "confidence": 0.82, "reason": "fits"}
        ),
    }))

    note_id = db.add_node(type_="note", fields={"title": "Fog scene", "content": "Mist"})
    proto.create_writing_project("Novel")
    proto.create_timeline(
        proto.list_writing_projects()[0]["id"], "World",
    )

    bundle = intel.suggest_promotion(db.get_node(note_id))
    assert bundle["offline"] is False
    assert bundle["research"] is not None
    assert bundle["suggestion"]["fields"]["model"] == "infer_7b"


def test_suggest_reading_recommendations_for_project_offline(modules, db, monkeypatch):
    intel = modules["intel"]
    store = modules["store"]
    monkeypatch.setenv("STORY_TIMELINE_DISABLE_MCP", "1")
    project_id = db.add_node(
        type_="project",
        fields={
            "title": "Ecology of Arrakis",
            "summary": "Research desert ecology and political ecology for worldbuilding.",
            "status": "active",
            "tags": "ecology, politics",
        },
    )

    bundle = intel.suggest_reading_recommendations(db.get_node(project_id))
    suggestion = bundle["suggestion"]

    assert bundle["offline"] is True
    assert suggestion["fields"]["suggestion_kind"] == intel.READING_RECOMMENDATION_KIND
    assert suggestion["fields"]["proposed_fields"]["title"] != f"Background reading for Ecology of Arrakis"
    assert suggestion["fields"]["proposed_fields"]["author"]
    assert "Ecology of Arrakis" in suggestion["fields"]["proposed_fields"]["reason"]
    assert store.list_suggestions(status=store.STATUS_PENDING)


def test_suggest_reading_recommendations_project_uses_project_context(modules, db):
    intel = modules["intel"]
    mcp = modules["mcp"]
    captured: dict = {}

    def infer_handler(inputs):
        captured["inputs"] = inputs
        return {
            "recommendations": [
                {
                    "title": "The Ecology of Freedom",
                    "author": "Murray Bookchin",
                    "reason": "Foundational political ecology.",
                    "tags": "ecology",
                }
            ]
        }

    mcp.set_test_override(_mock_handler({
        "mem_jeles_ask": {
            "answer": "Consider political ecology and desert studies.",
            "sources": [{"title": "Ecology reader"}],
        },
        "kb_search": {"knowledge": []},
        "infer_7b": infer_handler,
    }))

    project_id = db.add_node(
        type_="project",
        fields={
            "title": "Desert Politics",
            "summary": "Worldbuilding around scarcity and governance.",
            "status": "planning",
        },
    )
    bundle = intel.suggest_reading_recommendations(db.get_node(project_id))

    assert bundle["offline"] is False
    assert bundle["suggestion"]["fields"]["proposed_fields"]["title"] == "The Ecology of Freedom"
    ctx = captured["inputs"].get("context", "")
    assert "library project" in ctx.lower()
    assert "Desert Politics" in captured["inputs"].get("content", "")
    assert "Worldbuilding around scarcity" in ctx


def test_suggest_reading_recommendations_for_author_offline(modules, db, monkeypatch):
    intel = modules["intel"]
    monkeypatch.setenv("STORY_TIMELINE_DISABLE_MCP", "1")
    author_id = db.add_node(type_="author", fields={"name": "Philip K. Dick"})

    bundle = intel.suggest_reading_recommendations(db.get_node(author_id))
    title = bundle["suggestion"]["fields"]["proposed_fields"]["title"]

    assert title != "More like Philip K. Dick"
    assert bundle["suggestion"]["fields"]["proposed_fields"]["author"]
    assert title in {
        "The Left Hand of Darkness",
        "Flowers for Algernon",
        "Slaughterhouse-Five",
    }


def test_suggest_reading_recommendations_needs_no_writing_project(modules, db, monkeypatch):
    intel = modules["intel"]
    store = modules["store"]
    monkeypatch.setenv("STORY_TIMELINE_DISABLE_MCP", "1")
    book_id = db.add_node(
        type_="book",
        fields={"title": "Dune", "author": "Frank Herbert", "tags": "science fiction"},
    )

    bundle = intel.suggest_reading_recommendations(db.get_node(book_id))
    suggestion = bundle["suggestion"]

    assert bundle["offline"] is True
    assert suggestion["fields"]["suggestion_kind"] == intel.READING_RECOMMENDATION_KIND
    assert suggestion["fields"]["proposed_fields"]["shelf"] == "to-read"
    assert store.list_suggestions(status=store.STATUS_PENDING)


def test_accept_reading_recommendation_adds_to_read_book(modules, db, monkeypatch):
    intel = modules["intel"]
    store = modules["store"]
    monkeypatch.setenv("STORY_TIMELINE_DISABLE_MCP", "1")
    project_id = db.add_node(type_="project", fields={"title": "Library project"})

    bundle = intel.suggest_reading_recommendations(db.get_node(project_id))
    sid = bundle["suggestion"]["id"]
    out = intel.accept_suggestion(
        sid,
        edits={
            "title": "The Left Hand of Darkness",
            "author": "Ursula K. Le Guin",
            "reason": "Adjacent classic speculative fiction.",
            "tags": "science fiction",
        },
    )

    assert out["book"]["type"] == "book"
    assert out["book"]["fields"]["shelf"] == "to-read"
    assert out["book"]["fields"]["title"] == "The Left Hand of Darkness"
    assert store.get_suggestion(sid)["fields"]["status"] == "accepted"


def test_suggest_reading_recommendations_with_mock_mcp(modules, db):
    intel = modules["intel"]
    mcp = modules["mcp"]

    mcp.set_test_override(_mock_handler({
        "mem_jeles_ask": {
            "answer": "Look for political ecological science fiction.",
            "sources": [{"title": "Reader guide"}],
        },
        "kb_search": {"knowledge": []},
        "infer_7b": lambda inputs: {
            "recommendations": [
                {
                    "title": "The Dispossessed",
                    "author": "Ursula K. Le Guin",
                    "reason": "Political SF with social systems at the center.",
                    "tags": "science fiction",
                }
            ]
        },
    }))

    book_id = db.add_node(type_="book", fields={"title": "Dune", "author": "Frank Herbert"})
    bundle = intel.suggest_reading_recommendations(db.get_node(book_id))

    assert bundle["offline"] is False
    suggestion = bundle["suggestion"]
    assert suggestion["fields"]["model"] == "infer_7b"
    assert suggestion["fields"]["proposed_fields"]["title"] == "The Dispossessed"


def test_suggest_reading_recommendations_filters_source_book(modules, db):
    intel = modules["intel"]
    mcp = modules["mcp"]

    mcp.set_test_override(_mock_handler({
        "mem_jeles_ask": {"answer": "Try adjacent political science fiction."},
        "kb_search": {"knowledge": []},
        "infer_7b": lambda inputs: {
            "recommendations": [
                {
                    "title": "Dune",
                    "author": "Frank Herbert",
                    "reason": "The model echoed the source.",
                },
                {
                    "title": "The Dispossessed",
                    "author": "Ursula K. Le Guin",
                    "reason": "Adjacent political science fiction.",
                },
            ]
        },
    }))

    book_id = db.add_node(type_="book", fields={"title": "Dune", "author": "Frank Herbert"})
    bundle = intel.suggest_reading_recommendations(db.get_node(book_id))
    titles = [
        s["fields"]["proposed_fields"]["title"]
        for s in bundle["suggestions"]
    ]

    assert titles == ["The Dispossessed"]


def test_suggest_reading_recommendations_filters_existing_books(modules, db):
    intel = modules["intel"]
    mcp = modules["mcp"]

    db.add_node(type_="book", fields={"title": "The Dispossessed", "author": "Ursula K. Le Guin"})
    mcp.set_test_override(_mock_handler({
        "mem_jeles_ask": {"answer": "Try adjacent political science fiction."},
        "kb_search": {"knowledge": []},
        "infer_7b": lambda inputs: {
            "recommendations": [
                {
                    "title": "The Dispossessed",
                    "author": "Ursula K. Le Guin",
                    "reason": "Already in the library.",
                },
                {
                    "title": "The Left Hand of Darkness",
                    "author": "Ursula K. Le Guin",
                    "reason": "Adjacent speculative anthropology.",
                },
            ]
        },
    }))

    book_id = db.add_node(type_="book", fields={"title": "Dune", "author": "Frank Herbert"})
    bundle = intel.suggest_reading_recommendations(db.get_node(book_id))
    titles = [
        s["fields"]["proposed_fields"]["title"]
        for s in bundle["suggestions"]
    ]

    assert titles == ["The Left Hand of Darkness"]


def test_accept_suggestion_promotes(modules, db, edges):
    intel = modules["intel"]
    proto = modules["proto"]
    store = modules["store"]

    note_id = db.add_node(type_="note", fields={"title": "Beat", "content": "Reveal"})
    project = proto.create_writing_project("Novel")
    timeline = proto.create_timeline(project["id"], "World")

    bundle = intel.suggest_promotion(db.get_node(note_id))
    sid = bundle["suggestion"]["id"]

    out = intel.accept_suggestion(sid, uuid=TEST_UUID)
    assert out["promotion"]["entry"]["type"] == "timeline_entry"
    updated = store.get_suggestion(sid)
    assert updated["fields"]["status"] == "accepted"
    entries = proto.list_timeline_entries(timeline["id"])
    assert len(entries) == 1


def test_dismiss_suggestion(modules, db):
    intel = modules["intel"]
    proto = modules["proto"]
    store = modules["store"]

    note_id = db.add_node(type_="note", fields={"title": "Beat", "content": "Reveal"})
    project = proto.create_writing_project("Novel")
    proto.create_timeline(project["id"], "World")
    bundle = intel.suggest_promotion(db.get_node(note_id))
    sid = bundle["suggestion"]["id"]
    assert intel.dismiss_suggestion(sid) is True
    assert store.get_suggestion(sid)["fields"]["status"] == "dismissed"


def test_bundle_for_suggestion(modules, db):
    intel = modules["intel"]
    proto = modules["proto"]

    note_id = db.add_node(type_="note", fields={"title": "Beat", "content": "Reveal"})
    project = proto.create_writing_project("Novel")
    proto.create_timeline(project["id"], "World")
    bundle = intel.suggest_promotion(db.get_node(note_id))
    sid = bundle["suggestion"]["id"]

    loaded = intel.bundle_for_suggestion(sid)
    assert loaded["suggestion"]["id"] == sid
    assert loaded["context"]["source"]["id"] == note_id
    assert loaded["context"]["timelines"]


def test_run_jeles_research_rejects_unauthorized(modules, db):
    intel = modules["intel"]
    store = modules["store"]
    mcp = modules["mcp"]

    mcp.set_test_override(_mock_handler({
        "mem_jeles_ask": {
            "error": "unauthorized",
            "app_id": "story-timeline",
            "tool": "mem_jeles_ask",
        },
    }))
    note_id = db.add_node(type_="note", fields={"title": "Beat", "content": "Reveal"})
    result = intel.run_jeles_research(db.get_node(note_id))

    assert result["ok"] is False
    assert "unauthorized" in result["error"].lower()
    assert store.list_research_for_source(note_id) == []


def test_suggest_reading_still_works_when_jeles_unauthorized(modules, db):
    intel = modules["intel"]
    store = modules["store"]
    mcp = modules["mcp"]

    mcp.set_test_override(_mock_handler({
        "mem_jeles_ask": {"error": "unauthorized"},
        "kb_search": {"knowledge": []},
        "infer_7b": {"error": "unauthorized"},
    }))
    book_id = db.add_node(type_="book", fields={"title": "Dune", "author": "Herbert"})
    bundle = intel.suggest_reading_recommendations(db.get_node(book_id))

    assert bundle["suggestion"] is not None
    assert bundle["suggestion"]["fields"]["model"] == "heuristic"
    assert store.list_research_for_source(book_id) == []


def test_research_view_for_packet_surfaces_unauthorized(modules, db):
    intel = modules["intel"]
    store = modules["store"]

    note_id = db.add_node(type_="note", fields={"title": "Beat", "content": "Reveal"})
    packet = store.create_research_packet(
        note_id,
        query="q",
        summary="",
        raw={"error": "unauthorized", "tool": "mem_jeles_ask"},
    )
    view = intel.research_view_for_packet(packet)
    assert view["ok"] is False
    assert "unauthorized" in view["error"].lower()


def test_run_jeles_research_offline(modules, db, monkeypatch):
    intel = modules["intel"]
    mcp = modules["mcp"]
    mcp.reset_for_tests()
    monkeypatch.setenv("STORY_TIMELINE_DISABLE_MCP", "1")
    note_id = db.add_node(type_="note", fields={"title": "Beat", "content": "Reveal"})
    result = intel.run_jeles_research(db.get_node(note_id))
    assert result["ok"] is False
    assert "error" in result


def test_research_creates_packet_when_mcp_available(modules, db):
    intel = modules["intel"]
    store = modules["store"]
    mcp = modules["mcp"]

    mcp.set_test_override(_mock_handler({
        "mem_jeles_ask": {
            "answer": "Cited answer.",
            "sources": [{"title": "LOC", "url": "https://loc.gov"}],
        },
    }))
    note_id = db.add_node(type_="note", fields={"title": "Beat", "content": "Reveal"})
    result = intel.run_jeles_research(db.get_node(note_id))
    assert result["ok"] is True
    packets = store.list_research_for_source(note_id)
    assert len(packets) == 1
    assert packets[0]["fields"]["summary"] == "Cited answer."
