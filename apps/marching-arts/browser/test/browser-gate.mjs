/*
 * Copyright 2026 The marching-arts Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * The four mechanisms Node cannot reach, in a real browser, as a gate.
 *
 * `npm test` runs the resolver, the compiler, the schema, the store and the
 * owner protocol on the in-memory VFS, because Node has no OPFS and no
 * SharedWorker. Four things the app depends on are therefore untouched by it:
 *
 *   1. `opfs-sahpool` actually persisting across a reload
 *   2. the Web Locks election in `src/owner/election.ts`
 *   3. the `pauseVfs()` → release → acquire → `unpauseVfs()` handoff
 *   4. SharedWorker uniqueness — one owner by construction
 *
 * Each block below is written to **fail when its mechanism is broken**, not to
 * exercise it. `test/mutate-browser.mjs` breaks each one on purpose and asserts
 * the corresponding block goes red; the table of which break each block caught
 * is in README.md and is the only reason to believe any of this.
 *
 * Three things about the shape, all forced:
 *
 *   - **Everything runs in a worker.** `createSyncAccessHandle()` is worker-only,
 *     so `openDatabase()` on a page always lands on the memory rung. The first
 *     version of this file asserted `vfs === 'opfs-sahpool'` from a page and was
 *     red for a reason that had nothing to do with the app.
 *   - **A reload is a real reload.** Persistence is write → `page.reload()` →
 *     read back in a fresh realm. Reading back in the same worker proves a cache,
 *     not a file.
 *   - **Two contexts are two pages.** Two workers spawned from one page share a
 *     page lifetime; the election is about contexts that do not.
 *
 * Usage: node test/browser-gate.mjs [--verbose] [--only <substring>] [--headed]
 */

import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { startServer } from './serve.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..');

const VERBOSE = process.argv.includes('--verbose');
const HEADED = process.argv.includes('--headed');
const ONLY = (() => {
  const i = process.argv.indexOf('--only');
  return i === -1 ? null : process.argv[i + 1];
})();

if (!existsSync(join(ROOT, 'dist', 'index.js'))) {
  console.error('no dist/. Run:  npm run build');
  process.exit(2);
}

let chromium;
try {
  ({ chromium } = await import('playwright'));
} catch {
  console.error(
    'FATAL: playwright is not installed.\n' +
      '  npm ci   (then, in a fresh environment, npx playwright install chromium)\n' +
      '  Refusing to report a pass: these four mechanisms have no other check.',
  );
  process.exit(2);
}

/**
 * Where the browser binary is.
 *
 * Playwright normally resolves this itself from `PLAYWRIGHT_BROWSERS_PATH`.
 * `MARCHING_ARTS_CHROMIUM` overrides it for environments where a preinstalled
 * Chromium does not match the pinned Playwright's expected revision — the
 * alternative there is downloading a second browser, which CI should not do and
 * a sandbox often cannot.
 */
const EXECUTABLE = process.env.MARCHING_ARTS_CHROMIUM || undefined;

// ── the tiny test harness, same shape as gate.mjs ────────────────────────────

const pending = [];
const failures = [];
let passed = 0;
let skipped = 0;

function test(name, fn) {
  pending.push([name, fn]);
}

function assert(condition, message) {
  if (!condition) throw new Error(message ?? 'assertion failed');
}

function eq(got, want, message) {
  const g = JSON.stringify(got);
  const w = JSON.stringify(want);
  if (g !== w) throw new Error(`${message ?? 'not equal'}\n    got  ${g}\n    want ${w}`);
}

// ── context plumbing ─────────────────────────────────────────────────────────

const server = await startServer();
const browser = await chromium.launch({
  headless: !HEADED,
  ...(EXECUTABLE ? { executablePath: EXECUTABLE } : {}),
});

const HARNESS = `${server.origin}/test/fixtures/harness.html`;

/**
 * A fresh browser context per test.
 *
 * Each one gets its own OPFS partition, so a leftover pool from an earlier test
 * cannot make a later one pass. It also means a test that leaves sync access
 * handles held cannot wedge the next test, which matters because several of
 * these deliberately leave a lock held until the end.
 */
async function withContext(fn) {
  const context = await browser.newContext();
  const errors = [];
  context.on('weberror', (e) => errors.push(String(e.error())));
  try {
    return await fn(context, errors);
  } finally {
    await context.close();
  }
}

