"""
Demo tree tests — load/clear lifecycle on the SQLite path.

Invariants: the Acorns load complete (pedigree renders to grandparents),
are marked as fictional, clear without touching real rows, and the whole
lifecycle rides the gated chokepoint (jeles cannot load or clear it).
"""
import pytest

from db import get_connection, release_connection
import db.persons as persons_db
import sap.core.gate as gate
from responder.commands.demo import cmd_demo
from responder.commands.tree import build_ancestors_dict


@pytest.fixture
def conn():
    c = get_connection()
    yield c
    release_connection(c)


def test_demo_load_builds_a_full_pedigree(conn):
    out = cmd_demo(conn, ["load"])
    assert "9 persons" in out
    hazel = persons_db.search_persons(conn, "Hazel Acorn")[0]
    ancestors = build_ancestors_dict(conn, hazel["id"], depth=3)
    # Ahnentafel 1..7: subject, both parents, all four grandparents.
    assert set(ancestors) >= {1, 2, 3, 4, 5, 6, 7}
    assert hazel["memorial_id"] == "DEMO"
    assert "Fictional" in hazel["bio"]


def test_demo_load_is_refused_twice(conn):
    cmd_demo(conn, ["load"])
    assert "already in the tree" in cmd_demo(conn, ["load"])


def test_demo_clear_removes_only_marked_rows(conn):
    real = persons_db.add_person(conn, full_name="Real Ancestor", birth_date="1850")
    cmd_demo(conn, ["load"])
    out = cmd_demo(conn, ["clear"])
    assert "9 fictional persons" in out
    assert persons_db.search_persons(conn, "Acorn") == []
    assert persons_db.search_persons(conn, "Real Ancestor")[0]["id"] == real["id"]
    assert "No demo data" in cmd_demo(conn, ["clear"])


def test_demo_rides_the_gate(conn):
    with gate.actor("jeles"):
        with pytest.raises(gate.PermissionDenied):
            cmd_demo(conn, ["load"])
