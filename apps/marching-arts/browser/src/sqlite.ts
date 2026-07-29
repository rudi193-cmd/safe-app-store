/*
 * Copyright 2026 The marching-arts Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * `Connection` over `sqlite3.oo1.DB` from `@sqlite.org/sqlite-wasm`.
 *
 * One thing here is a behaviour fix rather than a transcription. Python's
 * `sqlite3` binds a dict of named parameters by looking up only the names the
 * statement declares; extra keys are ignored. `oo1`'s `exec({bind})` throws
 * `Invalid bind() parameter name` on an extra key. That difference is not
 * cosmetic — `Store.visible` always adds `viewer` for the projection, and a
 * caller-supplied filter may legitimately carry parameters a *different* branch
 * of the predicate uses. So binding here walks the statement's own declared
 * parameter list (`sqlite3_bind_parameter_name`) and takes what it needs,
 * raising only on a name the statement wants and the caller did not supply.
 *
 * That makes the two implementations agree on both halves: extra keys are
 * tolerated, missing ones are an error.
 */

import { assertBindable, type Connection, type Row, type RunResult } from './connection.js';
import type { Params } from './rules.js';

/* eslint-disable @typescript-eslint/no-explicit-any */
type Sqlite3 = any;
type Oo1Db = any;
type Oo1Stmt = any;

/** Names the prepared statement actually declares, without their sigils. */
function declaredParams(sqlite3: Sqlite3, stmt: Oo1Stmt): { index: number; key: string }[] {
  const capi = sqlite3.capi;
  const n = capi.sqlite3_bind_parameter_count(stmt.pointer);
  const out: { index: number; key: string }[] = [];
  for (let i = 1; i <= n; i++) {
    const name = capi.sqlite3_bind_parameter_name(stmt.pointer, i);
    if (!name) throw new Error(`statement uses positional parameter ${i}; named only`);
    out.push({ index: i, key: name.slice(1) });
  }
  return out;
}

function bindDeclared(sqlite3: Sqlite3, stmt: Oo1Stmt, params: Params): void {
  for (const { index, key } of declaredParams(sqlite3, stmt)) {
    if (!Object.prototype.hasOwnProperty.call(params, key)) {
      throw new Error(`missing bind parameter :${key}`);
    }
    stmt.bind(index, params[key]);
  }
}

export class Oo1Connection implements Connection {
  readonly sqlite3: Sqlite3;
  readonly db: Oo1Db;

  constructor(sqlite3: Sqlite3, db: Oo1Db) {
    this.sqlite3 = sqlite3;
    this.db = db;
  }

  private prepare(sql: string, params?: Params): Oo1Stmt {
    const stmt = this.db.prepare(sql);
    try {
      bindDeclared(this.sqlite3, stmt, assertBindable(params));
    } catch (error) {
      stmt.finalize();
      throw error;
    }
    return stmt;
  }

  async all(sql: string, params?: Params): Promise<Row[]> {
    const stmt = this.prepare(sql, params);
    try {
      const rows: Row[] = [];
      while (stmt.step()) rows.push(stmt.get([]) as Row);
      return rows;
    } finally {
      stmt.finalize();
    }
  }

  async get(sql: string, params?: Params): Promise<Row | undefined> {
    const stmt = this.prepare(sql, params);
    try {
      return stmt.step() ? (stmt.get([]) as Row) : undefined;
    } finally {
      stmt.finalize();
    }
  }

  async run(sql: string, params?: Params): Promise<RunResult> {
    const stmt = this.prepare(sql, params);
    try {
      while (stmt.step()) {
        /* drain: a RETURNING clause or a pragma may produce rows */
      }
    } finally {
      stmt.finalize();
    }
    return {
      lastInsertRowid: Number(this.sqlite3.capi.sqlite3_last_insert_rowid(this.db.pointer)),
      changes: Number(this.db.changes()),
    };
  }

  async exec(sql: string): Promise<void> {
    this.db.exec(sql);
  }

  private get autocommit(): boolean {
    return this.sqlite3.capi.sqlite3_get_autocommit(this.db.pointer) !== 0;
  }

  async begin(): Promise<void> {
    if (this.autocommit) this.db.exec('BEGIN');
  }

  async commit(): Promise<void> {
    if (!this.autocommit) this.db.exec('COMMIT');
  }

  async rollback(): Promise<void> {
    if (!this.autocommit) this.db.exec('ROLLBACK');
  }

  async close(): Promise<void> {
    this.db.close();
  }
}

/**
 * Open an in-memory database. This is what the differential suite runs on under
 * Node, because Node has no OPFS and therefore no `opfs-sahpool` VFS — see
 * `open.ts` for the browser ladder and README.md for what that costs.
 */
export async function openMemory(sqlite3: Sqlite3, name = ':memory:'): Promise<Oo1Connection> {
  const db = new sqlite3.oo1.DB(name, 'c');
  db.exec('PRAGMA foreign_keys = ON');
  return new Oo1Connection(sqlite3, db);
}
