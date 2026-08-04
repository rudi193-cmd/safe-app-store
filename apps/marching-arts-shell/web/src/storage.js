/*
 * Copyright 2026 The marching-arts Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * The storage seam: an ordered ladder of backends, and a record of why each
 * rung was skipped.
 *
 * This is the shape kept from the quick-stupids skeleton, and only the shape.
 * That skeleton's ~630 lines of blob store were judged and discarded: it stored
 * one file per item per namespace, which leaves nowhere to put a WHERE clause
 * and therefore nowhere to put an authorization predicate. Filtering in JS after
 * fetching is the exact failure P1's gate exists to catch. Real storage here is
 * `@marching-arts/browser` — SQLite-WASM on OPFS, where the resolver compiles to
 * one SQL predicate. This module decides *which rung is available* and says so;
 * it does not store anything.
 *
 * Two rules it exists to enforce:
 *
 *   `durable` is a reported fact, never a silent downgrade. A tab that fell back
 *   to memory says so in the status bar rather than reporting itself durable.
 *
 *   No memoised module-level promise. The skeleton cached one `opening` promise
 *   forever, which is survivable for OPFS's async API and fatal for
 *   opfs-sahpool's exclusive handles — one session gets one backend, with no
 *   handoff and no way to release. Each probe here is independent.
 */

/** Ordered best-first. The first rung whose `available()` holds is the answer. */
export const LADDER = Object.freeze([
  Object.freeze({
    name: 'opfs-sahpool',
    durable: true,
    why: 'synchronous access handles — the only rung SQLite-WASM can use for a real database',
    available: () =>
      typeof navigator !== 'undefined' &&
      typeof navigator.storage?.getDirectory === 'function' &&
      typeof FileSystemFileHandle !== 'undefined' &&
      'createSyncAccessHandle' in FileSystemFileHandle.prototype,
  }),
  Object.freeze({
    name: 'indexeddb',
    durable: true,
    why: 'durable, but every read crosses an async boundary, so a query cannot stay in SQL',
    available: () => typeof indexedDB !== 'undefined',
  }),
  Object.freeze({
    name: 'memory',
    durable: false,
    why: 'always available, and loses everything on reload — reported, never assumed',
    available: () => true,
  }),
]);

/**
 * @returns {{name: string, durable: boolean, notes: string[]}}
 * `notes` carries one line per rung that was skipped and why. An absent rung is
 * a recorded value, not a missing row.
 */
export function probeStorage(ladder = LADDER) {
  const notes = [];
  for (const rung of ladder) {
    let ok = false;
    let failure = null;
    try {
      ok = rung.available() === true;
    } catch (error) {
      failure = error?.message ?? String(error);
    }
    if (ok) return { name: rung.name, durable: rung.durable, notes };
    notes.push(`${rung.name}: unavailable — ${failure ?? rung.why}`);
  }
  // Unreachable with LADDER, whose last rung is always available. Reachable if
  // somebody passes a shorter ladder, and silence would be the wrong answer.
  return { name: 'none', durable: false, notes };
}

/** What the status bar says. Never claims durability it did not verify. */
export function describeStorage(state = probeStorage()) {
  if (state.name === 'none') return 'no storage backend available';
  return state.durable
    ? `stored on this device (${state.name})`
    : `this session only (${state.name}) — nothing is being kept`;
}
