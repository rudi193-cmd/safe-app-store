/*
 * Copyright 2026 The marching-arts Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * Authorized reads over the facts table. Port of marching_arts/store.py.
 * Every read goes through the compiled predicate — there is no second path.
 *
 * The gate this module exists to pass: **hidden rows must not leak through a
 * COUNT, a filter, a sort order, or an empty state.** Each of those is a real
 * leak and each fails differently:
 *
 *   count  — the classic, and the one a browser port is most likely to get
 *            wrong, because `rows.length` is right there and it is *correct*.
 *            It is also a fetch of every hidden row into the tab's heap before
 *            hiding them. `count()` below is a SQL `COUNT(*)` under the same
 *            predicate; there is no array to take the length of.
 *   filter — a caller-supplied WHERE is ANDed *inside* the authorization
 *            predicate, never ORed and never substituted. Narrowing a query can
 *            hide rows from yourself; it can never reveal one.
 *   sort   — ordering columns come from an allowlist, so a sort cannot smuggle
 *            a subquery, and LIMIT/OFFSET apply after the predicate, so page
 *            boundaries do not count what they do not show.
 *   empty  — a subject you may not see must be indistinguishable from a subject
 *            who does not exist. This is the one people forget, and the one
 *            that matters most: a distinguishable refusal turns opting out into
 *            the signal.
 *
 * Nothing in this module opens a socket, and nothing it imports could.
 */

import { Policy, type Principal } from './policy.js';
import { compileRules, type Params } from './rules.js';
import type { Connection } from './connection.js';
import * as schema from './schema.js';

/**
 * Columns a caller may sort by. An allowlist rather than an escape: quoting a
 * caller-supplied ORDER BY correctly is possible and is not worth doing when the
 * set of legitimate sorts is this small.
 */
export const SORTABLE: ReadonlySet<string> = new Set([
  'id',
  'subject_id',
  'band',
  'created_at',
]);

export interface Fact {
  readonly id: number;
  readonly subjectId: string;
  readonly band: number;
  readonly payload: string | null;
  readonly instruction: string | null;
  readonly source: string;
}

export interface ReadOptions {
  where?: string | null;
  params?: Params | null;
  orderBy?: string;
  descending?: boolean;
  limit?: number | null;
  offset?: number;
}

export class SortColumnError extends Error {
  constructor(orderBy: string) {
    super(
      `cannot sort by ${JSON.stringify(orderBy)}; allowed: ${[...SORTABLE].sort().join(', ')}`,
    );
    this.name = 'SortColumnError';
  }
}

function toFact(row: readonly unknown[]): Fact {
  return {
    id: Number(row[0]),
    subjectId: String(row[1]),
    band: Number(row[2]),
    payload: row[3] === null || row[3] === undefined ? null : String(row[3]),
    instruction: row[4] === null || row[4] === undefined ? null : String(row[4]),
    source: String(row[5]),
  };
}

export class Store {
  readonly connection: Connection;
  readonly policy: Policy;

  private constructor(conn: Connection, policy: Policy) {
    this.connection = conn;
    this.policy = policy;
  }

  /**
   * Open a store over `conn`, running any migration not yet applied.
   *
   * Async because migrations are, so there is no half-constructed Store to
   * observe. Pass the connection rather than a path: consent, seals and domain
   * data share one file and are backed up as a unit, and Nestor's `Storage`
   * protocol is satisfied by this same connection.
   */
  static async open(conn: Connection, policy?: Policy): Promise<Store> {
    await conn.run('PRAGMA foreign_keys = ON');
    const store = new Store(conn, policy ?? new Policy());
    await schema.apply(conn);
    return store;
  }

  // ── the predicate every read shares ──────────────────────────────────────

  /**
   * Compile `principal`'s rules, ANDed with an optional caller filter.
   *
   * The caller's filter is a further narrowing and is parenthesised so its
   * internal ORs cannot escape into the authorization predicate. There is no
   * argument that widens the result set; that is not an omission.
   */
  predicate(
    principal: Principal,
    extra?: string | null,
    extraParams?: Params | null,
  ): { sql: string; params: Params } {
    const compiled = compileRules(this.policy.rules(principal));
    let sql = compiled.sql;
    let params = compiled.params;
    if (extra) {
      sql = `(${sql}) AND (${extra})`;
      params = { ...params, ...(extraParams ?? {}) };
    }
    return { sql, params };
  }

  // ── reads ────────────────────────────────────────────────────────────────

