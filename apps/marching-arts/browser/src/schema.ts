/*
 * Copyright 2026 The marching-arts Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * The migrations, carrying the columns that cannot be added later.
 * Port of marching_arts/schema.py.
 *
 * `band` and `source` are on the fact table from migration 001. Both can be
 * added to a schema afterwards; neither can be added to data already written
 * without them. A retrofit leaves you choosing a default for a million rows, and
 * whatever you choose is wrong for some of them.
 *
 * The CHECK constraints are the mechanism. An empty source is rejected by SQLite
 * itself, so a caller cannot forget to supply one and no application-layer
 * discipline is required to keep the guarantee true. That holds identically in
 * WASM: it is the same C library, and the constraint travels with the file.
 *
 * Migrations 002, 003 and 004 are P2, and they extend the same idea from
 * constraints to triggers, because the rules P2 has to keep are about *pairs* of
 * tables and a `CHECK` cannot see past its own row:
 *
 *   - a minor's grant must be signed by a guardian who is registered as one, and
 *     guardian authority stops at the age of majority — two tables, three rules;
 *   - consent may not be requested or signed by the person who benefits from it,
 *     with a carve-out for a registered guardian of the subject;
 *   - the same guardian rule over subject-consent's own hash-chained consent
 *     log, which 004 re-states so it survives the log being partitioned per
 *     subject as `consent/<subject_hash>`.
 *
 * Each is a `RAISE(ABORT)`. Not a validator a caller can forget to call: a code
 * path that has never heard of these rules still cannot break them, and that is
 * as true of this port as of the Python, because the rule is in the database
 * rather than in either implementation.
 *
 * **The `subject_consent` core itself is Python-only and stays that way.** What
 * is ported here is the schema those tables live in, so a browser-created
 * database is the same database, byte for byte, as a Python-created one. The
 * resolver reads `grants`; it never walks the chain.
 *
 * The DDL text is byte-compared against schema.py by the differential suite. If
 * you reformat it, the suite fails, which is the intended outcome — the two
 * implementations must produce the same database, not merely similar ones. The
 * odd double spaces and the `--` comment art are Python's, reproduced on
 * purpose. The only edits are the interpolations (`${BAND_MIN}`, `${BAND_MAX}`,
 * `${MAJORITY_AGE}`, standing where Python's `.format()` fields stood) and the
 * backslash-escaped backticks that a template literal requires; neither changes
 * a byte of the resulting string.
 */

import { BAND_MAX, BAND_MIN } from './bands.js';
import type { Connection } from './connection.js';
import { MAJORITY_AGE } from './policy.js';

const MIGRATION_001 = `
        CREATE TABLE IF NOT EXISTS facts (
            id          INTEGER PRIMARY KEY,
            subject_id  TEXT    NOT NULL,
            band        INTEGER NOT NULL
                        CHECK (band BETWEEN ${BAND_MIN} AND ${BAND_MAX}),
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
                        CHECK (band BETWEEN ${BAND_MIN} AND ${BAND_MAX}),
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
        `;

const MIGRATION_002 = `
        -- ── who is a minor, and who may consent for them ────────────────────
        -- A birthdate rather than an is_minor flag. A flag is true until
        -- somebody remembers to run the job that clears it; a birthdate is
        -- true continuously, and "still a minor" is then a fact the predicate
        -- can evaluate on every read with nothing scheduled.
        CREATE TABLE IF NOT EXISTS people (
            person_id  TEXT PRIMARY KEY,
            -- Both halves are needed, and the order they are written in is not
            -- the interesting part -- the NULL is. \`date('not-a-date')\` is
            -- NULL, \`birthdate = NULL\` is NULL, and a CHECK that evaluates to
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
                        CHECK (band BETWEEN ${BAND_MIN} AND ${BAND_MAX}),
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
                       AND date('now') < date(p.birthdate, '+${MAJORITY_AGE} years'))
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
                       AND date('now') < date(p.birthdate, '+${MAJORITY_AGE} years'))
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
                                AND date('now') < date(p.birthdate, '+${MAJORITY_AGE} years')))
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
                                AND date('now') < date(p.birthdate, '+${MAJORITY_AGE} years')))
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
        `;

