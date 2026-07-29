/*
 * Copyright 2026 The marching-arts Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * The one seam between the resolver and whatever is actually holding the
 * database file.
 *
 * The Python store takes a `sqlite3.Connection`. The browser store cannot: the
 * database lives in a SharedWorker (so there is exactly one writer by
 * construction) and every call has to cross a MessagePort. So the store is
 * written against this async interface instead, and there are two
 * implementations:
 *
 *   `Oo1Connection`    — sqlite3.oo1.DB directly. Used inside the worker, and
 *                        used by the differential suite under Node.
 *   `RemoteConnection` — RPC over a MessagePort to the owner.
 *
 * There is exactly one Store implementation over both. A second Store would be
 * a second place for the predicate to be wrong.
 *
 * Note what is *not* here: no `query(rows)` helper that fetches and filters, no
 * `all()` variant that takes a callback the caller can use to post-process. The
 * interface offers `count()` nothing at all — counting is a `COUNT(*)` the store
 * writes, and the only way to get a number out of this interface is to ask
 * SQLite for one.
 */

import type { Param, Params } from './rules.js';

export type Row = readonly unknown[];

export interface RunResult {
  /** rowid of the last INSERT on this connection. */
  readonly lastInsertRowid: number;
  /** rows changed by the last statement. */
  readonly changes: number;
}

export interface Connection {
  /** Run one statement, returning all rows as positional arrays. */
  all(sql: string, params?: Params): Promise<Row[]>;
  /** Run one statement, returning the first row or undefined. */
  get(sql: string, params?: Params): Promise<Row | undefined>;
  /** Run one statement for effect. */
  run(sql: string, params?: Params): Promise<RunResult>;
  /** Run a multi-statement script (migrations). No parameters. */
  exec(sql: string): Promise<void>;
  /** Begin an explicit transaction, so a seal ledger can share it. */
  begin(): Promise<void>;
  /** Commit if a transaction is open; a no-op under autocommit. */
  commit(): Promise<void>;
  /** Roll back if a transaction is open; a no-op under autocommit. */
  rollback(): Promise<void>;
  close(): Promise<void>;
}

/**
 * Run `fn` inside one transaction, committing on success and rolling back on
 * any throw.
 *
 * UTETY's `SqliteBackend` is the worked example this exists for: append-row and
 * write-anchor must land in *one* transaction, because the filesystem backend's
 * two non-atomic writes wedge the hash chain on a crash.
 */
export async function inTransaction<T>(conn: Connection, fn: () => Promise<T>): Promise<T> {
  await conn.begin();
  try {
    const result = await fn();
    await conn.commit();
    return result;
  } catch (error) {
    await conn.rollback();
    throw error;
  }
}

/** Values that survive a structured clone across a MessagePort unchanged. */
export function isBindable(value: unknown): value is Param {
  return (
    value === null ||
    typeof value === 'string' ||
    typeof value === 'number' ||
    value instanceof Uint8Array
  );
}

export function assertBindable(params: Params | undefined): Params {
  if (!params) return {};
  for (const [key, value] of Object.entries(params)) {
    if (!isBindable(value)) {
      throw new TypeError(`parameter ${JSON.stringify(key)} is not a bindable value`);
    }
  }
  return params;
}
