"""
gatefirst.store — SQLite storage that cannot exist without a checked-in session.

The retrofit puts authorized() at the top of every db function; any code that
imports db.persons holds the whole PII surface and a thread-local decides at
call time. Here the decision moved to the constructor: no live WillowGate
session, no Store. Methods still clear gate.authorize_tool() per call — the
ledger announces every touch — but that is the second wall, not the first.
"""

import sqlite3

VALID_CONFIDENCE = frozenset({"confirmed", "likely", "uncertain", "speculative"})


class Denied(PermissionError):
    """The gate refused — at construction or at the moment of use."""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS persons (
    id          INTEGER PRIMARY KEY,
    full_name   TEXT NOT NULL,
    birth_date  TEXT,
    birth_place TEXT,
    death_date  TEXT,
    death_place TEXT
);
CREATE TABLE IF NOT EXISTS fragments (
    id          INTEGER PRIMARY KEY,
    person_name TEXT NOT NULL,
    person_id   INTEGER REFERENCES persons(id),
    story_text  TEXT,
    confidence  TEXT NOT NULL DEFAULT 'uncertain'
);
"""


class Store:
    """A miniature of the real schema: persons + fragments only."""

    def __init__(self, gate, session, db_path=":memory:"):
        if gate is None or not isinstance(session, dict):
            raise Denied("no gate session — storage is unreachable without checking in")
        if session.get("nonce") not in gate.sessions:
            raise Denied("session is not live at this gate — check in first")
        self._gate = gate
        self._session = session
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def _clear(self, tool, *, export=False):
        ok, why = self._gate.authorize_tool(self._session, tool, export=export)
        if not ok:
            raise Denied(why)

    # ── reads ────────────────────────────────────────────────────────────────

    def search_persons(self, name_query=""):
        self._clear("read")
        rows = self._conn.execute(
            "SELECT * FROM persons WHERE full_name LIKE ? ORDER BY full_name",
            (f"%{name_query}%",)).fetchall()
        return [dict(r) for r in rows]

    def get_person(self, person_id):
        self._clear("read")
        row = self._conn.execute(
            "SELECT * FROM persons WHERE id = ?", (person_id,)).fetchone()
        return dict(row) if row else None

    def list_fragments(self, person_name=None):
        self._clear("read")
        if person_name is None:
            rows = self._conn.execute("SELECT * FROM fragments ORDER BY id").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM fragments WHERE person_name LIKE ? ORDER BY id",
                (f"%{person_name}%",)).fetchall()
        return [dict(r) for r in rows]

    # ── writes ───────────────────────────────────────────────────────────────

    def add_person(self, *, full_name, birth_date=None, birth_place=None,
                   death_date=None, death_place=None):
        self._clear("write")
        cur = self._conn.execute(
            "INSERT INTO persons (full_name, birth_date, birth_place, death_date, death_place) "
            "VALUES (?, ?, ?, ?, ?)",
            (full_name, birth_date, birth_place, death_date, death_place))
        self._conn.commit()
        return self.get_person(cur.lastrowid)

    def add_fragment(self, *, person_name, story_text, confidence="uncertain"):
        self._clear("write")
        if confidence not in VALID_CONFIDENCE:
            raise ValueError(f"invalid confidence {confidence!r} — one of {sorted(VALID_CONFIDENCE)}")
        cur = self._conn.execute(
            "INSERT INTO fragments (person_name, story_text, confidence) VALUES (?, ?, ?)",
            (person_name, story_text, confidence))
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM fragments WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)

    def link(self, fragment_id, person_id):
        self._clear("write")
        self._conn.execute(
            "UPDATE fragments SET person_id = ? WHERE id = ?", (person_id, fragment_id))
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM fragments WHERE id = ?", (fragment_id,)).fetchone()
        return dict(row) if row else None

    # ── export — PII leaving the box ─────────────────────────────────────────

    def export_gedcom_text(self):
        self._clear("read", export=True)
        lines = ["0 HEAD", "1 SOUR THE-SQUIRREL-GATEFIRST",
                 "1 GEDC", "2 VERS 5.5.1", "1 CHAR UTF-8"]
        for r in self._conn.execute("SELECT * FROM persons ORDER BY id"):
            lines.append(f"0 @I{r['id']}@ INDI")
            lines.append(f"1 NAME {r['full_name']}")
            for tag, date, place in (("BIRT", r["birth_date"], r["birth_place"]),
                                     ("DEAT", r["death_date"], r["death_place"])):
                if date or place:
                    lines.append(f"1 {tag}")
                    if date:
                        lines.append(f"2 DATE {date}")
                    if place:
                        lines.append(f"2 PLAC {place}")
        lines.append("0 TRLR")
        return "\n".join(lines) + "\n"