const MIGRATION_003 = `
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
                       AND date('now') < date(p.birthdate, '+${MAJORITY_AGE} years'))
         AND NOT EXISTS (SELECT 1 FROM guardianships g
                         WHERE g.subject_id = json_extract(new.row, '$.subject_id')
                           AND g.guardian_id = json_extract(new.row, '$.granted_by'))
        BEGIN
            SELECT RAISE(ABORT,
                'a minor does not consent for themselves: a registered guardian must grant this use');
        END;
        `;

const MIGRATION_004 = `
        -- The consent core addresses ONE global chain holding every subject's
        -- transitions interleaved. Unremarkable until someone asks to be
        -- forgotten: their rows are links in a chain the whole corps depends on,
        -- so removing them either breaks consent for everybody or cannot be done
        -- at all. Neither is an answer you can give a guardian. The backend now
        -- partitions at rest as \`consent/<subject_hash>\`; this makes the schema
        -- agree.
        --
        -- The bug this fixes is the partitioning's own: 003's guardian rule
        -- matched \`new.chain = 'consent'\` EXACTLY, so the moment the chain name
        -- gained a suffix the rule stopped firing and a minor could consent for
        -- themselves with nothing raised. It was caught by the test that exists
        -- for it, which is the only reason this comment is not an incident note.
        --
        -- The replacement matches the partitions AND the bare name. Keeping the
        -- bare name matters: a writer reaching past this module straight to SQL
        -- could otherwise insert under the old chain name and dodge the rule.
        DROP TRIGGER IF EXISTS trg_use_consent_minor_needs_guardian;

        CREATE TRIGGER trg_use_consent_minor_needs_guardian
        BEFORE INSERT ON consent_chain
        WHEN (new.chain = 'consent' OR new.chain LIKE 'consent/%')
         AND json_extract(new.row, '$.status') = 'granted'
         AND EXISTS (SELECT 1 FROM people p
                     WHERE p.person_id = json_extract(new.row, '$.subject_id')
                       AND date('now') < date(p.birthdate, '+${MAJORITY_AGE} years'))
         AND NOT EXISTS (SELECT 1 FROM guardianships g
                         WHERE g.subject_id = json_extract(new.row, '$.subject_id')
                           AND g.guardian_id = json_extract(new.row, '$.granted_by'))
        BEGIN
            SELECT RAISE(ABORT,
                'a minor does not consent for themselves: a registered guardian must grant this use');
        END;

        -- NOT ENFORCED HERE, and the gap is deliberate rather than overlooked:
        -- that a row lands in the partition naming its own subject cannot be a
        -- trigger, because stock SQLite has no SHA-256 and the partition key is
        -- one. \`SqliteConsentBackend.append_row\` checks it instead, which is a
        -- weaker guarantee than every other rule in this schema -- those hold
        -- against a writer who bypasses the module, and this one does not.
        -- Recorded so the asymmetry is visible rather than assumed away.
        `;

/**
 * Migration 005 — why the software refuses what it refuses, shipped in the box.
 *
 * Port of marching_arts/schema.py MIGRATIONS[4]. Emitted mechanically, not
 * retyped: the constants tier compares this string to the Python byte for byte,
 * including the whitespace artefacts of Python's implicit concatenation. The only
 * transformation is escaping the backticks a template literal requires.
 */