/**
 * How long to wait for a harness page to boot, in ms.
 *
 * Deliberately far above what it takes (~300 ms) and deliberately not
 * Playwright's 30 s default. Booting a harness means fetching and compiling the
 * ~1 MB SQLite WASM in a fresh context with an empty HTTP cache, and every test
 * here does it two or three times; on a loaded CI runner that has been seen to
 * cross 30 s and surface as `FAIL handoff · …` with a Playwright timeout, which
 * reads as the handoff being broken. It is not a mechanism failing, so it must
 * not be able to look like one.
 */
const BOOT_TIMEOUT_MS = Number(process.env.MARCHING_ARTS_BOOT_TIMEOUT_MS || 90_000);

/** Open a harness page and wait until its worker RPC is live. */
async function tab(context) {
  const page = await context.newPage();
  try {
    await page.goto(HARNESS, { timeout: BOOT_TIMEOUT_MS });
    await page.waitForFunction('window.probeReady === true', null, {
      timeout: BOOT_TIMEOUT_MS,
    });
  } catch (error) {
    throw new Error(
      `INFRASTRUCTURE, NOT A MECHANISM: the harness page did not boot within ` +
        `${BOOT_TIMEOUT_MS} ms (${error.message.split('\n')[0]}). ` +
        'Nothing under test failed; the browser did not get as far as testing it.',
    );
  }
  return page;
}

const call = (page, cmd, arg) =>
  page.evaluate(([c, a]) => window.probe.call(c, a), [cmd, arg]);

// ── 1 · the opfs-sahpool VFS actually persists ───────────────────────────────

test('vfs · openDatabase lands on opfs-sahpool in a worker, and says durable', async () => {
  await withContext(async (context) => {
    const page = await tab(context);
    const open = await call(page, 'open');
    eq(open.vfs, 'opfs-sahpool', `fell off the ladder: ${JSON.stringify(open.notes)}`);
    eq(open.durable, true, 'the sahpool rung reported itself as not durable');
    eq(open.notes, [], 'a clean sahpool open should have nothing to explain');
  });
});

test('vfs · a write survives a reload — write, reload, read back', async () => {
  await withContext(async (context) => {
    const token = `persist-${Date.now().toString(36)}`;
    const page = await tab(context);

    const first = await call(page, 'open');
    eq(first.vfs, 'opfs-sahpool', 'the first open was not on the pool');
    eq(await call(page, 'write', { subject: token, payload: 'before the reload' }), 1);
    await call(page, 'closeDb');

    // A real reload: new document, new worker, new realm. The pool's sync access
    // handles are released by the old worker's termination, which is also the
    // only reason the second open can install it at all.
    await page.reload();
    await page.waitForFunction('window.probeReady === true');

    const second = await call(page, 'open');
    eq(second.vfs, 'opfs-sahpool', `the reload fell off the ladder: ${JSON.stringify(second.notes)}`);
    eq(
      await call(page, 'count', { subject: token }),
      1,
      'the row written before the reload was not there after it — this is not persistence',
    );
    eq(await call(page, 'payloads', { subject: token }), ['before the reload']);
  });
});

test('vfs · a fresh partition does not see the previous test’s rows', async () => {
  // The control. Without it, "the row was there after the reload" would also
  // pass against a store that returns a fixed row, or against a partition that
  // was never actually torn down between tests.
  await withContext(async (context) => {
    const page = await tab(context);
    eq((await call(page, 'open')).vfs, 'opfs-sahpool');
    eq(
      await call(page, 'count', { subject: 'never-written-here' }),
      0,
      'a subject nothing ever wrote has rows',
    );
  });
});

// ── 2 · the Web Locks election ───────────────────────────────────────────────

test('election · two contexts request ownership, exactly one gets it', async () => {
  await withContext(async (context) => {
    const a = await tab(context);
    const b = await tab(context);

    eq(await call(a, 'locksAvailable'), true, 'no navigator.locks in this worker');

    eq(await call(a, 'acquire', { timeoutMs: 2000 }), { held: true }, 'the first context did not get the lock');

    // The second must still be waiting after a full second. This is the whole
    // assertion: `acquire` deliberately leaves the request queued on timeout, so
    // "did not get it" is observable without withdrawing the proof.
    eq(
      await call(b, 'acquire', { timeoutMs: 1000 }),
      { held: false },
      'a second context acquired ownership while the first still held it',
    );

    eq(
      await call(a, 'lockState'),
      { held: 1, pending: 1 },
      'the lock manager does not agree that one holds and one waits',
    );

    // …and the queue drains in order once the holder lets go.
    eq(await call(a, 'release'), { released: true });
    eq(
      await call(b, 'acquire', { timeoutMs: 4000 }),
      { held: true },
      'the queued context never got the lock after it was released',
    );
    eq(await call(b, 'lockState'), { held: 1, pending: 0 });
    await call(b, 'release');
  });
});

