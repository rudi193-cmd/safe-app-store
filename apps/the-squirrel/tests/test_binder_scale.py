"""
B-008 regression: no silent cap, no silent mis-bind, provenance persists.

The verifier's three demands, each pinned:
  - `bind all` examines every unsynced fragment (not the first 200) and
    reports honestly.
  - a tie between similarly-named people is skipped as ambiguous, never
    silently bound to whichever came first.
  - a bound fragment records WHICH person (bound_person_id), not just a
    timestamp.
"""
import pytest

from db import get_connection, release_connection
import db.persons as persons_db
import db.fragments as fragments_db
from binder import Binder


@pytest.fixture
def conn():
    c = get_connection()
    yield c
    release_connection(c)


def _frag(conn, name):
    return fragments_db.add_fragment(conn, person_name=name, fragment_type="name",
                                     story_text=name, source="test")


def test_examines_past_200(conn):
    # 250 non-matching fragments, then one that matches a real person.
    for i in range(250):
        _frag(conn, f"Nobody Number {i}")
    target = _frag(conn, "Oakley Uniquename")
    persons_db.add_person(conn, full_name="Oakley Uniquename")
    r = Binder(conn).auto_bind()
    assert r["examined"] >= 251                # not capped at 200
    assert len(r["bound"]) == 1                # the match past position 200 was found
    assert r["bound"][0]["fragment_id"] == target["id"]


def test_bound_person_id_persists(conn):
    f = _frag(conn, "Hazel Provenance")
    p = persons_db.add_person(conn, full_name="Hazel Provenance")
    Binder(conn).bind(f["id"], p["id"])
    cur = conn.cursor()
    cur.execute("SELECT bound_person_id, binder_synced_at FROM fragments WHERE id = %s", (f["id"],))
    bound_id, synced = cur.fetchone()
    assert bound_id == p["id"]                 # WHICH person, not just a timestamp
    assert synced is not None


def test_tie_is_skipped_not_misbound(conn):
    # Father and son, identical names — the classic genealogy tie.
    _frag(conn, "Oscar Mann")
    persons_db.add_person(conn, full_name="Oscar Mann")
    persons_db.add_person(conn, full_name="Oscar Mann")
    r = Binder(conn).auto_bind()
    assert len(r["bound"]) == 0                # not silently bound to first
    assert r["ambiguous"] == 1                 # flagged for a human instead


def test_shared_suffix_does_not_falsely_bind(conn):
    # "Frag Person 1234" vs a person "Tree Person 1234": different first names,
    # shared suffix — must not cross into a confident bind on its own.
    _frag(conn, "Frag Person 1234")
    persons_db.add_person(conn, full_name="Tree Person 1234")
    r = Binder(conn).auto_bind()
    assert len(r["bound"]) == 0


def test_report_is_honest_when_nothing_matches(conn):
    for i in range(5):
        _frag(conn, f"Unmatchable {i}")
    persons_db.add_person(conn, full_name="Completely Different Name")
    r = Binder(conn).auto_bind()
    assert r["examined"] == 5
    assert len(r["bound"]) == 0
    assert r["remaining"] == 0                 # fully examined, just no matches
