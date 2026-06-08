import csv
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apps/story-timeline"))


@pytest.fixture(autouse=True)
def reset_db(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(tmp_path / "timeline.db"))
    for name in ("timeline_db", "suggestion_store", "export_lists"):
        sys.modules.pop(name, None)


@pytest.fixture()
def modules(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(tmp_path / "timeline.db"))
    import importlib
    import timeline_db
    import suggestion_store
    import export_lists
    importlib.reload(timeline_db)
    importlib.reload(suggestion_store)
    importlib.reload(export_lists)
    return timeline_db, suggestion_store, export_lists


def test_books_for_scope_to_read(modules):
    db, _store, exports = modules
    db.add_node(type_="book", fields={"title": "Read Book", "author": "A", "shelf": "read"})
    db.add_node(type_="book", fields={"title": "Library Trip", "author": "B", "shelf": "to-read"})

    books = exports.books_for_scope("to-read")

    assert [b["fields"]["title"] for b in books] == ["Library Trip"]


def test_books_for_scope_selected_source_pending_recommendations(modules):
    db, store, exports = modules
    source_id = db.add_node(type_="project", fields={"title": "Desert Project"})
    store.create_suggestion(
        source_id,
        suggestion_kind="reading_recommendation",
        proposed_fields={
            "title": "The Ecology of Freedom",
            "author": "Murray Bookchin",
            "shelf": "to-read",
            "reason": "Useful background.",
            "tags": "ecology",
        },
    )

    books = exports.books_for_scope("selected-source", source_id=source_id)

    assert len(books) == 1
    assert books[0]["fields"]["title"] == "The Ecology of Freedom"
    assert books[0]["fields"]["shelf"] == "to-read"


def test_export_bundle_writes_markdown_and_goodreads_csv(tmp_path, modules):
    db, _store, exports = modules
    book_id = db.add_node(
        type_="book",
        fields={
            "title": "Kindred",
            "author": "Octavia E. Butler",
            "shelf": "to-read",
            "tags": "fiction",
            "review": "Ask at the library.",
        },
    )
    book = db.get_node(book_id)

    out = exports.export_bundle([book], label="to-read", out_dir=tmp_path)

    markdown = tmp_path / os.path.basename(out["markdown"])
    csv_path = tmp_path / os.path.basename(out["csv"])
    assert markdown.exists()
    assert csv_path.exists()
    assert "Kindred" in markdown.read_text(encoding="utf-8")
    assert "Ask at the library." in markdown.read_text(encoding="utf-8")

    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["Title"] == "Kindred"
    assert rows[0]["Author"] == "Octavia E. Butler"
    assert rows[0]["Exclusive Shelf"] == "to-read"
