"""Tests for import_csv.py — Goodreads/StoryGraph/LibraryThing importer."""
import csv
import os
import sys
from pathlib import Path

import pytest

# Point DB at a temp file for every test
@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_timeline.db"
    monkeypatch.setenv("STORY_TIMELINE_DB", str(db_path))
    # Re-init DB with fresh path
    import importlib
    import timeline_db
    monkeypatch.setattr(timeline_db, "DB_PATH", db_path)
    timeline_db._init_db()
    yield db_path


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


# ── detect_source ─────────────────────────────────────────────────────────────

def test_detect_goodreads():
    from import_csv import detect_source
    assert detect_source(["Title", "Author", "Exclusive Shelf", "Bookshelves"]) == "goodreads"


def test_detect_storygraph():
    from import_csv import detect_source
    assert detect_source(["Title", "Authors", "Read Status", "Star Rating"]) == "storygraph"


def test_detect_librarything():
    from import_csv import detect_source
    assert detect_source(["Title", "Author", "Collections", "Date"]) == "librarything"


# ── _import_id dedup ──────────────────────────────────────────────────────────

def test_import_id_stable():
    from import_csv import _import_id
    assert _import_id("Dune", "Frank Herbert") == _import_id("dune", "frank herbert")
    assert _import_id("Dune", "Frank Herbert") == _import_id("Dune", "Frank Herbert")


def test_import_id_distinct():
    from import_csv import _import_id
    assert _import_id("Dune", "Frank Herbert") != _import_id("Foundation", "Isaac Asimov")


# ── Goodreads import ──────────────────────────────────────────────────────────

GOODREADS_FIELDS = [
    "Book Id", "Title", "Author", "Author l-f", "ISBN", "ISBN13",
    "My Rating", "Average Rating", "Publisher", "Binding",
    "Number of Pages", "Year Published", "Original Publication Year",
    "Date Read", "Date Added", "Bookshelves", "Bookshelves with positions",
    "Exclusive Shelf", "My Review", "Spoiler", "Private Notes",
    "Read Count", "Owned Copies",
]


def test_goodreads_basic_import(tmp_path):
    from import_csv import run_import
    import timeline_db

    csv_file = _write_csv(tmp_path / "gr.csv", [
        {
            "Book Id": "1", "Title": "Dune", "Author": "Frank Herbert",
            "Author l-f": "Herbert, Frank", "ISBN": "=0441013597",
            "ISBN13": "=9780441013593", "My Rating": "5",
            "Average Rating": "4.26", "Publisher": "Ace",
            "Binding": "Paperback", "Number of Pages": "412",
            "Year Published": "1990", "Original Publication Year": "1965",
            "Date Read": "2023/01/15", "Date Added": "2023/01/01",
            "Bookshelves": "sci-fi,favorites", "Bookshelves with positions": "",
            "Exclusive Shelf": "read", "My Review": "A masterpiece.",
            "Spoiler": "N", "Private Notes": "", "Read Count": "1", "Owned Copies": "1",
        }
    ], GOODREADS_FIELDS)

    result = run_import(csv_file, source="goodreads")
    assert result["imported"] == 1
    assert result["skipped"] == 0
    assert result["errors"] == 0

    nodes = timeline_db.get_nodes(type_="book")
    assert len(nodes) == 1
    n = nodes[0]
    assert n["fields"]["title"] == "Dune"
    assert n["fields"]["author"] == "Frank Herbert"
    assert n["fields"]["shelf"] == "read"
    assert n["fields"]["rating"] == 5
    assert n["fields"]["isbn"] == "0441013597"
    assert n["id"].startswith("imported-")


def test_goodreads_dedup(tmp_path):
    from import_csv import run_import

    row = {
        "Book Id": "1", "Title": "Dune", "Author": "Frank Herbert",
        "Author l-f": "", "ISBN": "", "ISBN13": "", "My Rating": "5",
        "Average Rating": "4.26", "Publisher": "", "Binding": "",
        "Number of Pages": "", "Year Published": "", "Original Publication Year": "",
        "Date Read": "", "Date Added": "", "Bookshelves": "",
        "Bookshelves with positions": "", "Exclusive Shelf": "read",
        "My Review": "", "Spoiler": "", "Private Notes": "", "Read Count": "1",
        "Owned Copies": "0",
    }
    csv_file = _write_csv(tmp_path / "gr.csv", [row], GOODREADS_FIELDS)

    r1 = run_import(csv_file, source="goodreads")
    r2 = run_import(csv_file, source="goodreads")
    assert r1["imported"] == 1
    assert r2["imported"] == 0
    assert r2["skipped"] == 1


