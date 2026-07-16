"""
B-009: control characters are stripped at the db write boundary, and B-007:
the stash page never shows a truncated list under an inflated count.

The sanitization is the cross-cutting fix shared with ask-jeles (its _clean
at corpus._put); the stash-count honesty is Squirrel-specific (Jeles's lists
take an explicit limit and don't inflate a total).
"""
import pytest

from db import get_connection, release_connection, sanitize
import db.persons as persons_db
import db.fragments as fragments_db


@pytest.fixture
def conn():
    c = get_connection()
    yield c
    release_connection(c)


def test_sanitize_strips_c0_keeps_tab_newline():
    assert sanitize("Null\x00Byte") == "NullByte"
    assert sanitize("Bell\x07Name") == "BellName"
    assert sanitize("keep\ttab\nnewline") == "keep\ttab\nnewline"
    assert sanitize(None) is None
    assert sanitize(42) == 42


def test_add_person_stores_clean_name(conn):
    p = persons_db.add_person(conn, full_name="Null\x00Byte Person", birth_place="a\x07b")
    assert "\x00" not in p["full_name"]
    assert p["full_name"] == "NullByte Person"
    assert p["birth_place"] == "ab"


def test_add_fragment_stores_clean_text(conn):
    f = fragments_db.add_fragment(conn, person_name="Bell\x07", fragment_type="story",
                                  story_text="line\x00one\nline two")
    assert "\x07" not in f["person_name"]
    assert "\x00" not in f["story_text"]
    assert "\nline two" in f["story_text"]     # newline preserved


def test_edit_person_sanitizes(conn):
    p = persons_db.add_person(conn, full_name="Clean Start")
    persons_db.update_person_field(conn, p["id"], "bio", "haunted\x00text")
    tree = persons_db.get_family_tree(conn, p["id"])
    assert tree["person"]["bio"] == "hauntedtext"


def test_stash_render_is_honest_about_truncation():
    # >100 fragments must render "showing 100 of N", not a bare "N fragments".
    import squirrel_app
    conn = get_connection()
    try:
        for i in range(105):
            fragments_db.add_fragment(conn, person_name=f"P{i}", fragment_type="name",
                                      story_text=f"frag {i}", source="t")
        html = squirrel_app._render_stash(conn)
        assert "showing 100 of 105 fragments" in html
    finally:
        release_connection(conn)


def test_stash_render_no_note_under_100():
    import squirrel_app
    conn = get_connection()
    try:
        for i in range(3):
            fragments_db.add_fragment(conn, person_name=f"P{i}", fragment_type="name",
                                      story_text=f"frag {i}", source="t")
        html = squirrel_app._render_stash(conn)
        assert "3 fragments" in html and "showing" not in html
    finally:
        release_connection(conn)
