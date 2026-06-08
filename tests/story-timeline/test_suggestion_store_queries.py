import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apps/story-timeline"))


@pytest.fixture(autouse=True)
def reset_db(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(tmp_path / "timeline.db"))
    for name in ("timeline_db", "suggestion_store"):
        sys.modules.pop(name, None)


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(tmp_path / "timeline.db"))
    import importlib
    import timeline_db
    import suggestion_store
    importlib.reload(timeline_db)
    importlib.reload(suggestion_store)
    return suggestion_store


def test_list_suggestions_filters_status(store):
    src = "source-a"
    store.create_suggestion(
        src,
        suggestion_kind="promotion",
        proposed_fields={"timeline_id": "tl-1", "title": "A"},
        status=store.STATUS_PENDING,
    )
    store.create_suggestion(
        src,
        suggestion_kind="promotion",
        proposed_fields={"timeline_id": "tl-1", "title": "B"},
        status=store.STATUS_DISMISSED,
    )
    pending = store.list_suggestions(status=store.STATUS_PENDING)
    assert len(pending) == 1
    assert pending[0]["fields"]["proposed_fields"]["title"] == "A"


def test_list_research_respects_limit(store):
    for i in range(5):
        store.create_research_packet(
            f"src-{i}",
            query=f"q{i}",
            summary=f"summary {i}",
        )
    assert len(store.list_research()) == 5
    assert len(store.list_research(limit=2)) == 2


def test_counts_for_source(store):
    src = "note-1"
    store.create_research_packet(src, query="q", summary="s")
    store.create_suggestion(
        src,
        suggestion_kind="promotion",
        proposed_fields={"timeline_id": "tl", "title": "Beat"},
        status=store.STATUS_PENDING,
    )
    store.create_suggestion(
        src,
        suggestion_kind="promotion",
        proposed_fields={"timeline_id": "tl", "title": "Old"},
        status=store.STATUS_ACCEPTED,
    )
    counts = store.counts_for_source(src)
    assert counts["research"] == 1
    assert counts["pending_suggestions"] == 1
    assert counts["suggestions"] == 2


def test_pending_for_timeline(store):
    store.create_suggestion(
        "src-a",
        suggestion_kind="promotion",
        proposed_fields={"timeline_id": "tl-a", "title": "On A"},
        status=store.STATUS_PENDING,
    )
    store.create_suggestion(
        "src-b",
        suggestion_kind="promotion",
        proposed_fields={"timeline_id": "tl-b", "title": "On B"},
        status=store.STATUS_PENDING,
    )
    pending = store.pending_for_timeline("tl-a")
    assert len(pending) == 1
    assert pending[0]["fields"]["proposed_fields"]["title"] == "On A"


def test_dashboard_counts(store):
    import timeline_db as db

    db.add_node(type_="book", fields={"title": "Book"})
    db.add_node(type_="note", fields={"title": "Note"})
    db.add_node(type_="writing_project", fields={"title": "Novel"})
    store.create_research_packet("note-x", query="q", summary="s")
    store.create_suggestion(
        "note-x",
        suggestion_kind="promotion",
        proposed_fields={"timeline_id": "tl", "title": "Beat"},
        status=store.STATUS_PENDING,
    )

    counts = store.dashboard_counts()
    assert counts["books"] == 1
    assert counts["notes"] == 1
    assert counts["writing_projects"] == 1
    assert counts["pending_suggestions"] == 1
    assert counts["research_packets"] == 1
