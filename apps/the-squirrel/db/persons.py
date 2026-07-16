"""
db.persons — PII layer: persons, relationships, person_lattice_cells, person_sources.
Schema: the_squirrel

Persons are fully-resolved individuals in the family tree.
Fragments (db.fragments) are raw observations; persons are what the Binder promotes them to.

SAP gate (L3-R15): all write functions call sap.core.gate.authorized() before touching PII.
Reads (search_persons, get_family_tree) are gated on "read" for symmetry.
init_schema() is DDL — no PII, no gate.
"""

from typing import Dict, Any, List
from db import _validate_lattice, SCHEMA, clean_params, sanitize
import sap.core.gate as _gate

VALID_RELATIONSHIP_TYPES = frozenset({"parent", "child", "spouse", "sibling"})
VALID_SOURCE_TYPES = frozenset({"findagrave", "familysearch", "census", "document", "oral"})

# Parentage linkage subtype (B-012): "fathered by one, raised by another".
# None = unspecified. Priority orders which parents fill the two pedigree
# slots — biological lineage first, by genealogical convention, but the
# others are shown, never dropped silently (B-011).
VALID_PARENT_KINDS = frozenset({"birth", "adopted", "foster", "step"})
PARENT_KIND_PRIORITY = {"birth": 0, None: 1, "adopted": 2, "foster": 3, "step": 4}