test('election · the loser cannot install the pool while the winner holds it', async () => {
  // The election is only worth anything because the thing it guards is
  // genuinely exclusive. This asserts that: the second context, having lost,
  // does not silently get a durable database anyway.
  await withContext(async (context) => {
    const a = await tab(context);
    const b = await tab(context);

    eq(await call(a, 'acquire', { timeoutMs: 2000 }), { held: true });
    eq((await call(a, 'open')).vfs, 'opfs-sahpool');

    const loser = await call(b, 'open');
    eq(loser.vfs, 'memory', 'two contexts both installed the exclusive pool');
    eq(loser.durable, false, 'the memory rung reported itself durable');
    assert(
      loser.notes.some((n) => n.startsWith('opfs-sahpool unavailable:')),
      `the fall back to memory was not explained: ${JSON.stringify(loser.notes)}`,
    );
  });
});

// ── 3 · the pause / release / acquire / unpause handoff ──────────────────────

test('handoff · the owner notices a challenger, yields, and the challenger takes the pool', async () => {
  await withContext(async (context) => {
    const a = await tab(context);
    const b = await tab(context);
    const token = `handoff-${Date.now().toString(36)}`;

    // A is the owner and has written something.
    eq(await call(a, 'acquire', { timeoutMs: 2000 }), { held: true });
    eq((await call(a, 'open')).vfs, 'opfs-sahpool');
    eq(await call(a, 'write', { subject: token, payload: 'written by A' }), 1);
    eq(await call(a, 'watch', { intervalMs: 100 }), 'watching');

    // B queues. `acquire` returns { held: false } and stays in the queue.
    eq(await call(b, 'acquire', { timeoutMs: 300 }), { held: false });

    // The poll in election.ts must see it. There is no event for a queued lock
    // request, so this is the only thing that makes a handoff start at all.
    eq(
      await call(a, 'challenged', { timeoutMs: 5000 }),
      true,
      'watchForChallengers never fired: an owner would hold the pool forever',
    );

    // A's half of the handoff, in sharedworker.ts's order: pause, then release.
    eq(await call(a, 'yield'), { released: true });

    // B's half.
    eq(
      await call(b, 'acquire', { timeoutMs: 5000 }),
      { held: true },
      'the challenger never got the lock after the owner released it',
    );
    const taken = await call(b, 'open');
    eq(
      taken.vfs,
      'opfs-sahpool',
      'the new owner could not install the pool — pauseVfs() did not release the handles: ' +
        JSON.stringify(taken.notes),
    );

    // The new owner sees the old owner's data and can actually write.
    eq(
      await call(b, 'count', { subject: token }),
      1,
      'the new owner opened a different database from the one it was handed',
    );
    eq(
      await call(b, 'write', { subject: token, payload: 'written by B' }),
      2,
      'the new owner holds the pool but cannot write to it',
    );
    eq(await call(b, 'payloads', { subject: token }), ['written by A', 'written by B']);
  });
});

test('handoff · unpauseVfs() brings the original owner back, seeing the other side’s write', async () => {
  await withContext(async (context) => {
    const a = await tab(context);
    const b = await tab(context);
    const token = `rotate-${Date.now().toString(36)}`;

    eq(await call(a, 'acquire', { timeoutMs: 2000 }), { held: true });
    eq((await call(a, 'open')).vfs, 'opfs-sahpool');
    eq(await call(a, 'write', { subject: token, payload: 'A1' }), 1);

    // A pauses but keeps its OpenResult — this is the case `unpause()` exists
    // for, and the one the manual page could never check on its own.
    eq(await call(a, 'pause'), 'paused');
    eq(await call(a, 'release'), { released: true });

    eq(await call(b, 'acquire', { timeoutMs: 4000 }), { held: true });
    eq((await call(b, 'open')).vfs, 'opfs-sahpool', 'B could not take the paused pool');
    eq(await call(b, 'write', { subject: token, payload: 'B1' }), 2);
    eq(await call(b, 'pause'), 'paused');
    eq(await call(b, 'release'), { released: true });

    // Back to A, through unpause() rather than through a fresh openDatabase().
    eq(await call(a, 'acquire', { timeoutMs: 4000 }), { held: true });
    eq(await call(a, 'unpause'), 'unpaused');
    eq(
      await call(a, 'count', { subject: token }),
      2,
      'after unpauseVfs() the original owner cannot see what the other side wrote',
    );
    eq(await call(a, 'payloads', { subject: token }), ['A1', 'B1']);
    eq(
      await call(a, 'write', { subject: token, payload: 'A2' }),
      3,
      'after unpauseVfs() the original owner cannot write',
    );
  });
});

