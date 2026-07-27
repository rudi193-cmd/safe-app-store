"""db.events — First-class genealogical events. Schema: the_squirrel"""
from typing import Dict, Any, List
from db import SCHEMA
import sap.core.gate as _gate

VALID_EVENT_TYPES = frozenset({"birth","death","marriage","immigration","census","other"})

def init_schema(conn):
    cur = conn.cursor()
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    cur.execute(f"SET search_path = {SCHEMA}, public")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            person_id   BIGINT NOT NULL REFERENCES persons(id),
            event_type  TEXT NOT NULL
                CHECK (event_type IN ('birth','death','marriage','immigration','census','other')),
            date        TEXT,
            place       TEXT,
            notes       TEXT,
            source_url  TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_person ON events (person_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events (event_type)")
    conn.commit()

def add_event(conn, *, person_id: int, event_type: str, date: str = None,
              place: str = None, notes: str = None, source_url: str = None) -> Dict[str, Any]:
    _gate.authorized("write")
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"Invalid event_type '{event_type}'. Must be one of: {VALID_EVENT_TYPES}")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO events (person_id, event_type, date, place, notes, source_url)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id, person_id, event_type, date, place, notes, source_url, created_at
    """, (person_id, event_type, date, place, notes, source_url))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))

def get_events(conn, person_id: int) -> List[Dict[str, Any]]:
    _gate.authorized("read")
    cur = conn.cursor()
    cur.execute("""
        SELECT id, person_id, event_type, date, place, notes, source_url, created_at
        FROM events WHERE person_id = %s ORDER BY date ASC NULLS LAST
    """, (person_id,))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]