const MIGRATION_005 = `
        -- WHY THE SOFTWARE REFUSES WHAT IT REFUSES, shipped in the box.
        --
        -- A director asks why they cannot see a member's health record. A
        -- guardian asks why a declined grant renders as nothing rather than as
        -- a greyed row. A maintainer eighteen months from now asks why the
        -- consent chain is partitioned per subject. Today each of those is a
        -- support conversation, and the answer lives in a commit message or in
        -- somebody's head.
        --
        -- This table is the answer, on the same connection as the data it
        -- explains, so a corps that backed up one file backed up the reasoning
        -- with it. It is deliberately NOT a separate store: this app is
        -- stdlib-only and import-pure (tests/test_no_egress.py, and
        -- test_import_is_stdlib_only), so it cannot take a runtime dependency
        -- on anything that would host one -- and the browser half has no such
        -- host available at all.
        --
        -- THE GATE IS DIFFERENT FROM THE ONE ON \`facts\`, AND THE DIFFERENCE IS
        -- THE POINT. A row in \`facts\` is about a PERSON, so it is gated by the
        -- authorization predicate. A row here is about the SOFTWARE, so it is
        -- gated by whether a named human has said it may leave the building.
        -- Two tables, two gates, and no code path that confuses them.
        --
        -- \`publication\` defaults to 'draft', so a record that nobody has
        -- classified cannot ship. That is the same fail-closed direction as an
        -- empty allow set compiling to 0 rather than 1.
        --
        --   draft    -- written, not reviewed. The default. Never packaged.
        --   internal -- true and correct, and not for a customer. Competitive
        --               assessments of other vendors live here; so does
        --               anything whose subject is a live defect.
        --   shipped  -- a named human sealed it for the box.
        --
        -- The seal requirement is \`grants\`' own rule pointed at a different
        -- noun: a sealed grant nobody signed is refused, and so is a shipped
        -- rationale nobody signed. Machine-written text stays draft forever
        -- unless a person puts their name to it.
        CREATE TABLE IF NOT EXISTS rationale (
            id          INTEGER PRIMARY KEY,
            -- Stable slug, so a UI can deep-link an answer and a test can
            -- assert a specific one is present. Also the join key to the SOIL
            -- record this was distilled from, where one exists.
            topic       TEXT    NOT NULL UNIQUE
                        CHECK (length(trim(topic)) > 0),
            -- The question in the words somebody would actually ask it.
            question    TEXT    NOT NULL
                        CHECK (length(trim(question)) > 0),
            answer      TEXT    NOT NULL
                        CHECK (length(trim(answer)) > 0),
            -- The mechanism, named. Not "we don't share health data" but the
            -- migration, trigger or test that makes it so. An answer with no
            -- mechanism is a promise, and this project does not ship those.
            mechanism   TEXT,
            -- Same rule as every fact row: provenance is not optional.
            source      TEXT    NOT NULL
                        CHECK (length(trim(source)) > 0),
            publication TEXT    NOT NULL DEFAULT 'draft'
                        CHECK (publication IN ('draft', 'internal', 'shipped')),
            sealed_by   TEXT,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            CHECK (publication != 'shipped' OR (sealed_by IS NOT NULL
                                                AND length(trim(sealed_by)) > 0))
        );

        CREATE INDEX IF NOT EXISTS ix_rationale_publication
            ON rationale(publication, topic);

        -- A shipped record must name its mechanism. An internal note may be
        -- prose; the thing that goes to a customer may not be, because "there
        -- is no code path that transmits it" is checkable and "we take privacy
        -- seriously" is not. This is a trigger rather than a CHECK so the
        -- message can say why.
        CREATE TRIGGER IF NOT EXISTS trg_rationale_shipped_names_a_mechanism
        BEFORE INSERT ON rationale
        WHEN new.publication = 'shipped'
         AND (new.mechanism IS NULL OR length(trim(new.mechanism)) = 0)
        BEGIN
            SELECT RAISE(ABORT,
                'a shipped rationale must name its mechanism: a guarantee with no mechanism is a wish');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_rationale_shipped_names_a_mechanism_upd
        BEFORE UPDATE ON rationale
        WHEN new.publication = 'shipped'
         AND (new.mechanism IS NULL OR length(trim(new.mechanism)) = 0)
        BEGIN
            SELECT RAISE(ABORT,
                'a shipped rationale must name its mechanism: a guarantee with no mechanism is a wish');
        END;
        `;

