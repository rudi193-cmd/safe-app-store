import pytest
from db import get_connection, release_connection
import db.media as media_db
import db.persons as persons_db

@pytest.fixture
def conn():
    c = get_connection()
    media_db.init_schema(c)
    yield c
    c.cursor().execute("DELETE FROM the_squirrel.media WHERE caption LIKE 'TEST%'")
    c.commit()
    release_connection(c)

def test_add_and_get_media(conn):
    person = persons_db.add_person(conn, full_name="TEST Media Person")
    pid = person["id"]
    m = media_db.add_media(conn, file_path="/tmp/photo.jpg",
                            mime_type="image/jpeg", caption="TEST photo", person_id=pid)
    assert m["person_id"] == pid
    results = media_db.get_media(conn, pid)
    assert any(r["caption"] == "TEST photo" for r in results)
    cur = conn.cursor()
    cur.execute("DELETE FROM the_squirrel.media WHERE person_id = %s", (pid,))
    cur.execute("DELETE FROM the_squirrel.persons WHERE id = %s", (pid,))
    conn.commit()
