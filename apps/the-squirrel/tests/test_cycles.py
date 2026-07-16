"""
B-002/B-003 regression: ancestor cycles and self-links are refused, and
legitimate pedigree collapse still renders.

Verifier-confirmed cases: self-parent, parent-side 2-cycle, CHILD-side
2-cycle (the direction my first sketch missed), the checking walk surviving
pre-existing cycles, and same-grandfather-both-sides NOT being erased.
"""
import pytest

from db import get_connection, release_connection
import db.persons as persons_db
from responder.commands.relationship import cmd_link
from responder.commands.tree import build_ancestors_dict


@pytest.fixture
def conn():
    c = get_connection()
    yield c
    release_connection(c)


def _add(conn, name):
    return persons_db.add_person(conn, full_name=name)["id"]


def test_self_parent_refused(conn):
    rid = _add(conn, "Ratatosk")
    with pytest.raises(ValueError, match="their own parent"):
        persons_db.add_relationship(conn, rid, rid, "parent")


def test_self_link_refused_for_every_type(conn):
    rid = _add(conn, "Solo")
    for t in ("parent", "child", "spouse", "sibling"):
        with pytest.raises(ValueError, match="their own"):
            persons_db.add_relationship(conn, rid, rid, t)


def test_parent_side_cycle_refused(conn):
    a, b = _add(conn, "Zeus"), _add(conn, "Odin")
    persons_db.add_relationship(conn, a, b, "parent")     # Odin is Zeus's parent
    with pytest.raises(ValueError, match="ancestor loop"):
        persons_db.add_relationship(conn, b, a, "parent")  # Zeus is Odin's parent → loop


def test_child_side_cycle_refused(conn):
    # The direction the first fix sketch missed.
    a, b = _add(conn, "Alpha"), _add(conn, "Beta")
    persons_db.add_relationship(conn, a, b, "child")       # Beta is Alpha's child (Alpha parent Beta)
    with pytest.raises(ValueError, match="ancestor loop"):
        persons_db.add_relationship(conn, b, a, "child")   # Alpha is Beta's child → loop


def test_mixed_direction_cycle_refused(conn):
    a, b = _add(conn, "One"), _add(conn, "Two")
    persons_db.add_relationship(conn, a, b, "parent")      # Two is One's parent
    with pytest.raises(ValueError, match="ancestor loop"):
        persons_db.add_relationship(conn, a, b, "child")   # Two is One's child → loop


def test_grandparent_cycle_refused(conn):
    a, b, c = _add(conn, "Kid"), _add(conn, "Dad"), _add(conn, "Gramps")
    persons_db.add_relationship(conn, a, b, "parent")
    persons_db.add_relationship(conn, b, c, "parent")
    with pytest.raises(ValueError, match="ancestor loop"):
        persons_db.add_relationship(conn, c, a, "parent")  # Kid as Gramps's parent → loop


def test_pedigree_collapse_still_renders(conn):
    # Same grandfather on both sides — a path-local visited-set must keep both.
    kid, dad, mom, gramps = (_add(conn, n) for n in ("Kid", "Dad", "Mom", "Gramps"))
    persons_db.add_relationship(conn, kid, dad, "parent")
    persons_db.add_relationship(conn, kid, mom, "parent")
    persons_db.add_relationship(conn, dad, gramps, "parent")
    persons_db.add_relationship(conn, mom, gramps, "parent")
    anc = build_ancestors_dict(conn, kid, depth=3)
    gramps_slots = sorted(k for k, v in anc.items() if v["full_name"] == "Gramps")
    assert gramps_slots == [4, 6]  # both paternal and maternal slots kept


def test_walker_survives_a_preexisting_cycle(conn):
    # Simulate legacy data: write a cycle directly, bypassing the new guard.
    a, b = _add(conn, "Loop A"), _add(conn, "Loop B")
    cur = conn.cursor()
    cur.execute("INSERT INTO relationships (person_id, related_person_id, relationship_type) "
                "VALUES (%s, %s, 'parent')", (a, b))
    cur.execute("INSERT INTO relationships (person_id, related_person_id, relationship_type) "
                "VALUES (%s, %s, 'parent')", (b, a))
    conn.commit()
    anc = build_ancestors_dict(conn, a, depth=99)  # must terminate, not hang
    assert len(anc) <= 127
    # and the cycle check itself terminates on cyclic data
    assert persons_db.is_ancestor(conn, a, b) is True
