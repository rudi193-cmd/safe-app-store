/*
 * Copyright 2026 The marching-arts Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * A dedicated worker that exposes `dist/` over a tiny command RPC.
 *
 * Everything the browser gate checks has to happen in a **worker**, not on a
 * page. `FileSystemFileHandle.createSyncAccessHandle()` is only exposed in
 * dedicated and shared workers, so `installOpfsSAHPoolVfs()` on the main thread
 * fails with "Missing required OPFS APIs." and `openDatabase()` quietly returns
 * the memory rung. That is not a limitation of this harness; it is why the app
 * ships a SharedWorker owner in the first place.
 *
 * This file imports the same `dist/index.js` a tab does, and calls the same
 * exported functions. It contains no copy of any mechanism under test — if a
 * check here passes it is because `open.ts` or `election.ts` made it pass. The
 * mutation runner edits `dist/` and reruns the gate against this same file.
 *
 * Protocol: `{ id, cmd, arg }` in, `{ id, ok, value }` or `{ id, ok: false,
 * error }` out. Unsolicited `{ event }` messages carry things that happen
 * without being asked for, which is the whole point of the challenger watch.
 */

import {
  Band,
  GrantState,
  OWNER_LOCK,
  Store,
  acquireOwnership,
  locksAvailable,
  openDatabase,
  principal,
  watchForChallengers,
} from '../../dist/index.js';

/** Distinct per realm. Two of these means two contexts, which is the point. */
const REALM = Math.random().toString(36).slice(2, 10);

let open = null;
let store = null;

/** The in-flight or held ownership, and a promise that settles when it lands. */
let ownership = null;
let acquiring = null;
let acquired = false;

/** Set by `watch`; resolves the first time a challenger queues behind us. */
let challenged = null;
let stopWatching = null;

const settled = (promise) => {
  let done = false;
  promise.then(
    () => {
      done = true;
    },
    () => {
      done = true;
    },
  );
  return () => done;
};

function withTimeout(promise, ms, onTimeout) {
  return new Promise((resolve, reject) => {
    let finished = false;
    const timer = setTimeout(() => {
      if (finished) return;
      finished = true;
      resolve(onTimeout);
    }, ms);
    promise.then(
      (value) => {
        if (finished) return;
        finished = true;
        clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        if (finished) return;
        finished = true;
        clearTimeout(timer);
        reject(error);
      },
    );
  });
}