/**
 * Migration 006 — who is asking, and the proof that they are.
 *
 * Port of marching_arts/schema.py MIGRATIONS[5]. Emitted mechanically, not
 * retyped, for the same reason 005 was: the constants tier compares this string
 * to the Python byte for byte, whitespace artefacts included. The only
 * transformation is escaping the backticks a template literal requires.
 *
 * **The DDL is ported; the gate is not, yet.** `marching_arts/auth.py` verifies a
 * principal's proof inside `Store.predicate`, and this port has no equivalent —
 * so a browser tab reading an ARMED database resolves unproven principals that
 * the Python would refuse. That asymmetry is deliberate for exactly one bite and
 * is asserted by `test/gate.mjs` rather than left to be discovered: the schema
 * has to land first so a browser-created file is the same file as a
 * Python-created one, and the verifier needs a decision this port has not made —
 * WebCrypto's HMAC is async, so verifying inside `predicate()` makes the whole
 * read path async. Recorded here because an implementation that silently enforces
 * less than its twin is the exact failure this differential exists to catch.
 */
const MIGRATION_006 = `
        -- WHO IS ASKING, AND THE PROOF THAT THEY ARE.
        --
        -- Until this migration, \`Principal("delacroix")\` was an unverified
        -- string. The predicate compiled from it was correct, per-record and
        -- mutation-tested, and a perfect predicate over an unauthenticated
        -- principal is theatre: anything that can construct a Principal can
        -- construct any Principal. marching_arts/auth.py is the mechanism; this
        -- is where its state lives.
        --
        -- ON THE SAME CONNECTION as the grants, the chain and the roster, for
        -- the reason every other table here is: a corps that backed up one file
        -- backed up its logins with it, or backed up none of them. A credential
        -- store restorable out of step with the grants it gates is one that will
        -- eventually admit somebody who was removed.
        --
        -- WHAT THIS DOES NOT DO. It does not make the file confidential. Anyone
        -- holding it opens it with sqlite3 and reads every row, with no
        -- credential and no proof. These tables gate the application's
        -- RESOLVER; they do not gate the FILE. Encryption at rest is a separate
        -- mechanism needing a cipher that exists nowhere in reach -- P3's
        -- stolen-device gate in docs/BUILD_PLAN.md. Recorded here because a
        -- table named \`credentials\` invites the stronger reading.
        --
        -- NO SIGNING KEY IS STORED. The HMAC key that makes a proof unforgeable
        -- is generated per process and held in memory only, so there is nothing
        -- at rest to steal and a token minted by one process is meaningless in
        -- another. That is why this migration has no \`secrets\` table, and the
        -- absence is the design rather than an omission.
        CREATE TABLE IF NOT EXISTS credentials (
            -- PRIMARY KEY, so a person cannot acquire a SECOND credential
            -- alongside their first. Rotation is an update that
            -- Authenticator.enroll refuses without proof of the old secret -- a
            -- rule that module holds and this schema cannot, because verifying
            -- PBKDF2 is not something stock SQLite can do inside a trigger.
            -- Same asymmetry migration 004 records about its partition check,
            -- written down for the same reason: it is weaker than every other
            -- rule here and pretending otherwise is how it gets relied on.
            person_id  TEXT PRIMARY KEY
                       CHECK (length(trim(person_id)) > 0),
            -- The derivation, named in the row rather than assumed by whoever
            -- reads it next. A future migration adds a second KDF by name and
            -- the rows already on file keep working; a schema that left this
            -- implicit would have to choose a default for every existing
            -- credential, and whatever it chose would be wrong for some.
            kdf        TEXT NOT NULL
                       CHECK (kdf IN ('pbkdf2_hmac_sha256')),
            -- Stored per row, so the cost can be raised for new enrolments
            -- without invalidating the ones already here.
            iterations INTEGER NOT NULL CHECK (iterations >= 100000),
            salt       BLOB NOT NULL CHECK (length(salt) >= 16),
            verifier   BLOB NOT NULL CHECK (length(verifier) >= 32),
            source     TEXT NOT NULL CHECK (length(trim(source)) > 0),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- ── the arming latch, and why it is its own table ───────────────────
        -- Whether proofs are required is derived from the data, not from a
        -- constructor flag: a flag is a second copy of the truth and it is wrong
        -- the first time somebody opens the file without setting it, which is
        -- the objection migration 002 raised against an \`is_minor\` column.
        --
        -- The obvious phrasing is "require proofs if any credential exists",
        -- and it is WRONG IN THE DANGEROUS DIRECTION -- deleting the credential
        -- rows would reopen the database to unproven principals, making
        -- \`DELETE FROM credentials\` a privilege escalation. So arming is
        -- recorded here instead, and it is one-way. Delete every credential
        -- from an armed database and nobody can authenticate at all. That is
        -- the correct way to fail.
        CREATE TABLE IF NOT EXISTS auth_policy (
            id       INTEGER PRIMARY KEY CHECK (id = 1),
            required INTEGER NOT NULL CHECK (required IN (0, 1))
        );

        -- A latch, in SQL. Not a convention and not a comment on the update
        -- statement: no writer disarms this, including one that has never heard
        -- of auth.py.
        CREATE TRIGGER IF NOT EXISTS trg_auth_policy_never_disarms
        BEFORE UPDATE ON auth_policy
        WHEN old.required = 1 AND new.required = 0
        BEGIN
            SELECT RAISE(ABORT,
                'authentication cannot be turned off once it is on: delete the credentials instead and lock everyone out');
        END;

        -- Deleting the latch row is disarming it by another name, so the same
        -- refusal covers it. The recovery path for a corps that genuinely wants
        -- an open database is a new file, which is also the only honest one: an
        -- armed database holds records written on the understanding that reads
        -- were gated.
        CREATE TRIGGER IF NOT EXISTS trg_auth_policy_is_not_deletable
        BEFORE DELETE ON auth_policy
        WHEN old.required = 1
        BEGIN
            SELECT RAISE(ABORT,
                'authentication cannot be turned off once it is on: this row is a latch');
        END;
        `;

