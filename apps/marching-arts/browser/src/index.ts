/*
 * Copyright 2026 The marching-arts Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * Public entry point for the browser half of P1.
 *
 *   import { connectToOwner, Store, principal } from '@marching-arts/browser';
 *
 *   const conn  = await connectToOwner(new URL('./worker.js', import.meta.url));
 *   const store = await Store.open(conn);
 *   const n     = await store.count(principal('leader'));   // COUNT(*) in SQL
 *
 * Note what the surface does *not* offer: no `rows()` that returns everything
 * for the caller to filter, no principal-free read, no way to obtain a
 * connection that has not been through `Store`. The predicate is not a
 * convenience the caller may opt into.
 */

export { Band, BAND_MAX, BAND_MIN, BAND_NAMES, DERIVE_AT, NEVER_SERVED, parseBand } from './bands.js';
export {
  ALLOW_ALL,
  DENY_ALL,
  Effect,
  compileRules,
  explain,
  formatSql,
  renderRule,
  rule,
  type Param,
  type Params,
  type Rule,
} from './rules.js';
export { GrantState, Policy, principal, type Principal } from './policy.js';
export { MIGRATIONS, apply as applyMigrations } from './schema.js';
export {
  assertBindable,
  inTransaction,
  isBindable,
  type Connection,
  type Row,
  type RunResult,
} from './connection.js';
export { Oo1Connection, openMemory } from './sqlite.js';
export { openDatabase, sqlite3, type OpenOptions, type OpenResult, type Vfs } from './open.js';
export { SORTABLE, SortColumnError, Store, type Fact, type ReadOptions } from './store.js';
export { RemoteConnection } from './owner/client.js';
export { handleRequest, serve, announce, type PortLike } from './owner/server.js';
export {
  PROTOCOL_VERSION,
  isNotice,
  type Notice,
  type Op,
  type Request,
  type Response,
} from './owner/protocol.js';
export {
  CHALLENGE_POLL_MS,
  OWNER_LOCK,
  acquireOwnership,
  locksAvailable,
  watchForChallengers,
  type Ownership,
} from './owner/election.js';

import { RemoteConnection } from './owner/client.js';
import type { PortLike } from './owner/server.js';

/**
 * Connect a tab to the SharedWorker that owns the database.
 *
 * Falls back to a dedicated worker where SharedWorker is missing (Chrome on
 * Android, some WebViews). In that case the Web Lock in `owner/election.ts` is
 * the only thing keeping the `opfs-sahpool` handles single-holder, and the
 * fallback is deliberately loud in the console rather than silent.
 */
export function connectToOwner(scriptUrl: string | URL): RemoteConnection {
  const url = String(scriptUrl);
  const g = globalThis as unknown as {
    SharedWorker?: new (u: string, o?: object) => { port: PortLike };
    Worker?: new (u: string, o?: object) => PortLike;
  };
  if (typeof g.SharedWorker === 'function') {
    const worker = new g.SharedWorker(url, { type: 'module', name: 'marching-arts-db' });
    return new RemoteConnection(worker.port);
  }
  if (typeof g.Worker === 'function') {
    console.warn(
      '[marching-arts] No SharedWorker in this browser; using a dedicated worker per tab. ' +
        'Single-owner is enforced by the Web Lock alone.',
    );
    return new RemoteConnection(new g.Worker(url, { type: 'module' }));
  }
  throw new Error('no worker support: the database cannot be opened in this context');
}
