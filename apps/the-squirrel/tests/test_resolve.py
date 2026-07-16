"""
B-005: name resolution has a confidence floor — a command resolves to ONE
person only when the match is confident, and surfaces the ambiguity instead
of silently picking matches[0] by alphabetical luck.

Borrows ask-jeles's MIN_ASK_SCORE idea: don't call a weak/tied match an answer.
"""
import pytest

from db import get_connection, release_connection
import db.persons as persons_db
from responder.commands.relationship import cmd_link, cmd_show_kin
from responder.commands.tree import cmd_tree


@pytest.fixture
def conn():
    c = get_connection()
    yield c
    release_connection(c)


def _add(conn, name):
    return persons_db.add_person(conn, full_name=name)["id"]


def test_exact_match_beats_substring(conn):
    # The B-005 case: "Albert Einstein" must not be ambiguous just because
    # "Hans Albert Einstein" also contains it.
    _add(conn, "Albert Einstein")
    _add(conn, "Hans Albert Einstein")
    status, person = persons_db.resolve_person(conn, "Albert Einstein")
    assert status == "found"
    assert person["full_name"] == "Albert Einstein"


def test_lone_substring_is_confident(conn):
    _add(conn, "Hans Albert Einstein")
    status, person = persons_db.resolve_person(conn, "Hans")
    assert status == "found"
    assert person["full_name"] == "Hans Albert Einstein"


def test_multiple_substring_is_ambiguous(conn):
    _add(conn, "Albert Einstein")
    _add(conn, "Hans Albert Einstein")
    status, cands = persons_db.resolve_person(conn, "Einstein")
    assert status == "ambiguous"
    assert len(cands) == 2


def test_identical_names_are_ambiguous(conn):
    # Father and son, same name — no alphabetical luck may decide.
    _add(conn, "Oscar Mann")
    _add(conn, "Oscar Mann")
    status, cands = persons_db.resolve_person(conn, "Oscar Mann")
    assert status == "ambiguous"
    assert len(cands) == 2


def test_no_match_is_none(conn):
    status, payload = persons_db.resolve_person(conn, "Nobody Here")
    assert status == "none" and payload is None


def test_tree_surfaces_ambiguity_not_a_guess(conn):
    _add(conn, "Albert Einstein")
    _add(conn, "Hans Albert Einstein")
    out = cmd_tree(conn, ["Einstein"])
    assert "matches several people" in out
    assert "Albert Einstein" in out and "Hans Albert Einstein" in out
    assert "Pedigree" not in out            # did NOT silently draw one


def test_tree_exact_still_draws(conn):
    _add(conn, "Albert Einstein")
    _add(conn, "Hans Albert Einstein")
    out = cmd_tree(conn, ["Albert", "Einstein"])
    assert "tree — Albert Einstein" in out  # exact match resolves and draws
    assert "matches several people" not in out


def test_link_refuses_ambiguous_endpoint(conn):
    _add(conn, "Oscar Mann")
    _add(conn, "Oscar Mann")
    _add(conn, "Carl Mann")
    out = cmd_link(conn, "Oscar Mann → parent → Carl Mann".split())
    assert "matches several people" in out
    # nothing linked — no relationship was written on an ambiguous endpoint
    assert "✓" not in out


def test_show_kin_ambiguous(conn):
    _add(conn, "Oscar Mann")
    _add(conn, "Oscar Mann")
    out = cmd_show_kin(conn, ["Oscar", "Mann"])
    assert "matches several people" in out
