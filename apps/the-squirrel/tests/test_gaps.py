"""
The acknowledged-unknowns ledger (sap.core.gaps) — the Squirrel finally
means the ΔΣ=42 it signs every file with.

Modeled on ask-jeles's gap backlog, with the one deliberate divergence that
matters: these gaps name family members (PII), so the ledger is LOCAL and
never forwards — see test_chokepoint (unchanged: still zero egress).
"""
import pytest

from db import get_connection, release_connection
import sap.core.gaps as gaps
from responder.commands.relationship import cmd_link, cmd_show_kin
from responder.commands.tree import cmd_tree
from responder.commands.person import cmd_add_person
from responder.commands.control import cmd_gaps


@pytest.fixture
def conn():
    c = get_connection()
    yield c
    release_connection(c)


def test_deliberate_name_miss_logs_a_gap(conn):
    cmd_tree(conn, ["Oscar", "Mann"])           # not in the tree
    rows = gaps.list_open()
    assert len(rows) == 1
    assert rows[0]["kind"] == "unknown_person"
    assert rows[0]["subject"] == "Oscar Mann"


def test_repeat_miss_bumps_count_not_duplicates(conn):
    cmd_tree(conn, ["Oscar", "Mann"])
    cmd_show_kin(conn, ["Oscar", "Mann"])
    cmd_tree(conn, ["oscar", "mann"])           # case-insensitive same gap
    rows = gaps.list_open()
    assert len(rows) == 1
    assert rows[0]["asked_count"] == 3


def test_adding_the_person_resolves_the_gap(conn):
    cmd_tree(conn, ["Carl", "Mann"])
    assert gaps.count_open() == 1
    out = cmd_add_person(conn, ["Carl", "Mann", "b.1855"])
    assert "resolved an open gap" in out
    assert gaps.count_open() == 0


def test_ambiguous_bind_logs_a_gap(conn):
    import db.persons as P
    import db.fragments as F
    from binder import Binder
    F.add_fragment(conn, person_name="Oscar Mann", fragment_type="name",
                   story_text="Oscar Mann", source="t")
    P.add_person(conn, full_name="Oscar Mann")
    P.add_person(conn, full_name="Oscar Mann")   # the tie
    Binder(conn).auto_bind()
    rows = gaps.list_open()
    assert any(g["kind"] == "ambiguous_bind" for g in rows)


def test_gaps_command_lists_and_resolves(conn):
    cmd_tree(conn, ["Ada", "Lovelace"])
    out = cmd_gaps([])
    assert "unknown person" in out and "Ada Lovelace" in out
    gid = gaps.list_open()[0]["id"]
    done = cmd_gaps(["resolve", gid])
    assert "resolved" in done
    assert gaps.count_open() == 0


def test_empty_ledger_message(conn):
    assert "No open gaps" in cmd_gaps([])


def test_found_person_logs_no_gap(conn):
    import db.persons as P
    P.add_person(conn, full_name="Grace Hopper")
    cmd_tree(conn, ["Grace", "Hopper"])          # present — not a gap
    assert gaps.count_open() == 0