export const MIGRATIONS: readonly (readonly [string, string])[] = [
  ['001_facts_and_grants', MIGRATION_001],
  ['002_people_guardianship_and_consent_chain', MIGRATION_002],
  ['003_minor_use_consent_is_a_guardians_to_give', MIGRATION_003],
  ['004_consent_chain_is_per_subject', MIGRATION_004],
  ['005_rationale', MIGRATION_005],
  ['006_credentials_and_the_arming_latch', MIGRATION_006],
];

/** Run every migration not yet applied. Returns the names that ran. */
export async function apply(conn: Connection): Promise<string[]> {
  await conn.run(
    'CREATE TABLE IF NOT EXISTS schema_migrations (' +
      ' name TEXT PRIMARY KEY,' +
      ' applied_at TEXT NOT NULL DEFAULT (datetime(\'now\')))',
  );
  const done = new Set(
    (await conn.all('SELECT name FROM schema_migrations')).map((r) => String(r[0])),
  );
  const ran: string[] = [];
  for (const [name, sql] of MIGRATIONS) {
    if (done.has(name)) continue;
    await conn.exec(sql);
    await conn.run('INSERT INTO schema_migrations(name) VALUES (:name)', { name });
    ran.push(name);
  }
  await conn.commit();
  return ran;
}
