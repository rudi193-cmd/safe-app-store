/*
 * Copyright 2026 The marching-arts Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * A gate that cannot fail is not a gate — the browser half.
 *
 * `test/mutate.mjs` does this for the resolver. This does it for the four
 * mechanisms only a real browser can execute: it breaks each one in `dist/`,
 * reruns `test/browser-gate.mjs`, records **which block** went red, restores the
 * file and verifies the restoration by hash.
 *
 * Two things make the output worth reading rather than just the exit code:
 *
 *   - Every mutation names the block it is *supposed* to break (`expect`). A
 *     mutation caught by some other block and not by its own is reported as a
 *     failure, because it means the mechanism it targets is still ungated and
 *     the red came from somewhere incidental.
 *   - Two of these are not inventions. `pause-before-close` and
 *     `no-unpause-on-reopen` restore bugs that were actually in this tree before
 *     the gate existed; the gate found them on its first run. They are kept as
 *     mutations so the fixes cannot quietly regress.
 *
 * One repair the gate prompted is **not** covered by a mutation here: removing
 * the `.catch(() => {})` around the pause/close pair in `sharedworker.ts`. The
 * handoff blocks drive `election.ts` and `open.ts` directly rather than through
 * the SharedWorker, and the SharedWorker owner cannot reach the pool on this
 * engine anyway (see README.md), so a mutation restoring that swallow would pass
 * — which is exactly why it is named here instead of being written and reported
 * as caught.
 *
 * Usage: node test/mutate-browser.mjs [--verbose]
 */

import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const DIST = join(HERE, '..', 'dist');
const VERBOSE = process.argv.includes('--verbose');

if (!existsSync(join(DIST, 'open.js'))) {
  console.error('no dist/. Run:  npm run build');
  process.exit(2);
}

const sha = (s) => createHash('sha256').update(s).digest('hex').slice(0, 12);

/** The four blocks in browser-gate.mjs, keyed by the prefix each test uses. */
const BLOCKS = ['vfs', 'election', 'handoff', 'sharedworker'];

const MUTATIONS = [
  // ── 1 · the opfs-sahpool VFS actually persists ────────────────────────────
  {
    name: 'durable-lie',
    file: 'open.js',
    expect: 'vfs',
    from: "            let db = new pool.OpfsSAHPoolDb(filename);",
    to: "            let db = new api.oo1.DB(':memory:', 'c');",
    why:
      'the pool is installed and reported, but the database is opened in memory. ' +
      'Every label the caller can see stays correct; only a reload can tell.',
  },
  {
    name: 'no-opfs-at-all',
    file: 'open.js',
    expect: 'vfs',
    from: "    if (!options.forceMemory && typeof api.installOpfsSAHPoolVfs === 'function') {",
    to: "    if (false && !options.forceMemory && typeof api.installOpfsSAHPoolVfs === 'function') {",
    why: 'the ladder never tries the pool and everything silently lands on memory',
  },

  // ── 2 · the Web Locks election ────────────────────────────────────────────
  {
    name: 'no-lock',
    file: 'owner/election.js',
    expect: 'election',
    from: "        const lost = new Promise((resolveLost) => {\n            locks()",
    to:
      "        const lost = new Promise((resolveLost) => {\n" +
      "            resolveAcquired({ lost, release: () => { done = true; resolveLost(); } });\n" +
      "            if (false)\n            locks()",
    why: 'ownership is granted without ever requesting the lock — everyone is the owner',
  },
  {
    name: 'shared-mode',
    file: 'owner/election.js',
    expect: 'election',
    from: "                .request(name, { mode: 'exclusive' }, () => {",
    to: "                .request(name, { mode: 'shared' }, () => {",
    why: 'the lock is taken shared, so every context holds it at once and none queues',
  },

  // ── 3 · the pause / release / acquire / unpause handoff ───────────────────
  {
    name: 'skip-pause',
    file: 'open.js',
    expect: 'handoff',
    from: "                    db.close();\n                    pool.pauseVfs();\n                    paused = true;",
    to: "                    paused = true;",
    why: 'pause() releases nothing, so the incoming owner finds the handles still held',
  },
  {
    name: 'pause-before-close',
    file: 'open.js',
    expect: 'handoff',
    from: "                    db.close();\n                    pool.pauseVfs();",
    to: "                    try { pool.pauseVfs(); } catch { }\n                    db.close();",
    why:
      'the ordering this tree actually shipped: pauseVfs() while a database handle is ' +
      'open throws SQLITE_MISUSE and has no side effects, so the handles stay held',
  },
  {
    name: 'no-unpause-on-reopen',
    file: 'open.js',
    expect: 'handoff',
    from: "            if (pool.isPaused())\n                await pool.unpauseVfs();",
    to: "            if (false)\n                await pool.unpauseVfs();",
    why:
      'a context that paused and re-opens gets its own memoised, still-paused pool ' +
      'back and drops to memory — the second lap of sharedworker.ts’s loop',
  },
  {
    name: 'no-challenger-poll',
    file: 'owner/election.js',
    expect: 'handoff',
    from: "            const queued = (state.pending ?? []).some((entry) => entry.name === name);",
    to: "            const queued = false && (state.pending ?? []).some((entry) => entry.name === name);",
    why:
      'the owner never notices a challenger. There is no event for a queued lock ' +
      'request, so without the poll a handoff never starts at all.',
  },

  // ── 4 · SharedWorker uniqueness ───────────────────────────────────────────
  {
    name: 'per-tab-worker-url',
    file: 'index.js',
    expect: 'sharedworker',
    from: "        const worker = new g.SharedWorker(url, { type: 'module', name: 'marching-arts-db' });",
    to:
      "        const worker = new g.SharedWorker(url + '?tab=' + Math.random().toString(36).slice(2), " +
      "{ type: 'module', name: 'marching-arts-db' });",
    why:
      'a per-tab query string on the worker URL. The classic way to end up with one ' +
      'owner per tab while the code still says SharedWorker.',
  },
  {
    name: 'dedicated-worker-per-tab',
    file: 'index.js',
    expect: 'sharedworker',
    from: "    if (typeof g.SharedWorker === 'function') {",
    to: "    if (false && typeof g.SharedWorker === 'function') {",
    why:
      'take the no-SharedWorker fallback even where SharedWorker exists, so every tab ' +
      'runs its own owner and uniqueness is left entirely to the lock',
  },
];