def init_schema(conn):
    """Create persons, relationships, person_lattice_cells, person_sources. Idempotent."""
    cur = conn.cursor()
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    cur.execute(f"SET search_path = {SCHEMA}, public")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS persons (
            id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            full_name    TEXT NOT NULL,
            birth_date   TEXT,
            birth_place  TEXT,
            death_date   TEXT,
            death_place  TEXT,
            burial_place TEXT,
            memorial_id  TEXT,
            memorial_url TEXT,
            bio          TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_deleted   BOOLEAN DEFAULT FALSE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS relationships (
            id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            person_id         BIGINT NOT NULL REFERENCES persons(id),
            related_person_id BIGINT NOT NULL REFERENCES persons(id),
            relationship_type TEXT NOT NULL
                CHECK (relationship_type IN ('parent','child','spouse','sibling')),
            parent_kind       TEXT,
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # B-012: linkage subtype for tables created before parent_kind existed.
    # Idempotent — probe the column, add it only if absent.
    try:
        cur.execute("SELECT parent_kind FROM relationships LIMIT 1")
        cur.fetchall()
    except Exception:
        conn.rollback()
        cur = conn.cursor()
        # Postgres rolls back the session SET search_path along with the failed
        # probe (a plain SET is transactional), so restore it before the ALTER
        # or the table resolves to the wrong schema. SQLite translates this to
        # a no-op.
        cur.execute(f"SET search_path = {SCHEMA}, public")
        cur.execute("ALTER TABLE relationships ADD COLUMN parent_kind TEXT")
        conn.commit()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS person_lattice_cells (
            id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            person_id    BIGINT NOT NULL REFERENCES persons(id),
            domain       TEXT NOT NULL,
            depth        INTEGER NOT NULL CHECK (depth >= 1 AND depth <= 23),
            temporal     TEXT NOT NULL,
            content      TEXT NOT NULL,
            source       TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_sensitive BOOLEAN DEFAULT FALSE,
            UNIQUE(person_id, domain, depth, temporal)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS person_sources (
            id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            person_id    BIGINT NOT NULL REFERENCES persons(id),
            source_type  TEXT NOT NULL
                CHECK (source_type IN ('findagrave','familysearch','census','document','oral')),
            source_url   TEXT,
            source_title TEXT,
            raw_content  TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_persons_name ON persons (full_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rel_person ON relationships (person_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rel_related ON relationships (related_person_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_plc_person ON person_lattice_cells (person_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_plc_domain ON person_lattice_cells (domain)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_plc_temporal ON person_lattice_cells (temporal)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_psrc_person ON person_sources (person_id)")

    conn.commit()


def add_person(conn, *, full_name: str, birth_date: str = None, birth_place: str = None,
               death_date: str = None, death_place: str = None, burial_place: str = None,
               memorial_id: str = None, memorial_url: str = None, bio: str = None) -> Dict[str, Any]:
    """Insert a person. Returns the new row as a dict."""
    _gate.authorized("write")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO persons (full_name, birth_date, birth_place, death_date, death_place,
                             burial_place, memorial_id, memorial_url, bio)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, full_name, birth_date, birth_place, death_date, death_place,
                  burial_place, memorial_id, memorial_url, bio, created_at, updated_at, is_deleted
    """, clean_params((full_name, birth_date, birth_place, death_date, death_place,
                       burial_place, memorial_id, memorial_url, bio)))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def _parent_ids(conn, child_id: int) -> List[int]:
    """The parent person_ids of child_id, from BOTH row directions:
    forward `(child, X, 'parent')` and reverse `(X, child, 'child')`.
    Read-only helper for the cycle check — gated by its callers."""
    cur = conn.cursor()
    cur.execute(
        "SELECT related_person_id FROM relationships "
        "WHERE person_id = %s AND relationship_type = 'parent' "
        "UNION "
        "SELECT person_id FROM relationships "
        "WHERE related_person_id = %s AND relationship_type = 'child'",
        (child_id, child_id))
    return [r[0] for r in cur.fetchall()]


def is_ancestor(conn, ancestor_id: int, of_id: int) -> bool:
    """True if ancestor_id is already an ancestor of of_id. Walks up via
    _parent_ids with a visited-set, so it terminates even if the existing
    graph already contains a cycle (every install could — nothing prevented
    them before this)."""
    seen = set()
    stack = list(_parent_ids(conn, of_id))
    while stack:
        pid = stack.pop()
        if pid == ancestor_id:
            return True
        if pid in seen:
            continue
        seen.add(pid)
        stack.extend(_parent_ids(conn, pid))
    return False


def add_relationship(conn, person_id: int, related_id: int, rel_type: str,
                     parent_kind: str = None) -> Dict[str, Any]:
    """Link two persons. Returns the new relationship row as a dict.

    Refuses self-links (a person is not their own parent/child/spouse/sibling)
    and refuses a parent/child link that would close an ancestor loop —
    direction-agnostic, so `A → child → B` is checked the same as
    `B → parent → A`.

    parent_kind (birth/adopted/foster/step, or None) records HOW someone is a
    parent — "fathered by one, raised by another". Only meaningful for
    parent/child links; ignored otherwise."""
    _gate.authorized("write")
    if rel_type not in VALID_RELATIONSHIP_TYPES:
        raise ValueError(f"Invalid relationship_type '{rel_type}'. Must be one of: {VALID_RELATIONSHIP_TYPES}")
    if person_id == related_id:
        raise ValueError("A person cannot be their own " + rel_type + ".")
    if parent_kind is not None:
        if parent_kind not in VALID_PARENT_KINDS:
            raise ValueError(f"Invalid parent kind '{parent_kind}'. Must be one of: {sorted(VALID_PARENT_KINDS)}")
        if rel_type not in ("parent", "child"):
            raise ValueError(f"A '{parent_kind}' kind only applies to a parent or child link.")
    if rel_type in ("parent", "child"):
        # Normalize to (child, parent): "A parent B" => B is A's parent;
        # "A child B" => A is B's parent.
        child_id, parent_id = (person_id, related_id) if rel_type == "parent" else (related_id, person_id)
        # Adding "parent_id is parent of child_id" loops iff child_id is
        # already an ancestor of parent_id.
        if is_ancestor(conn, child_id, parent_id):
            raise ValueError(
                "That link would create an ancestor loop — the descendant is "
                "already an ancestor of the parent.")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO relationships (person_id, related_person_id, relationship_type, parent_kind)
        VALUES (%s, %s, %s, %s)
        RETURNING id, person_id, related_person_id, relationship_type, parent_kind, created_at
    """, (person_id, related_id, rel_type, parent_kind))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def add_source(conn, person_id: int, source_type: str, url: str = None,
               title: str = None, content: str = None) -> Dict[str, Any]:
    """Attach a source record to a person. Returns the new source row as a dict."""
    _gate.authorized("write")
    if source_type not in VALID_SOURCE_TYPES:
        raise ValueError(f"Invalid source_type '{source_type}'. Must be one of: {VALID_SOURCE_TYPES}")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO person_sources (person_id, source_type, source_url, source_title, raw_content)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id, person_id, source_type, source_url, source_title, raw_content, created_at
    """, (person_id, source_type, url, title, content))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def place_in_lattice(conn, person_id: int, domain: str, depth: int, temporal: str,
                     content: str, source: str = None, is_sensitive: bool = False) -> Dict[str, Any]:
    """Map a person to a lattice cell. Upserts on (person_id, domain, depth, temporal)."""
    _gate.authorized("write")
    _validate_lattice(domain, depth, temporal)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO person_lattice_cells
            (person_id, domain, depth, temporal, content, source, is_sensitive)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (person_id, domain, depth, temporal)
        DO UPDATE SET content = EXCLUDED.content,
                      source = EXCLUDED.source,
                      is_sensitive = EXCLUDED.is_sensitive
        RETURNING id, person_id, domain, depth, temporal, content, source, created_at, is_sensitive
    """, (person_id, domain, depth, temporal, content, source, is_sensitive))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def get_family_tree(conn, person_id: int) -> Dict[str, Any]:
    """Return the person record plus all relationships. Immutable result."""
    _gate.authorized("read")
    cur = conn.cursor()
    cur.execute("SELECT * FROM persons WHERE id = %s AND is_deleted = FALSE", (person_id,))
    person_row = cur.fetchone()
    if person_row is None:
        return {"person": None, "relationships": []}
    pcols = [d[0] for d in cur.description]
    person = dict(zip(pcols, person_row))

    cur.execute("""
        SELECT r.*, p.full_name AS related_name
        FROM relationships r JOIN persons p ON p.id = r.related_person_id
        WHERE r.person_id = %s
        UNION ALL
        SELECT r.*, p.full_name AS related_name
        FROM relationships r JOIN persons p ON p.id = r.person_id
        WHERE r.related_person_id = %s
        ORDER BY id
    """, (person_id, person_id))
    rows = cur.fetchall()
    rcols = [d[0] for d in cur.description]
    return {"person": person, "relationships": [dict(zip(rcols, r)) for r in rows]}


EDITABLE_FIELDS = frozenset({"birth_date", "death_date", "birth_place",
                             "death_place", "burial_place", "bio"})


def update_person_field(conn, person_id: int, field: str, value: str) -> bool:
    """Update one editable field. Returns False if no such person."""
    _gate.authorized("write")
    if field not in EDITABLE_FIELDS:
        raise ValueError(f"Field '{field}' is not editable. Allowed: {sorted(EDITABLE_FIELDS)}")
    cur = conn.cursor()
    # field is whitelist-checked above; values are parameterized.
    cur.execute(f"UPDATE persons SET {field} = %s, updated_at = CURRENT_TIMESTAMP "
                f"WHERE id = %s AND is_deleted = FALSE", (sanitize(value), person_id))
    if cur.rowcount == 0:
        conn.rollback()
        return False
    conn.commit()
    return True


def all_persons(conn) -> List[Dict[str, Any]]:
    """Every live person — the GEDCOM export walk."""
    _gate.authorized("read")
    cur = conn.cursor()
    cur.execute("SELECT * FROM persons WHERE is_deleted = FALSE ORDER BY id")
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]


def all_relationships(conn) -> List[Dict[str, Any]]:
    """Every relationship — the GEDCOM export walk."""
    _gate.authorized("read")
    cur = conn.cursor()
    cur.execute("SELECT * FROM relationships ORDER BY id")
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]


def delete_marked_persons(conn, memorial_mark: str) -> int:
    """Hard-delete persons whose memorial_id equals the mark, plus their
    relationships, lattice cells, and sources. Exists for demo teardown —
    the one sanctioned hard delete (archive-don't-delete applies to real
    data; fictional seed rows are not data). Returns persons removed."""
    _gate.authorized("write")
    cur = conn.cursor()
    cur.execute("SELECT id FROM persons WHERE memorial_id = %s", (memorial_mark,))
    ids = [r[0] for r in cur.fetchall()]
    if not ids:
        return 0
    marks = ", ".join(["%s"] * len(ids))
    cur.execute(f"DELETE FROM relationships WHERE person_id IN ({marks}) "
                f"OR related_person_id IN ({marks})", ids + ids)
    cur.execute(f"DELETE FROM person_lattice_cells WHERE person_id IN ({marks})", ids)
    cur.execute(f"DELETE FROM person_sources WHERE person_id IN ({marks})", ids)
    cur.execute(f"DELETE FROM persons WHERE id IN ({marks})", ids)
    conn.commit()
    return len(ids)


def search_persons(conn, name_query: str) -> List[Dict[str, Any]]:
    """Search persons by name (case-insensitive ILIKE). Returns list of dicts."""
    _gate.authorized("read")
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM persons
        WHERE full_name ILIKE %s AND is_deleted = FALSE
        ORDER BY full_name
    """, (f"%{name_query}%",))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]


def resolve_person(conn, query: str):
    """Resolve a name to a single person, or refuse to guess (B-005).

    The confidence floor, borrowed from ask-jeles's MIN_ASK_SCORE: a command
    that needs ONE person may only act on a confident resolution, never on the
    first of several equally-good substring hits picked by alphabetical luck.

    Returns one of:
      ("found", person)          exactly one confident match
      ("ambiguous", [persons])   several equally-good matches — caller surfaces
      ("none", None)             nothing matched

    Precedence: an exact (case-insensitive) full_name match beats a substring
    match, so "Albert Einstein" resolves to the person named exactly that even
    when "Hans Albert Einstein" also contains it. A lone substring match is
    confident; multiple substring matches with no exact are ambiguous."""
    if not (query or "").strip():
        return ("none", None)          # an empty query matches everyone — resolve to no-one
    matches = search_persons(conn, query)
    if not matches:
        return ("none", None)
    q = " ".join(query.split()).strip().lower()
    exact = [p for p in matches if " ".join(p["full_name"].split()).lower() == q]
    if len(exact) == 1:
        return ("found", exact[0])
    if len(exact) > 1:
        return ("ambiguous", exact)
    if len(matches) == 1:
        return ("found", matches[0])
    return ("ambiguous", matches)
