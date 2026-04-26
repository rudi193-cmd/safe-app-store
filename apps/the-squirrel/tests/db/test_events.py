import pytest
from db import get_connection, release_connection
import db.events as events_db
import db.persons as persons_db

@pytest.fixture
def conn():
    c = get_connection()
    events_db.init_schema(c)
    yield c
    c.cursor().execute("DELETE FROM the_squirrel.events WHERE notes LIKE 'TEST%'")
    c.commit()
    release_connection(c)

def test_add_and_get_event(conn):
    person = persons_db.add_person(conn, full_name="TEST Event Person")
    pid = person["id"]
    event = events_db.add_event(conn, person_id=pid, event_type="birth",
                                 date="1882", place="Iowa", notes="TEST birth")
    assert event["person_id"] == pid
    assert event["event_type"] == "birth"
    fetched = events_db.get_events(conn, pid)
    assert any(e["place"] == "Iowa" for e in fetched)
    cur = conn.cursor()
    cur.execute("DELETE FROM the_squirrel.events WHERE person_id = %s", (pid,))
    cur.execute("DELETE FROM the_squirrel.persons WHERE id = %s", (pid,))
    conn.commit()

def test_invalid_event_type(conn):
    with pytest.raises(ValueError, match="Invalid event_type"):
        events_db.add_event(conn, person_id=1, event_type="baptism")
