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

import { GrantVia, Policy, type Principal } from './policy.js';
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

/**
 * One answer to "why does the software do that", and its provenance.
 *
 * `mechanism` is the load-bearing field. A shipped row must name one, by
 * trigger — the migration, constraint or test that makes the answer true.
 * Without it the row is a promise, and this project does not ship promises.
 */
export interface Rationale {
  readonly topic: string;
  readonly question: string;
  readonly answer: string;
  readonly mechanism: string | null;
  readonly source: string;
  readonly publication: string;
  readonly sealedBy: string | null;
}

export type Publication = 'draft' | 'internal' | 'shipped';

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

  /**
   * Insert or replace a grant. A sealed grant without a signer is refused.
   *
   * Four more refusals arrive from the schema rather than from here, which is
   * why this method stays this short: a minor's grant that is not
   * guardian-derived, a guardian-derived grant whose signer is not a registered
   * guardian, a guardian-derived grant on a subject who has reached majority,
   * and any grant the beneficiary signed or requested. Each is a trigger in
   * migration 002. No code path avoids them, including one written later by
   * somebody who has not read this comment — and including one written in
   * JavaScript, because the rule is in the database and not in either port.
   *
   * `commit: false` leaves the write open so a caller can land the grant and its
   * disclosure row in one transaction.
   */
  async recordGrant(
    subjectId: string,
    granteeId: string,
    band: number,
    state: string,
    source: string,
    extra: {
      sealedBy?: string | null;
      grantedVia?: string;
      requestedBy?: string | null;
      commit?: boolean;
    } = {},
  ): Promise<number> {
    const result = await this.connection.run(
      'INSERT INTO grants(subject_id, grantee_id, band, state, sealed_by,' +
        '                   granted_via, requested_by, source)' +
        ' VALUES (:subject_id, :grantee_id, :band, :state, :sealed_by,' +
        '         :granted_via, :requested_by, :source)' +
        ' ON CONFLICT(subject_id, grantee_id) DO UPDATE SET' +
        '   band = excluded.band, state = excluded.state,' +
        '   sealed_by = excluded.sealed_by,' +
        '   granted_via = excluded.granted_via,' +
        '   requested_by = excluded.requested_by,' +
        '   source = excluded.source',
      {
        subject_id: subjectId,
        grantee_id: granteeId,
        band: Math.trunc(band),
        state,
        sealed_by: extra.sealedBy ?? null,
        granted_via: extra.grantedVia ?? GrantVia.MEMBER,
        requested_by: extra.requestedBy ?? null,
        source,
      },
    );
    if (extra.commit !== false) await this.connection.commit();
    return result.lastInsertRowid;
  }

  /**
   * Silent revocation. The grantee is not told, and nothing notifies them.
   *
   * A delete rather than a state change, so no residue of the former grant is
   * readable. The disclosure ledger, which lives beside this store, is where the
   * history belongs — not in the table the resolver reads on every query.
   *
   * Resolves to `undefined` on purpose, and resolves to it whether or not a
   * grant was there to delete. A rowcount would be a side channel: a grantee who
   * could call this and read "1" would learn they had access, which is exactly
   * the fact a silent revocation withholds.
   */
  async revoke(
    subjectId: string,
    granteeId: string,
    extra: { commit?: boolean } = {},
  ): Promise<void> {
    await this.connection.run(
      'DELETE FROM grants WHERE subject_id = :subject_id AND grantee_id = :grantee_id',
      { subject_id: subjectId, grantee_id: granteeId },
    );
    if (extra.commit !== false) await this.connection.commit();
  }

  // ── people and guardianship ──────────────────────────────────────────────

  /**
   * Register a person's birthdate. Rejected if it is not a real date.
   *
   * A birthdate and not an `is_minor` flag, because the flag is only true until
   * the job that clears it fails to run, and the failure is silent and in the
   * wrong direction.
   */
  async recordPerson(personId: string, birthdate: string, source: string): Promise<void> {
    await this.connection.run(
      'INSERT INTO people(person_id, birthdate, source)' +
        ' VALUES (:person_id, :birthdate, :source)' +
        ' ON CONFLICT(person_id) DO UPDATE SET' +
        '   birthdate = excluded.birthdate, source = excluded.source',
      { person_id: personId, birthdate, source },
    );
    await this.connection.commit();
  }

  /**
   * Register who may consent for a minor. The subject must exist first — a
   * guardianship over nobody is refused by the foreign key.
   */
  async recordGuardianship(
    guardianId: string,
    subjectId: string,
    relation: string,
    source: string,
  ): Promise<void> {
    await this.connection.run(
      'INSERT INTO guardianships(guardian_id, subject_id, relation, source)' +
        ' VALUES (:guardian_id, :subject_id, :relation, :source)' +
        ' ON CONFLICT(guardian_id, subject_id) DO UPDATE SET' +
        '   relation = excluded.relation, source = excluded.source',
      { guardian_id: guardianId, subject_id: subjectId, relation, source },
    );
    await this.connection.commit();
  }

  /**
   * True only for a person on file who is under the age of majority.
   *
   * A person with no birthdate on file is **not** a minor here. That is the
   * fail-closed direction for this particular question: treating an unknown as a
   * minor would let anybody claim guardian authority over a subject the platform
   * knows nothing about.
   *
   * Phrased by `Policy.stillAMinor`, the same expression the resolver's grant
   * lookup embeds, so this answer and the predicate cannot disagree.
   */
  async isMinor(personId: string): Promise<boolean> {
    const row = await this.connection.get(`SELECT ${this.policy.stillAMinor(':who')}`, {
      who: personId,
    });
    return Boolean(row && Number(row[0]));
  }

  async guardiansOf(subjectId: string): Promise<string[]> {
    const rows = await this.connection.all(
      'SELECT guardian_id FROM guardianships WHERE subject_id = :subject_id' +
        ' ORDER BY guardian_id',
      { subject_id: subjectId },
    );
    return rows.map((r) => String(r[0]));
  }

  // ── rationale: why the software refuses what it refuses ──────────────────
  //
  // Not gated by the authorization predicate, and that is the design rather
  // than an omission. A `facts` row is about a PERSON and needs a `WHERE`
  // clause. A `rationale` row is about the SOFTWARE and needs a human to have
  // said it may leave the building. Two tables, two gates, no path that
  // confuses them — see migration 005.

  /** Write a rationale. Defaults to `draft`, which never ships. */
  async recordRationale(
    topic: string,
    question: string,
    answer: string,
    source: string,
    opts: {
      mechanism?: string | null;
      publication?: Publication;
      sealedBy?: string | null;
    } = {},
  ): Promise<void> {
    await this.connection.run(
      'INSERT INTO rationale(topic, question, answer, mechanism, source,' +
        ' publication, sealed_by)' +
        ' VALUES (:topic, :question, :answer, :mechanism, :source,' +
        ' :publication, :sealed_by)',
      {
        topic,
        question,
        answer,
        mechanism: opts.mechanism ?? null,
        source,
        publication: opts.publication ?? 'draft',
        sealed_by: opts.sealedBy ?? null,
      },
    );
  }

  /**
   * Mark a rationale shippable. Only a human does this.
   *
   * Deliberately a separate call from writing one: the machine that drafts an
   * answer is not the thing that decides a customer may read it.
   */
  async sealRationale(topic: string, sealedBy: string): Promise<void> {
    if (!sealedBy || !sealedBy.trim()) {
      throw new Error("a seal needs a name: 'shipped' with no signer is refused");
    }
    await this.connection.run(
      "UPDATE rationale SET publication = 'shipped', sealed_by = :sealed_by" +
        ' WHERE topic = :topic',
      { sealed_by: sealedBy, topic },
    );
  }

  /**
   * Rationale rows at one publication level. Defaults to what ships.
   *
   * The default is the point: a caller that forgets to say what it wants gets
   * the shippable set, not everything.
   */
  async rationale(publication: Publication = 'shipped'): Promise<Rationale[]> {
    if (publication !== 'draft' && publication !== 'internal' &&
        publication !== 'shipped') {
      throw new Error(`unknown publication level ${String(publication)}`);
    }
    const rows = await this.connection.all(
      'SELECT topic, question, answer, mechanism, source, publication,' +
        ' sealed_by FROM rationale WHERE publication = :publication' +
        ' ORDER BY topic',
      { publication },
    );
    return rows.map((r) => ({
      topic: String(r[0]),
      question: String(r[1]),
      answer: String(r[2]),
      mechanism: r[3] === null ? null : String(r[3]),
      source: String(r[4]),
      publication: String(r[5]),
      sealedBy: r[6] === null ? null : String(r[6]),
    }));
  }
}
