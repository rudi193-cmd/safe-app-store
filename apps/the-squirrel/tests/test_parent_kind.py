"""
B-011 / B-012: biological vs. adoptive/foster/step parentage linkage.

Closes the cross-parentage gap the Roman-emperors / Steve-Jobs drive found:
the subtype is stored, entered via the link grammar, shown in kin and the
pedigree, and exported to GEDCOM PEDI — and the pedigree no longer drops a
person's extra parents in silence.
"""
import pytest

from db import get_connection, release_connection
import db.persons as persons_db
from responder.commands.relationship import cmd_link, cmd_show_kin, parse_link_args
from responder.commands.tree import cmd_tree, build_ancestors_dict
from gedcom.exporter import build_gedcom_lines


@pytest.fixture
def conn():
    c = get_connection()
    yield c
    release_connection(c)


def _add(conn, name):
    return persons_db.add_person(conn, full_name=name)["id"]


# ── storage + validation ──────────────────────────────────────────────────────

def test_kind_stored_and_returned(conn):
    a, b = _add(conn, "Kid"), _add(conn, "Adopter")
    row = persons_db.add_relationship(conn, a, b, "parent", parent_kind="adopted")
    assert row["parent_kind"] == "adopted"


def test_invalid_kind_refused(conn):
    a, b = _add(conn, "K"), _add(conn, "P")
    with pytest.raises(ValueError, match="Invalid parent kind"):
        persons_db.add_relationship(conn, a, b, "parent", parent_kind="cloned")


def test_kind_only_on_parent_child(conn):
    a, b = _add(conn, "One"), _add(conn, "Two")
    with pytest.raises(ValueError, match="only applies to a parent or child"):
        persons_db.add_relationship(conn, a, b, "spouse", parent_kind="adopted")


def test_plain_parent_has_null_kind(conn):
    a, b = _add(conn, "Kid2"), _add(conn, "Bio")
    row = persons_db.add_relationship(conn, a, b, "parent")
    assert row["parent_kind"] is None


# ── link grammar ──────────────────────────────────────────────────────────────

def test_parse_kind_prefix():
    p = parse_link_args("Steve Jobs → adopted parent → Paul Jobs".split())
    assert p == ("Steve Jobs", "parent", "adopted", "Paul Jobs")


def test_parse_plain_still_works():
    p = parse_link_args("A → parent → B".split())
    assert p == ("A", "parent", None, "B")


def test_cmd_link_with_kind(conn):
    _add(conn, "Steve Jobs"); _add(conn, "Paul Jobs")
    out = cmd_link(conn, "Steve Jobs → adopted parent → Paul Jobs".split())
    assert "adopted parent" in out
    kin = cmd_show_kin(conn, ["Steve", "Jobs"])
    assert "adopted parent: Paul Jobs" in kin


# ── pedigree: no silent truncation (B-011) ────────────────────────────────────

def test_pedigree_prefers_birth_and_names_the_rest(conn):
    steve = _add(conn, "Steve Jobs")
    jandali, schieble = _add(conn, "Abdulfattah Jandali"), _add(conn, "Joanne Schieble")
    paul, clara = _add(conn, "Paul Jobs"), _add(conn, "Clara Jobs")
    persons_db.add_relationship(conn, steve, jandali, "parent", parent_kind="birth")
    persons_db.add_relationship(conn, steve, schieble, "parent", parent_kind="birth")
    persons_db.add_relationship(conn, steve, paul, "parent", parent_kind="adopted")
    persons_db.add_relationship(conn, steve, clara, "parent", parent_kind="adopted")

    anc = build_ancestors_dict(conn, steve, depth=2)
    shown = {anc[2]["full_name"], anc[3]["full_name"]}
    assert shown == {"Abdulfattah Jandali", "Joanne Schieble"}  # birth in the slots

    out = cmd_tree(conn, ["Steve", "Jobs"])
    # the raising parents are NAMED, not silently dropped
    assert "Paul Jobs (adopted)" in out and "Clara Jobs (adopted)" in out
    assert "not shown in the two-slot pedigree" in out


def test_two_parents_no_note(conn):
    kid = _add(conn, "Only Two")
    d, m = _add(conn, "Dad"), _add(conn, "Mom")
    persons_db.add_relationship(conn, kid, d, "parent")
    persons_db.add_relationship(conn, kid, m, "parent")
    out = cmd_tree(conn, ["Only", "Two"])
    assert "not shown" not in out


# ── GEDCOM export carries PEDI ────────────────────────────────────────────────

def test_gedcom_emits_famc_pedi(conn):
    steve = _add(conn, "Steve Jobs")
    jandali = _add(conn, "Abdulfattah Jandali")
    paul = _add(conn, "Paul Jobs")
    persons_db.add_relationship(conn, steve, jandali, "parent", parent_kind="birth")
    persons_db.add_relationship(conn, steve, paul, "parent", parent_kind="adopted")
    persons = persons_db.all_persons(conn)
    rels = persons_db.all_relationships(conn)
    lines = build_gedcom_lines(persons, rels)
    text = "\n".join(lines)
    assert "2 PEDI birth" in text
    assert "2 PEDI adopted" in text
    assert text.count("FAM") >= 2              # two families (birth, adopted)
    assert "1 FAMC" in text and "1 CHIL" in text