  async visible(principal: Principal, options: ReadOptions = {}): Promise<Fact[]> {
    const orderBy = options.orderBy ?? 'id';
    if (!SORTABLE.has(orderBy)) throw new SortColumnError(orderBy);

    const { sql: predicate, params } = this.predicate(
      principal,
      options.where ?? null,
      options.params ?? null,
    );
    const bound: Params = { ...params };
    Object.assign(bound, this.policy.projectionParams(principal));

    let sql =
      'SELECT facts.id, facts.subject_id, facts.band,' +
      ` ${this.policy.projection(principal)} AS payload,` +
      ' facts.instruction, facts.source' +
      ` FROM facts WHERE ${predicate}` +
      ` ORDER BY facts.${orderBy} ${options.descending ? 'DESC' : 'ASC'}`;

    if (options.limit !== undefined && options.limit !== null) {
      sql += ' LIMIT :_limit OFFSET :_offset';
      bound._limit = Math.trunc(options.limit);
      bound._offset = Math.trunc(options.offset ?? 0);
    }

    return (await this.connection.all(sql, bound)).map(toFact);
  }

  /**
   * `COUNT(*)` under the authorization predicate.
   *
   * The count is computed by SQLite over rows this principal may see. It is
   * never the length of a fetched array, because that shape requires the hidden
   * rows to have been read first — and in a browser, to have been read into a
   * heap a devtools console can walk.
   */
  async count(
    principal: Principal,
    options: Pick<ReadOptions, 'where' | 'params'> = {},
  ): Promise<number> {
    const { sql: predicate, params } = this.predicate(
      principal,
      options.where ?? null,
      options.params ?? null,
    );
    const row = await this.connection.get(
      `SELECT COUNT(*) FROM facts WHERE ${predicate}`,
      params,
    );
    return Number(row ? row[0] : 0);
  }

  /**
   * Distinct subjects with at least one visible row.
   *
   * Subjects with nothing visible are absent from this list rather than present
   * and empty. An empty slot is a disclosure: it says a person exists and you
   * may not see them, which is most of what you wanted to know.
   */
  async subjects(principal: Principal): Promise<string[]> {
    const { sql: predicate, params } = this.predicate(principal);
    const rows = await this.connection.all(
      'SELECT DISTINCT facts.subject_id FROM facts' +
        ` WHERE ${predicate} ORDER BY facts.subject_id`,
      params,
    );
    return rows.map((r) => String(r[0]));
  }

  // ── writes ───────────────────────────────────────────────────────────────

  /** Insert a fact. Rejected by the schema if `source` is blank. */
  async recordFact(
    subjectId: string,
    band: number,
    source: string,
    extra: { payload?: string | null; instruction?: string | null } = {},
  ): Promise<number> {
    const result = await this.connection.run(
      'INSERT INTO facts(subject_id, band, payload, instruction, source)' +
        ' VALUES (:subject_id, :band, :payload, :instruction, :source)',
      {
        subject_id: subjectId,
        band: Math.trunc(band),
        payload: extra.payload ?? null,
        instruction: extra.instruction ?? null,
        source,
      },
    );
    await this.connection.commit();
    return result.lastInsertRowid;
  }

  /** Insert or replace a grant. A sealed grant without a signer is refused. */
  async recordGrant(
    subjectId: string,
    granteeId: string,
    band: number,
    state: string,
    source: string,
    extra: { sealedBy?: string | null } = {},
  ): Promise<number> {
    const result = await this.connection.run(
      'INSERT INTO grants(subject_id, grantee_id, band, state, sealed_by, source)' +
        ' VALUES (:subject_id, :grantee_id, :band, :state, :sealed_by, :source)' +
        ' ON CONFLICT(subject_id, grantee_id) DO UPDATE SET' +
        '   band = excluded.band, state = excluded.state,' +
        '   sealed_by = excluded.sealed_by, source = excluded.source',
      {
        subject_id: subjectId,
        grantee_id: granteeId,
        band: Math.trunc(band),
        state,
        sealed_by: extra.sealedBy ?? null,
        source,
      },
    );
    await this.connection.commit();
    return result.lastInsertRowid;
  }

  /**
   * Silent revocation. The grantee is not told, and nothing notifies them.
   *
   * A delete rather than a state change, so no residue of the former grant is
   * readable. The disclosure ledger, which lives beside this store, is where the
   * history belongs — not in the table the resolver reads on every query.
   */
  async revoke(subjectId: string, granteeId: string): Promise<void> {
    await this.connection.run(
      'DELETE FROM grants WHERE subject_id = :subject_id AND grantee_id = :grantee_id',
      { subject_id: subjectId, grantee_id: granteeId },
    );
    await this.connection.commit();
  }
}