test('handoff · re-open in a context that has paused comes back on the pool', async () => {
  // installOpfsSAHPoolVfs is memoised per pool name per realm. The loop in
  // sharedworker.ts hands over and then queues again, so the second
  // openDatabase() in a context gets the pool object it paused. Without the
  // isPaused() check in open.ts that open silently lands on memory.
  await withContext(async (context) => {
    const a = await tab(context);
    const token = `reopen-${Date.now().toString(36)}`;

    eq((await call(a, 'open')).vfs, 'opfs-sahpool');
    eq(await call(a, 'write', { subject: token, payload: 'first' }), 1);
    eq(await call(a, 'pause'), 'paused');

    const again = await call(a, 'open');
    eq(
      again.vfs,
      'opfs-sahpool',
      `a re-open after a pause fell to memory: ${JSON.stringify(again.notes)}`,
    );
    eq(again.durable, true);
    eq(await call(a, 'count', { subject: token }), 1, 're-opened a different database');
  });
});

// ── 4 · SharedWorker uniqueness ──────────────────────────────────────────────

test('sharedworker · two tabs share one owner instance, by fetch count and by state', async () => {
  await withContext(async (context) => {
    const a = await tab(context);
    const token = `shared-${Date.now().toString(36)}`;

    await a.evaluate(() => window.probe.attachToOwner());
    eq(await a.evaluate((t) => window.probe.ownerWrite(t, 'from tab A'), token), 1);

    const b = await tab(context);
    await b.evaluate(() => window.probe.attachToOwner());

    // The behavioural half: the second tab sees the first tab's write. It can
    // only do that if it is talking to the same worker holding the same file —
    // a second SharedWorker instance would be blocked on the owner lock, and a
    // second one that got past the lock would be on the memory rung.
    eq(
      await b.evaluate((t) => window.probe.ownerCount(t), token),
      1,
      'the second tab does not see the first tab’s write: it is not the same owner',
    );
    eq(
      await b.evaluate((t) => window.probe.ownerWrite(t, 'from tab B'), token),
      2,
      'the second tab could not write through the owner',
    );
    eq(
      await a.evaluate((t) => window.probe.ownerPayloads(t), token),
      ['from tab A', 'from tab B'],
      'the first tab does not see the second tab’s write',
    );

    // The structural half: one script URL, one instance, therefore one fetch.
    // This is what catches a per-tab query string on the worker URL — the
    // classic way to end up with N owners while every behavioural check still
    // passes on a fast enough machine.
    eq(
      server.fetches('/dist/sharedworker.js'),
      1,
      `the owner script was fetched ${server.fetches('/dist/sharedworker.js')} times for 2 tabs: ` +
        'more than one SharedWorker instance exists',
    );
  });
});

test('sharedworker · every tab is told which rung the owner reached, and it does not overclaim', async () => {
  await withContext(async (context) => {
    const a = await tab(context);
    await a.evaluate(() => window.probe.attachToOwner());

    const check = async (page, which) => {
      const ready = (await page.evaluate(() => window.probe.notices())).filter(
        (n) => n.notice === 'ready',
      );
      assert(ready.length >= 1, `${which}: no ready notice reached the tab`);
      const n = ready[0];
      // The invariant the shell is built on: `durable` is a fact about the rung,
      // never a default. A `durable: true` on anything but the pool would be the
      // exact lie `open.ts` exists to refuse to tell.
      eq(
        n.durable,
        n.vfs === 'opfs-sahpool',
        `${which}: the owner announced vfs=${n.vfs} durable=${n.durable}`,
      );
      if (n.vfs !== 'opfs-sahpool') {
        assert(
          (n.notes ?? []).some((note) => note.startsWith('opfs-sahpool unavailable:')),
          `${which}: fell to ${n.vfs} without saying why: ${JSON.stringify(n.notes)}`,
        );
      }
      return n;
    };

    const first = await check(a, 'first tab');

    const b = await tab(context);
    await b.evaluate(() => window.probe.attachToOwner());
    const second = await check(b, 'second tab');

    eq(
      [second.vfs, second.durable],
      [first.vfs, first.durable],
      'two tabs were told different things about the same owner',
    );
  });
});

