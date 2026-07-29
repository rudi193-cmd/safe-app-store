/*
 * Copyright 2026 The marching-arts Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * The first migration, carrying the two columns that cannot be added later.
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
 * The DDL text is byte-compared against schema.py by the differential suite. If
 * you reformat it, the suite fails, which is the intended outcome — the two
 * implementations must produce the same database, not merely similar ones.
 */

import { BAND_MAX, BAND_MIN } from './bands.js';
import type { Connection } from './connection.js';

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

export const MIGRATIONS: readonly (readonly [string, string])[] = [
  ['001_facts_and_grants', MIGRATION_001],
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