const ops = {
  realm: () => REALM,

  locksAvailable: () => locksAvailable(),

  async open(arg = {}) {
    open = await openDatabase(arg);
    store = await Store.open(open.conn);
    return { vfs: open.vfs, durable: open.durable, notes: [...open.notes] };
  },

  async write({ subject, payload, band = Band.ROSTER }) {
    await store.recordFact(subject, band, 'browser-gate', { payload });
    return store.count(principal(subject));
  },

  count: ({ subject }) => store.count(principal(subject)),

  async payloads({ subject }) {
    const rows = await store.visible(principal(subject), { orderBy: 'id' });
    return rows.map((r) => r.payload);
  },

  async pause() {
    await open.pause();
    return 'paused';
  },

  async unpause() {
    await open.unpause();
    return 'unpaused';
  },

  async closeDb() {
    await open.close();
    open = null;
    store = null;
    return 'closed';
  },

  /**
   * The P1 gate's core claims, against a real file rather than `:memory:`.
   *
   * Used by the manual page (`test/browser.html`), which cannot run these on the
   * main thread because that thread can never install the pool. The automated
   * gate does not call this — `test/gate.mjs` already asserts all of it, in more
   * detail and with statement tracing, and duplicating it here would mean two
   * places to update when the policy moves.
   */
  async gateBattery() {
    const stamp = String(Date.now());
    const visible = `visible-${stamp}`;
    const hidden = `hidden-${stamp}`;
    const leader = principal(`leader-${stamp}`);
    for (let i = 0; i < 3; i++)
      await store.recordFact(visible, Band.CRAFT, 'rehearsal log', { payload: `v${i}` });
    for (let i = 0; i < 7; i++)
      await store.recordFact(hidden, Band.CRAFT, 'rehearsal log', { payload: `h${i}` });
    await store.recordGrant(visible, leader.personId, Band.CRAFT, GrantState.SEALED, 'form', {
      sealedBy: 'guardian',
    });

    const refused = await store.visible(leader, {
      where: 'facts.subject_id = :s',
      params: { s: hidden },
    });
    const absent = await store.visible(leader, {
      where: 'facts.subject_id = :s',
      params: { s: 'no-such-person' },
    });
    const subjects = await store.subjects(leader);
    return [
      [(await store.count(leader)) === 3, 'COUNT excludes hidden rows'],
      [
        (await store.count(leader, { where: '1 = 1 OR 1 = 1' })) === 3,
        'a caller filter cannot widen',
      ],
      [
        refused.length === 0 && absent.length === 0,
        'refused and nonexistent are indistinguishable',
      ],
      [subjects.length === 1 && subjects[0] === visible, 'the subject list omits'],
      [(await store.count(principal('nobody-at-all'))) === 0, 'an unknown principal sees nothing'],
    ];
  },

  // ── election ───────────────────────────────────────────────────────────────

  /**
   * Start requesting the owner lock. Returns as soon as it is held, or reports
   * `{ held: false }` after `timeoutMs` — *without* withdrawing the request, so
   * the caller can then assert that this context is sitting in the queue. That
   * is the shape the election test needs: "the second context did not get it"
   * has to be observable without cancelling the thing that proves it.
   */
  async acquire({ timeoutMs = 1000, name = OWNER_LOCK } = {}) {
    if (!acquiring) {
      acquiring = acquireOwnership(name).then((o) => {
        ownership = o;
        acquired = true;
        return o;
      });
      acquiring.catch(() => {});
    }
    const isSettled = settled(acquiring);
    await withTimeout(acquiring, timeoutMs, null);
    return { held: acquired && isSettled() };
  },

  release() {
    if (!ownership) return { released: false };
    ownership.release();
    ownership = null;
    acquiring = null;
    acquired = false;
    return { released: true };
  },

  /** What `navigator.locks.query()` says about the owner lock, right now. */
  async lockState({ name = OWNER_LOCK } = {}) {
    const state = await navigator.locks.query();
    return {
      held: (state.held ?? []).filter((l) => l.name === name).length,
      pending: (state.pending ?? []).filter((l) => l.name === name).length,
    };
  },

  /** Arm the challenger poll. Emits `{ event: 'challenged' }` when it fires. */
  watch({ name = OWNER_LOCK, intervalMs } = {}) {
    challenged = new Promise((resolve) => {
      stopWatching = watchForChallengers(
        name,
        () => {
          self.postMessage({ event: 'challenged', realm: REALM });
          resolve(true);
        },
        intervalMs,
      );
    });
    return 'watching';
  },

  /** Block until the challenger poll fires, or report false after `timeoutMs`. */
  challenged: ({ timeoutMs = 4000 } = {}) => withTimeout(challenged, timeoutMs, false),

  unwatch() {
    stopWatching?.();
    stopWatching = null;
    return 'stopped';
  },

  /**
   * The outgoing owner's half of a handoff, in the order `sharedworker.ts` does
   * it: stop serving, release the pool, *then* release the lock.
   */
  async yield() {
    stopWatching?.();
    await open.pause();
    const r = ops.release();
    return r;
  },
};

self.onmessage = async (event) => {
  const { id, cmd, arg } = event.data ?? {};
  if (typeof id !== 'number') return;
  try {
    const op = ops[cmd];
    if (!op) throw new Error(`unknown command ${JSON.stringify(cmd)}`);
    self.postMessage({ id, ok: true, value: await op(arg) });
  } catch (error) {
    self.postMessage({ id, ok: false, error: String((error && error.message) || error) });
  }
};

self.postMessage({ event: 'up', realm: REALM });
