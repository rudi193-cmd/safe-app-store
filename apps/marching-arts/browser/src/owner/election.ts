/*
 * Copyright 2026 The marching-arts Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * Who owns the database file. Web Locks decide; the SAH pool VFS hands over.
 *
 * The design goal from the build plan is "one owner **by construction** rather
 * than by protocol". Two mechanisms stack to give that:
 *
 *   1. A **SharedWorker**. One script URL, one worker instance per origin, every
 *      tab attaches a port to the same one. Where SharedWorker exists there is
 *      nothing to elect — the browser has already elected.
 *   2. A **Web Lock**, for where it does not. Chrome on Android and several
 *      WebViews ship no SharedWorker at all, so those tabs each run a dedicated
 *      worker and exactly one of them may hold the pool. The lock is what makes
 *      "exactly one" true there, and it is also the belt-and-braces for the
 *      moment a SharedWorker is being torn down while a new one starts.
 *
 * The `opfs-sahpool` VFS is the reason this cannot be skipped. It takes
 * exclusive `FileSystemSyncAccessHandle`s over its pool files; a second context
 * that tries to install it gets an exception rather than a queue. So the handoff
 * has to be explicit: the outgoing owner calls `pauseVfs()`, which releases every
 * handle, and only then releases the lock; the incoming owner acquires the lock
 * and calls `unpauseVfs()`.
 *
 * **Untested here.** Node has neither `navigator.locks` nor SharedWorker, so
 * nothing in this file is exercised by the differential suite. It is written to
 * be readable and is marked as unverified in README.md. Do not read a green
 * `npm test` as evidence that the election works.
 */

export const OWNER_LOCK = 'marching-arts.db.owner';

/** How often the holder checks whether anyone is queued behind it. */
export const CHALLENGE_POLL_MS = 250;

interface LockManagerLike {
  request(
    name: string,
    options: { mode: 'exclusive' | 'shared'; signal?: AbortSignal; ifAvailable?: boolean },
    callback: (lock: unknown) => Promise<void>,
  ): Promise<void>;
  query(): Promise<{ held?: { name?: string }[]; pending?: { name?: string }[] }>;
}

function locks(): LockManagerLike {
  const nav = globalThis.navigator as unknown as { locks?: LockManagerLike } | undefined;
  if (!nav?.locks) throw new Error('Web Locks are not available in this context');
  return nav.locks;
}

export function locksAvailable(): boolean {
  const nav = globalThis.navigator as unknown as { locks?: unknown } | undefined;
  return Boolean(nav && nav.locks);
}

export interface Ownership {
  /** Resolves when this context stops being the owner, for any reason. */
  readonly lost: Promise<void>;
  /** Give up ownership voluntarily. Idempotent. */
  release(): void;
}

/**
 * Hold `name` exclusively until `release()` is called.
 *
 * Resolves once the lock is actually held, so the caller may install the VFS
 * knowing no other context can be holding the pool files.
 */
export function acquireOwnership(name: string = OWNER_LOCK): Promise<Ownership> {
  return new Promise<Ownership>((resolveAcquired, rejectAcquired) => {
    let releaseHeld: (() => void) | null = null;
    let done = false;
    const lost = new Promise<void>((resolveLost) => {
      locks()
        .request(name, { mode: 'exclusive' }, () => {
          return new Promise<void>((resolveLock) => {
            releaseHeld = () => {
              if (done) return;
              done = true;
              resolveLock();
              resolveLost();
            };
            resolveAcquired({
              lost,
              release: () => releaseHeld?.(),
            });
          });
        })
        .catch((error) => {
          if (!done) rejectAcquired(error);
          resolveLost();
        });
    });
  });
}

/**
 * Poll for another context queued behind us on `name` and call `onChallenge`
 * once when one appears. Returns a stop function.
 *
 * Polling rather than eventing because there is no notification when a lock
 * request is enqueued. 250 ms is chosen so a newly opened tab waits a quarter of
 * a second for the database rather than however long the previous tab lives; the
 * cost is one `locks.query()` per quarter second in the owning context, which is
 * a hash-map read.
 */
export function watchForChallengers(
  name: string,
  onChallenge: () => void,
  intervalMs: number = CHALLENGE_POLL_MS,
): () => void {
  let stopped = false;
  const timer = setInterval(async () => {
    if (stopped) return;
    try {
      const state = await locks().query();
      const queued = (state.pending ?? []).some((entry) => entry.name === name);
      if (queued && !stopped) {
        stopped = true;
        clearInterval(timer);
        onChallenge();
      }
    } catch {
      /* a query failure is not a challenge; keep holding */
    }
  }, intervalMs);
  return () => {
    stopped = true;
    clearInterval(timer);
  };
}