def test_goodreads_shelf_normalisation(tmp_path):
    from import_csv import run_import
    import timeline_db

    rows = [
        {"Book Id": "1", "Title": "Book A", "Author": "Auth A", "Author l-f": "",
         "ISBN": "", "ISBN13": "", "My Rating": "0", "Average Rating": "",
         "Publisher": "", "Binding": "", "Number of Pages": "",
         "Year Published": "", "Original Publication Year": "",
         "Date Read": "", "Date Added": "", "Bookshelves": "",
         "Bookshelves with positions": "", "Exclusive Shelf": "to-read",
         "My Review": "", "Spoiler": "", "Private Notes": "", "Read Count": "0",
         "Owned Copies": "0"},
        {"Book Id": "2", "Title": "Book B", "Author": "Auth B", "Author l-f": "",
         "ISBN": "", "ISBN13": "", "My Rating": "0", "Average Rating": "",
         "Publisher": "", "Binding": "", "Number of Pages": "",
         "Year Published": "", "Original Publication Year": "",
         "Date Read": "", "Date Added": "", "Bookshelves": "",
         "Bookshelves with positions": "", "Exclusive Shelf": "currently-reading",
         "My Review": "", "Spoiler": "", "Private Notes": "", "Read Count": "0",
         "Owned Copies": "0"},
    ]
    csv_file = _write_csv(tmp_path / "gr.csv", rows, GOODREADS_FIELDS)
    run_import(csv_file, source="goodreads")

    nodes = {n["fields"]["title"]: n for n in timeline_db.get_nodes(type_="book")}
    assert nodes["Book A"]["fields"]["shelf"] == "to-read"
    assert nodes["Book B"]["fields"]["shelf"] == "currently-reading"


# ── StoryGraph import ─────────────────────────────────────────────────────────

STORYGRAPH_FIELDS = [
    "Title", "Authors", "Read Status", "Star Rating", "Last Date Read",
    "Review", "Tags", "Number of Pages", "ISBN/UID", "Date Added",
]


def test_storygraph_import(tmp_path):
    from import_csv import run_import
    import timeline_db

    csv_file = _write_csv(tmp_path / "sg.csv", [
        {
            "Title": "Foundation", "Authors": "Isaac Asimov",
            "Read Status": "read", "Star Rating": "4",
            "Last Date Read": "2022-06-01", "Review": "Classic.",
            "Tags": "sci-fi", "Number of Pages": "244",
            "ISBN/UID": "9780553293357", "Date Added": "2022-05-01",
        }
    ], STORYGRAPH_FIELDS)

    result = run_import(csv_file, source="storygraph")
    assert result["imported"] == 1
    nodes = timeline_db.get_nodes(type_="book")
    assert nodes[0]["fields"]["title"] == "Foundation"
    assert nodes[0]["fields"]["shelf"] == "read"


def test_storygraph_currently_reading(tmp_path):
    from import_csv import run_import
    import timeline_db

    csv_file = _write_csv(tmp_path / "sg.csv", [
        {
            "Title": "Neuromancer", "Authors": "William Gibson",
            "Read Status": "currently reading", "Star Rating": "",
            "Last Date Read": "", "Review": "", "Tags": "",
            "Number of Pages": "271", "ISBN/UID": "", "Date Added": "",
        }
    ], STORYGRAPH_FIELDS)

    run_import(csv_file, source="storygraph")
    nodes = timeline_db.get_nodes(type_="book")
    assert nodes[0]["fields"]["shelf"] == "currently-reading"


# ── LibraryThing import ───────────────────────────────────────────────────────

LIBRARYTHING_FIELDS = [
    "Title", "Author", "Rating", "Collections", "Date", "Review", "Tags",
    "Publisher", "Pages", "ISBN", "Entry Date",
]


def test_librarything_import(tmp_path):
    from import_csv import run_import
    import timeline_db

    csv_file = _write_csv(tmp_path / "lt.csv", [
        {
            "Title": "1984", "Author": "George Orwell",
            "Rating": "5", "Collections": "Your library",
            "Date": "2021-03-10", "Review": "Essential.",
            "Tags": "dystopia,classics", "Publisher": "Penguin",
            "Pages": "328", "ISBN": "9780141036144", "Entry Date": "2021-01-01",
        }
    ], LIBRARYTHING_FIELDS)

    result = run_import(csv_file, source="librarything")
    assert result["imported"] == 1
    nodes = timeline_db.get_nodes(type_="book")
    assert nodes[0]["fields"]["title"] == "1984"
    assert nodes[0]["fields"]["shelf"] == "read"


