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

Migrations 002 and 003 are P2, and they extend the same idea from constraints to
triggers, because the rules P2 has to keep are about *pairs* of tables and a
``CHECK`` cannot see past its own row:

* a minor's grant must be signed by a guardian who is registered as one, and
  guardian authority stops at the age of majority — two tables, three rules;
* consent may not be requested or signed by the person who benefits from it,
  with a carve-out for a registered guardian of the subject;
* the same guardian rule over subject-consent's own hash-chained consent log,
  which is the concrete payoff of keeping that log in this database instead of
  a file beside it.

Each is a ``RAISE(ABORT)``. Not a validator a caller can forget to call, and not
a comment: a code path that has never heard of these rules still cannot break
them.
"""
from __future__ import annotations

from .bands import Band
from .policy import MAJORITY_AGE

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
    (
        "002_people_guardianship_and_consent_chain",
        """
        -- ── who is a minor, and who may consent for them ────────────────────
        -- A birthdate rather than an is_minor flag. A flag is true until
        -- somebody remembers to run the job that clears it; a birthdate is
        -- true continuously, and "still a minor" is then a fact the predicate
        -- can evaluate on every read with nothing scheduled.
        CREATE TABLE IF NOT EXISTS people (
            person_id  TEXT PRIMARY KEY,
            -- Both halves are needed, and the order they are written in is not
            -- the interesting part -- the NULL is. `date('not-a-date')` is
            -- NULL, `birthdate = NULL` is NULL, and a CHECK that evaluates to
            -- NULL *passes*. So a malformed birthdate would sail in, and then
            -- every "still a minor" test comparing against it would also be
            -- NULL, and NULL is not true, and a fourteen-year-old would quietly
            -- become an adult with no guardian requirement left on them. The
            -- IS NOT NULL is what turns that into a refused insert.
            birthdate  TEXT NOT NULL
                       CHECK (date(birthdate) IS NOT NULL
                              AND birthdate = date(birthdate)),
            source     TEXT NOT NULL CHECK (length(trim(source)) > 0),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS guardianships (
            guardian_id TEXT NOT NULL,
            subject_id  TEXT NOT NULL REFERENCES people(person_id) ON DELETE CASCADE,
            -- subject_consent.RELATIONS minus 'self': a guardianship is by
            -- definition somebody else's, and the CHECK below says so twice.
            relation    TEXT NOT NULL
                        CHECK (relation IN ('child', 'ward', 'household', 'other')),
            source      TEXT NOT NULL CHECK (length(trim(source)) > 0),
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (guardian_id, subject_id),
            CHECK (guardian_id <> subject_id)
        );

        -- ── the hash-chained consent + disclosure log, in this same file ────
        -- subject_consent owns the chain LOGIC (prev-links, row hashes, the
        -- head anchor that makes tail truncation detectable). These two tables
        -- are where the rows land, so consent, disclosure and domain data are
        -- one database, backed up and audited as a unit. The anchor is a table
        -- and not a column so that a row and its anchor commit together.
        CREATE TABLE IF NOT EXISTS consent_chain (
            chain TEXT    NOT NULL,
            seq   INTEGER NOT NULL,
            row   TEXT    NOT NULL,   -- the core's hash-chained row, verbatim JSON
            PRIMARY KEY (chain, seq)
        );

        CREATE TABLE IF NOT EXISTS consent_anchor (
            chain TEXT    PRIMARY KEY,
            hash  TEXT    NOT NULL,
            count INTEGER NOT NULL
        );

        -- ── grants gain provenance of the consent itself ────────────────────
        -- Rebuilt rather than ALTERed: the new rules are table constraints and
        -- SQLite cannot add one to an existing table. Migration 001's rows
        -- carry forward unchanged and default to member-granted.
        DROP INDEX IF EXISTS ix_grants_lookup;
        ALTER TABLE grants RENAME TO grants_001;

        CREATE TABLE grants (
            id          INTEGER PRIMARY KEY,
            subject_id  TEXT    NOT NULL,   -- whose information
            grantee_id  TEXT    NOT NULL,   -- who may see it
            band        INTEGER NOT NULL
                        CHECK (band BETWEEN {lo} AND {hi}),
            state       TEXT    NOT NULL
                        CHECK (state IN ('sealed', 'draft', 'pending')),
            sealed_by   TEXT,
            -- 'member': the subject signed for themselves.
            -- 'guardian': a registered guardian signed for a minor. That
            -- authority is not permanent — the resolver stops honouring it the
            -- day the subject turns eighteen, with no job to run.
            granted_via TEXT    NOT NULL DEFAULT 'member'
                        CHECK (granted_via IN ('member', 'guardian')),
            -- Who asked for this grant. Never the person who benefits from it;
            -- a trigger below refuses the insert.
            requested_by TEXT,
            source      TEXT    NOT NULL
                        CHECK (length(trim(source)) > 0),
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            CHECK (state != 'sealed' OR (sealed_by IS NOT NULL
                                         AND length(trim(sealed_by)) > 0)),
            UNIQUE (subject_id, grantee_id)
        );

        INSERT INTO grants (id, subject_id, grantee_id, band, state, sealed_by,
                            source, created_at)
            SELECT id, subject_id, grantee_id, band, state, sealed_by,
                   source, created_at
            FROM grants_001;

        DROP TABLE grants_001;

        CREATE INDEX IF NOT EXISTS ix_grants_lookup
            ON grants(subject_id, grantee_id, state, band);

        -- ── a minor's consent is a guardian's to give ───────────────────────
        CREATE TRIGGER IF NOT EXISTS trg_grants_minor_needs_guardian_ins
        BEFORE INSERT ON grants
        WHEN new.state = 'sealed'
         AND new.granted_via <> 'guardian'
         AND EXISTS (SELECT 1 FROM people p
                     WHERE p.person_id = new.subject_id
                       AND date('now') < date(p.birthdate, '+{majority} years'))
        BEGIN
            SELECT RAISE(ABORT,
                'a minor does not consent for themselves: seal it through a guardian');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_grants_minor_needs_guardian_upd
        BEFORE UPDATE ON grants
        WHEN new.state = 'sealed'
         AND new.granted_via <> 'guardian'
         AND EXISTS (SELECT 1 FROM people p
                     WHERE p.person_id = new.subject_id
                       AND date('now') < date(p.birthdate, '+{majority} years'))
        BEGIN
            SELECT RAISE(ABORT,
                'a minor does not consent for themselves: seal it through a guardian');
        END;

        -- ── guardian authority is registered, and it is not permanent ───────
        -- Both halves in one condition: the signer must be a registered
        -- guardian of this subject, AND the subject must still be a minor. The
        -- second half is why guardian access converts at eighteen rather than
        -- persisting -- it cannot even be rewritten once majority arrives.
        CREATE TRIGGER IF NOT EXISTS trg_grants_guardian_authority_ins
        BEFORE INSERT ON grants
        WHEN new.state = 'sealed'
         AND new.granted_via = 'guardian'
         AND NOT (EXISTS (SELECT 1 FROM guardianships g
                          WHERE g.subject_id = new.subject_id
                            AND g.guardian_id = new.sealed_by)
                  AND EXISTS (SELECT 1 FROM people p
                              WHERE p.person_id = new.subject_id
                                AND date('now') < date(p.birthdate, '+{majority} years')))
        BEGIN
            SELECT RAISE(ABORT,
                'guardian consent requires a registered guardian of a subject who is still a minor');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_grants_guardian_authority_upd
        BEFORE UPDATE ON grants
        WHEN new.state = 'sealed'
         AND new.granted_via = 'guardian'
         AND NOT (EXISTS (SELECT 1 FROM guardianships g
                          WHERE g.subject_id = new.subject_id
                            AND g.guardian_id = new.sealed_by)
                  AND EXISTS (SELECT 1 FROM people p
                              WHERE p.person_id = new.subject_id
                                AND date('now') < date(p.birthdate, '+{majority} years')))
        BEGIN
            SELECT RAISE(ABORT,
                'guardian consent requires a registered guardian of a subject who is still a minor');
        END;

        -- ── consent is never obtained by the person who benefits from it ────
        -- A section leader asking their own squad is coercion with extra steps,
        -- and so is a section leader signing the form. The one carve-out is a
        -- registered guardian, whose access to their own minor's record is the
        -- relationship rather than an abuse of one -- and which expires above.
        CREATE TRIGGER IF NOT EXISTS trg_grants_no_self_dealing_ins
        BEFORE INSERT ON grants
        WHEN (new.sealed_by = new.grantee_id OR new.requested_by = new.grantee_id)
         AND NOT EXISTS (SELECT 1 FROM guardianships g
                         WHERE g.subject_id = new.subject_id
                           AND g.guardian_id = new.grantee_id)
        BEGIN
            SELECT RAISE(ABORT,
                'consent may not be requested or signed by the person who benefits from it');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_grants_no_self_dealing_upd
        BEFORE UPDATE ON grants
        WHEN (new.sealed_by = new.grantee_id OR new.requested_by = new.grantee_id)
         AND NOT EXISTS (SELECT 1 FROM guardianships g
                         WHERE g.subject_id = new.subject_id
                           AND g.guardian_id = new.grantee_id)
        BEGIN
            SELECT RAISE(ABORT,
                'consent may not be requested or signed by the person who benefits from it');
        END;
        """.format(lo=int(min(Band)), hi=int(max(Band)),
                   majority=int(MAJORITY_AGE)),
    ),
    (
        "003_minor_use_consent_is_a_guardians_to_give",
        """
        -- subject_consent's use-class consent (local_only, process_analysis,
        -- kb_promotion, person_inference) lands as opaque hash-chained JSON in
        -- consent_chain, which is exactly why it is worth having it in THIS
        -- database rather than in a sibling file: the same guardian rule the
        -- grants triggers enforce can be enforced over it, by joining the chain
        -- to the roster inside one engine. A JSONL file on disk could not.
        --
        -- Requires SQLite's JSON1 (default since 3.38; present in sqlite-wasm,
        -- which is what the browser host will run).
        CREATE TRIGGER IF NOT EXISTS trg_use_consent_minor_needs_guardian
        BEFORE INSERT ON consent_chain
        WHEN new.chain = 'consent'
         AND json_extract(new.row, '$.status') = 'granted'
         AND EXISTS (SELECT 1 FROM people p
                     WHERE p.person_id = json_extract(new.row, '$.subject_id')
                       AND date('now') < date(p.birthdate, '+{majority} years'))
         AND NOT EXISTS (SELECT 1 FROM guardianships g
                         WHERE g.subject_id = json_extract(new.row, '$.subject_id')
                           AND g.guardian_id = json_extract(new.row, '$.granted_by'))
        BEGIN
            SELECT RAISE(ABORT,
                'a minor does not consent for themselves: a registered guardian must grant this use');
        END;
        """.format(majority=int(MAJORITY_AGE)),
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
