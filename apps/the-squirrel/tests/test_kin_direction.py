"""
Regression: relationship direction — found by the Einstein drive test.

A row (child, parent, 'parent') read from the parent's side must present
as 'child', and the ancestor walker must never follow reverse rows back
into the subject.
"""
from db import get_connection, release_connection
import db.persons as persons_db
from responder.commands.tree import build_ancestors_dict
from responder.commands.relationship import cmd_show_kin


def test_reverse_rows_invert_and_dont_pollute_the_pedigree():
    conn = get_connection()
    try:
        albert = persons_db.add_person(conn, full_name="Albert Test", birth_date="1879")
        hermann = persons_db.add_person(conn, full_name="Hermann Test", birth_date="1847")
        hans = persons_db.add_person(conn, full_name="Hans Test", birth_date="1904")
        # Child rows FIRST — before the parent row — so the old walker,
        # which trusted list order, would have walked Hans as an ancestor.
        persons_db.add_relationship(conn, hans["id"], albert["id"], "parent")
        persons_db.add_relationship(conn, albert["id"], hermann["id"], "parent")

        ancestors = build_ancestors_dict(conn, albert["id"], depth=3)
        names = {p["full_name"] for p in ancestors.values()}
        assert "Hermann Test" in names
        assert "Hans Test" not in names          # the child is not an ancestor

        kin = cmd_show_kin(conn, ["Albert", "Test"])
        assert "child: Hans Test" in kin         # reverse row, inverted label
        assert "parent: Hermann Test" in kin
    finally:
        release_connection(conn)