def test_librarything_to_read(tmp_path):
    from import_csv import run_import
    import timeline_db

    csv_file = _write_csv(tmp_path / "lt.csv", [
        {
            "Title": "Middlemarch", "Author": "George Eliot",
            "Rating": "0", "Collections": "To Read",
            "Date": "", "Review": "", "Tags": "", "Publisher": "",
            "Pages": "800", "ISBN": "", "Entry Date": "",
        }
    ], LIBRARYTHING_FIELDS)

    run_import(csv_file, source="librarything")
    nodes = timeline_db.get_nodes(type_="book")
    assert nodes[0]["fields"]["shelf"] == "to-read"


# ── Author nodes ──────────────────────────────────────────────────────────────

def test_author_nodes_created(tmp_path):
    from import_csv import run_import
    import timeline_db

    rows = [
        {"Book Id": "1", "Title": "Dune", "Author": "Frank Herbert",
         "Author l-f": "", "ISBN": "", "ISBN13": "", "My Rating": "5",
         "Average Rating": "", "Publisher": "", "Binding": "",
         "Number of Pages": "", "Year Published": "", "Original Publication Year": "",
         "Date Read": "", "Date Added": "", "Bookshelves": "",
         "Bookshelves with positions": "", "Exclusive Shelf": "read",
         "My Review": "", "Spoiler": "", "Private Notes": "", "Read Count": "1",
         "Owned Copies": "0"},
        {"Book Id": "2", "Title": "Dune Messiah", "Author": "Frank Herbert",
         "Author l-f": "", "ISBN": "", "ISBN13": "", "My Rating": "4",
         "Average Rating": "", "Publisher": "", "Binding": "",
         "Number of Pages": "", "Year Published": "", "Original Publication Year": "",
         "Date Read": "", "Date Added": "", "Bookshelves": "",
         "Bookshelves with positions": "", "Exclusive Shelf": "read",
         "My Review": "", "Spoiler": "", "Private Notes": "", "Read Count": "1",
         "Owned Copies": "0"},
    ]
    csv_file = _write_csv(tmp_path / "gr.csv", rows, GOODREADS_FIELDS)

    result = run_import(csv_file, source="goodreads", create_authors=True)
    assert result["imported"] == 2
    assert result["author_nodes"] == 1  # one unique author

    author_nodes = timeline_db.get_nodes(type_="author")
    assert len(author_nodes) == 1
    assert author_nodes[0]["fields"]["name"] == "Frank Herbert"


# ── Dry run ───────────────────────────────────────────────────────────────────

def test_dry_run_writes_nothing(tmp_path):
    from import_csv import run_import
    import timeline_db

    csv_file = _write_csv(tmp_path / "gr.csv", [
        {"Book Id": "1", "Title": "Dune", "Author": "Frank Herbert",
         "Author l-f": "", "ISBN": "", "ISBN13": "", "My Rating": "5",
         "Average Rating": "", "Publisher": "", "Binding": "",
         "Number of Pages": "", "Year Published": "", "Original Publication Year": "",
         "Date Read": "", "Date Added": "", "Bookshelves": "",
         "Bookshelves with positions": "", "Exclusive Shelf": "read",
         "My Review": "", "Spoiler": "", "Private Notes": "", "Read Count": "1",
         "Owned Copies": "0"},
    ], GOODREADS_FIELDS)

    result = run_import(csv_file, source="goodreads", dry_run=True)
    assert result["imported"] == 1
    assert len(timeline_db.get_nodes()) == 0


# ── Auto-detect ───────────────────────────────────────────────────────────────

def test_autodetect_goodreads(tmp_path):
    from import_csv import run_import
    import timeline_db

    csv_file = _write_csv(tmp_path / "gr.csv", [
        {"Book Id": "1", "Title": "Dune", "Author": "Frank Herbert",
         "Author l-f": "", "ISBN": "", "ISBN13": "", "My Rating": "5",
         "Average Rating": "", "Publisher": "", "Binding": "",
         "Number of Pages": "", "Year Published": "", "Original Publication Year": "",
         "Date Read": "", "Date Added": "", "Bookshelves": "",
         "Bookshelves with positions": "", "Exclusive Shelf": "read",
         "My Review": "", "Spoiler": "", "Private Notes": "", "Read Count": "1",
         "Owned Copies": "0"},
    ], GOODREADS_FIELDS)

    result = run_import(csv_file)  # no source= specified
    assert result["imported"] == 1
    assert timeline_db.get_nodes(type_="book")[0]["fields"]["title"] == "Dune"
