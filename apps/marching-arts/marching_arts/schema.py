"""The first migration, carrying the two columns that cannot be added later.

``band`` and ``source`` are on the fact table from migration 001. Both can be
added to a schema afterwards; neither can be added to data already written
without them. A retrofit leaves you choosing a default for a million rows, and
whatever you choose is wrong for some of them.

``source`` is copied straight from dci_scores.db, which carries a provenance
string on every results, captions and repertoire row and a completeness flag on
every event. That database was built for an unrelated purpose and arrived at the
same rule independently: absence is a recorded value, not a missing row.

The CHECK constraints are the mechanism. An empty source is rejected by SQLite
itself, so a caller cannot forget to supply one and no application-layer
discipline is required to keep the guarantee true.
"""
from __future__ import annotations

from .bands import Band

MIGRATIONS: "list[tuple[str, str]]" = [
    (
        "001_facts_and_grants",
        """
        CREATE TABLE IF NOT EXISTS facts (
            id          INTEGER PRIMARY KEY,
            subject_id  TEXT    NOT NULL,
            band        INTEGER NOT NULL
                        CHECK (band BETWEEN {lo} AND {hi}),
            payload     TEXT,
            -- What a viewer who may not see the payload is told to do instead.
            instruction TEXT,
            -- Provenance. Not nullable, not blank: a fact with no source is not
            -- a fact, it is a rumour with a primary key.
            source      TEXT    NOT NULL
                        CHECK (length(trim(source)) > 0),
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS ix_facts_subject ON facts(subject_id, band);

        CREATE TABLE IF NOT EXISTS grants (
            id          INTEGER PRIMARY KEY,
            subject_id  TEXT    NOT NULL,   -- whose information
            grantee_id  TEXT    NOT NULL,   -- who may see it
            band        INTEGER NOT NULL
                        CHECK (band BETWEEN {lo} AND {hi}),
            -- sealed | draft | pending. Only 'sealed' authorizes anything.
            state       TEXT    NOT NULL
                        CHECK (state IN ('sealed', 'draft', 'pending')),
            -- Who signed it. Required when sealed: a grant nobody signed is a
            -- grant the system invented, and the schema will not store one.
            sealed_by   TEXT,
            source      TEXT    NOT NULL
                        CHECK (length(trim(source)) > 0),
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            CHECK (state != 'sealed' OR (sealed_by IS NOT NULL
                                         AND length(trim(sealed_by)) > 0)),
            UNIQUE (subject_id, grantee_id)
        );

        CREATE INDEX IF NOT EXISTS ix_grants_lookup
            ON grants(subject_id, grantee_id, state, band);
        """.format(lo=int(min(Band)), hi=int(max(Band))),
    ),
]


def apply(conn) -> list[str]:
    """Run every migration not yet applied. Returns the names that ran."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " name TEXT PRIMARY KEY,"
        " applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    done = {r[0] for r in conn.execute("SELECT name FROM schema_migrations")}
    ran = []
    for name, sql in MIGRATIONS:
        if name in done:
            continue
        conn.executescript(sql)
        conn.execute("INSERT INTO schema_migrations(name) VALUES (?)", (name,))
        ran.append(name)
    conn.commit()
    return ran
