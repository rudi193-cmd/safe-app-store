/*
 * Copyright 2026 The marching-arts Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * The SharedWorker entry point: the one context that holds the database.
 *
 * Lifecycle, in order:
 *
 *   1. Acquire the `marching-arts.db.owner` Web Lock. The SharedWorker is
 *      already unique per origin; the lock covers the browsers that have no
 *      SharedWorker (this file is also usable as a dedicated worker, where the
 *      lock is the only thing keeping the pool single-holder) and the window
 *      during a worker restart where two instances briefly coexist.
 *   2. Install `opfs-sahpool` and open the database. Report the rung reached to
 *      every attached port as a `ready` notice, including `durable: false` when
 *      it fell back to memory — a shell that hides that is lying.
 *   3. Serve requests, one at a time, until a challenger queues on the lock.
 *   4. On challenge: stop serving, `pauseVfs()`, release the lock. The incoming
 *      owner acquires it and calls `unpauseVfs()`. Then queue behind them, so a
 *      handoff is a rotation rather than an abdication.
 *
 * Gated by the `sharedworker` block of `test/browser-gate.mjs`: two tabs must see
 * each other's writes *and* the browser must fetch this script exactly once.
 *
 * **What that block cannot make true.** `createSyncAccessHandle()` is
 * `[Exposed=DedicatedWorker]`, so step 2 above always fails here and this owner
 * is always on the memory rung; Chromium does not expose `Worker` inside a
 * SharedWorker either, so it cannot delegate the pool to a nested dedicated
 * worker. The uniqueness this file gives is real; the durability is not, and a
 * tripwire test fails the day Chromium changes either. See README.md.
 */

import { openDatabase, type OpenOptions, type OpenResult } from './open.js';
import { acquireOwnership, locksAvailable, watchForChallengers, OWNER_LOCK } from './owner/election.js';
import { announce, serve, type PortLike } from './owner/server.js';
import type { Connection } from './connection.js';

const ports = new Set<PortLike>();
let open: OpenResult | null = null;

function connection(): Connection | null {
  return open ? open.conn : null;
}

async function ownershipCycle(options: OpenOptions): Promise<void> {
  // Loop rather than run once: after handing the pool to a challenger this
  // context queues again, so a tab that yielded is not permanently demoted.
  for (;;) {
    const ownership = locksAvailable() ? await acquireOwnership(OWNER_LOCK) : null;
    open = await openDatabase(options);
    if (open.vfs !== 'memory') await open.unpause().catch(() => {});
    announce(ports, {
      notice: 'ready',
      vfs: open.vfs,
      durable: open.durable,
      notes: open.notes,
    });

    if (!ownership) return; // no Web Locks: hold forever, single context only.

    await new Promise<void>((resolve) => {
      const stop = watchForChallengers(OWNER_LOCK, () => {
        stop();
        resolve();
      });
      ownership.lost.then(() => {
        stop();
        resolve();
      });
    });

    announce(ports, { notice: 'paused', reason: 'another context asked for the database' });
    const closing = open;
    open = null;
    // Not `.catch(() => {})`. If `pause()` fails the sync access handles are
    // still held, and releasing the lock anyway hands the challenger a lock over
    // a pool it cannot install — it falls back to memory and the handoff has
    // silently become a downgrade. The lock is released regardless, because the
    // alternative is a challenger that waits forever, but the reason travels to
    // every attached port instead of being swallowed.
    try {
      await closing.pause();
      await closing.close();
    } catch (error) {
      announce(ports, {
        notice: 'lost',
        reason: `could not release the pool cleanly: ${(error as Error).message}`,
      });
    }
    ownership.release();
  }
}

export function startOwner(options: OpenOptions = {}): void {
  void ownershipCycle(options).catch((error) => {
    announce(ports, { notice: 'lost', reason: (error as Error).message });
  });
}

function attach(port: PortLike): void {
  ports.add(port);
  serve(port, connection);
  if (open) {
    announce([port], {
      notice: 'ready',
      vfs: open.vfs,
      durable: open.durable,
      notes: open.notes,
    });
  }
}

const scope = globalThis as unknown as {
  onconnect?: (event: { ports: PortLike[] }) => void;
  addEventListener?: (type: string, listener: (event: unknown) => void) => void;
  postMessage?: (message: unknown) => void;
};

// SharedWorker: one `connect` event per tab, each carrying a fresh port.
if ('onconnect' in scope || typeof SharedWorkerGlobalScope !== 'undefined') {
  scope.onconnect = (event) => {
    for (const port of event.ports) attach(port);
  };
  startOwner();
} else if (typeof scope.postMessage === 'function' && typeof scope.addEventListener === 'function') {
  // Dedicated-worker fallback for browsers with no SharedWorker. Here the Web
  // Lock in election.ts is not belt-and-braces, it is the whole mechanism.
  attach(scope as unknown as PortLike);
  startOwner();
}

declare const SharedWorkerGlobalScope: unknown;