// ── the platform fact the SharedWorker owner rests on ────────────────────────
//
// This one is a tripwire, not a gate, and it is here because leaving it out
// would make the block above read as if the owner were durable.
//
// `FileSystemFileHandle.createSyncAccessHandle()` is `[Exposed=DedicatedWorker]`.
// It is **not** available in a SharedWorker, so `installOpfsSAHPoolVfs()` inside
// `dist/sharedworker.js` fails with "Missing required OPFS APIs." every time and
// the shared owner is always on the memory rung. Chromium also does not expose
// `Worker` inside a SharedWorker, so the obvious repair — the shared owner
// spawning a nested dedicated worker to hold the pool and transferring each
// tab's port to it — is not available either.
//
// So the two halves of the design are, on this engine, mutually exclusive: the
// SharedWorker gives uniqueness without durability, and a dedicated worker gives
// durability without uniqueness. The Web Lock is what bridges them, which makes
// `election.ts` the load-bearing mechanism rather than the fallback README.md
// describes it as. That is a finding about the architecture, not about the test.
//
// The assertion is written so it fails the day Chromium gains either capability
// — which is the day someone should move the owner onto the pool.
test('sharedworker · tripwire · a SharedWorker still cannot hold the pool on this engine', async () => {
  await withContext(async (context) => {
    const page = await tab(context);
    const caps = await page.evaluate(async () => {
      const src = `self.onconnect = (e) => {
        const port = e.ports[0];
        port.postMessage({
          syncAccessHandle: typeof FileSystemFileHandle.prototype.createSyncAccessHandle,
          nestedWorker: typeof Worker,
          storage: typeof navigator.storage?.getDirectory,
          locks: typeof navigator.locks,
          secure: self.isSecureContext,
        });
        port.start();
      };`;
      const url = URL.createObjectURL(new Blob([src], { type: 'text/javascript' }));
      const sw = new SharedWorker(url, { type: 'module' });
      sw.port.start();
      return new Promise((resolve, reject) => {
        sw.port.onmessage = (e) => resolve(e.data);
        setTimeout(() => reject(new Error('the capability probe never answered')), 5000);
      });
    });

    // These two are the premises everything else in the owner story assumes.
    eq(caps.secure, true, 'the harness is not a secure context: OPFS would be absent for that reason');
    eq(caps.locks, 'object', 'no navigator.locks in a SharedWorker');
    eq(caps.storage, 'function', 'no navigator.storage.getDirectory in a SharedWorker');

    // And these two are the finding.
    eq(
      caps.syncAccessHandle,
      'undefined',
      'GOOD NEWS, ACTION REQUIRED: createSyncAccessHandle() is now exposed in a ' +
        'SharedWorker. The shared owner can hold opfs-sahpool directly; move it ' +
        'there and delete this tripwire.',
    );
    eq(
      caps.nestedWorker,
      'undefined',
      'GOOD NEWS, ACTION REQUIRED: nested Workers are now available inside a ' +
        'SharedWorker. The shared owner can spawn a dedicated worker to hold the ' +
        'pool and transfer each tab port to it; do that and delete this tripwire.',
    );
  });
});

// ── run ──────────────────────────────────────────────────────────────────────

const started = Date.now();
for (const [name, fn] of pending) {
  if (ONLY && !name.includes(ONLY)) {
    skipped += 1;
    continue;
  }
  server.resetFetches();
  const t0 = Date.now();
  try {
    await fn();
    passed += 1;
    if (VERBOSE) console.log(`ok    ${name}  (${Date.now() - t0} ms)`);
  } catch (error) {
    failures.push([name, error]);
    console.error(`FAIL  ${name}\n      ${String(error.message).split('\n').join('\n      ')}`);
  }
}

await browser.close();
await server.close();

const elapsed = ((Date.now() - started) / 1000).toFixed(1);
console.log(
  `\n${passed}/${pending.length - skipped} browser-mechanism tests passed in ${elapsed}s` +
    (skipped ? ` (${skipped} filtered out by --only)` : ''),
);
if (failures.length) {
  console.error(`${failures.length} failed`);
  process.exit(1);
}