// ── running the gate, and attributing the red to a block ─────────────────────

function runGate() {
  const r = spawnSync(process.execPath, [join(HERE, 'browser-gate.mjs')], {
    encoding: 'utf8',
    timeout: 15 * 60 * 1000,
  });
  const out = `${r.stdout || ''}\n${r.stderr || ''}`;
  const failed = new Set();
  for (const line of out.split('\n')) {
    const m = /^FAIL {2}(\w+) · /.exec(line.trim());
    if (m && BLOCKS.includes(m[1])) failed.add(m[1]);
  }
  const summary = out.split('\n').find((l) => l.includes('browser-mechanism tests passed')) ?? '';
  return { status: r.status, failed: [...failed], summary: summary.trim(), out };
}

console.log('browser mutation test: break each mechanism on purpose, confirm its gate notices\n');

const baseline = runGate();
console.log(`baseline  exit ${baseline.status}  ${baseline.summary}`);
if (baseline.status !== 0) {
  console.error('\nthe browser gate is already failing; fix that before mutating.\n');
  // The whole failure, not just the FAIL lines. A baseline that failed on a
  // harness-boot timeout rather than on a mechanism looks identical from the
  // headline, and the difference is the difference between a bug and a slow
  // runner.
  console.error(
    baseline.out
      .split('\n')
      .filter((l) => l.startsWith('FAIL') || l.startsWith('      '))
      .join('\n'),
  );
  process.exit(2);
}

const results = [];
for (const m of MUTATIONS) {
  const path = join(DIST, m.file);
  const original = readFileSync(path, 'utf8');
  const originalHash = sha(original);

  if (!original.includes(m.from)) {
    console.error(
      `\n[${m.name}] SKIPPED — the text this mutation edits is not in dist/${m.file}.\n` +
        '  A skipped mutation is a hole in the gate, not a pass; fix the pattern.',
    );
    results.push({ ...m, failed: null });
    continue;
  }

  writeFileSync(path, original.replace(m.from, m.to));
  let outcome;
  try {
    outcome = runGate();
  } finally {
    writeFileSync(path, original);
    const restoredHash = sha(readFileSync(path, 'utf8'));
    if (restoredHash !== originalHash) {
      console.error(`\nFATAL: dist/${m.file} was not restored (${restoredHash} != ${originalHash})`);
      process.exit(3);
    }
  }

  results.push({ ...m, failed: outcome.failed });
  const hitTarget = outcome.failed.includes(m.expect);
  console.log(`\n[${m.name}] ${m.why}`);
  console.log(`  exit ${outcome.status}  ${outcome.summary}`);
  console.log(
    `  blocks that went red: ${outcome.failed.length ? outcome.failed.join(', ') : 'NONE'}` +
      `   (target: ${m.expect}${hitTarget ? ' — hit' : ' — MISSED'})`,
  );
  if (VERBOSE) {
    for (const l of outcome.out.split('\n').filter((l) => l.trim().startsWith('FAIL')).slice(0, 6)) {
      console.log('    ' + l.trim());
    }
  }
}

const after = runGate();
console.log(`\nrestored  exit ${after.status}  ${after.summary}`);

console.log('\n-- summary --');
console.log(`  ${'mutation'.padEnd(26)} ${'target'.padEnd(14)} caught by`);
for (const r of results) {
  const verdict =
    r.failed === null
      ? 'SKIPPED (pattern missing)'
      : r.failed.length === 0
        ? 'MISSED BY EVERYTHING'
        : r.failed.join(' + ');
  console.log(`  ${r.name.padEnd(26)} ${r.expect.padEnd(14)} ${verdict}`);
}

const missed = results.filter((r) => r.failed === null || !r.failed.includes(r.expect));
if (missed.length || after.status !== 0) {
  console.error(
    `\n${missed.length} mutation(s) not caught by the block they target; ` +
      `restored gate ${after.status === 0 ? 'green' : 'RED'}`,
  );
  process.exit(1);
}
console.log('\nevery mutation was caught by the block that targets it, and the restored gate is green');
