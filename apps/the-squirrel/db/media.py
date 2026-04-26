"""db.media — Media attachments linked to persons or events. Schema: the_squirrel"""
from typing import Dict, Any, List
from db import SCHEMA
import sap.core.gate as _gate

VALID_MIME_TYPES = frozenset({
    "image/jpeg","image/png","image/gif","image/tiff",
    "application/pdf","text/plain"
})

def init_schema(conn):
    cur = conn.cursor()
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    cur.execute(f"SET search_path = {SCHEMA}, public")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS media (
            id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            file_path   TEXT NOT NULL,
            mime_type   TEXT NOT NULL,
            caption     TEXT,
            person_id   BIGINT REFERENCES persons(id),
            event_id    BIGINT REFERENCES events(id),
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_media_person ON media (person_id)")
    conn.commit()

def add_media(conn, *, file_path: str, mime_type: str, caption: str = None,
              person_id: int = None, event_id: int = None) -> Dict[str, Any]:
    _gate.authorized("write")
    if mime_type not in VALID_MIME_TYPES:
        raise ValueError(f"Invalid mime_type '{mime_type}'.")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO media (file_path, mime_type, caption, person_id, event_id)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id, file_path, mime_type, caption, person_id, event_id, created_at
    """, (file_path, mime_type, caption, person_id, event_id))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))

def get_media(conn, person_id: int) -> List[Dict[str, Any]]:
    _gate.authorized("read")
    cur = conn.cursor()
    cur.execute("""
        SELECT id, file_path, mime_type, caption, person_id, event_id, created_at
        FROM media WHERE person_id = %s ORDER BY created_at DESC
    """, (person_id,))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]
