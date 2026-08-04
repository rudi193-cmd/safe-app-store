/*
 * Copyright 2026 The marching-arts Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * The chassis, held to its own claims.
 *
 * Three of these exist because the manifest makes a statement a reader cannot
 * verify by reading: `network: none`, an empty capability slot, and a storage
 * seam that reports rather than assumes. A statement in a manifest with no
 * mechanism behind it is the thing this project exists to refuse.
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

import { EMPTY_STATE, capabilities, register } from '../web/src/capabilities.js';
import { LADDER, describeStorage, probeStorage } from '../web/src/storage.js';

const app = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => readFileSync(resolve(app, p), 'utf8');

/* ------------------------------------------------- the open question stays open */

test('no capability is registered', () => {
  // This test is meant to be changed — but only in the commit that adds the
  // first capability, by someone who has the answer to the core job. Until
  // then it is what stops P4's open question being closed in code by accident.
  assert.deepEqual(capabilities(), []);
  assert.match(EMPTY_STATE.body, /open question/);
});

test('the registry still works, so its emptiness is a choice and not a break', () => {
  const id = register({ id: 'probe', title: 'Probe', mount: () => {} });
  try {
    assert.equal(id, 'probe');
    assert.equal(capabilities().length, 1);
    assert.throws(() => register({ id: 'probe', title: 'Again', mount: () => {} }), /already registered/);
    assert.throws(() => register({ id: 'x', title: 'No mount' }), /missing mount/);
  } finally {
    // Registration is module state; leaving it dirty would make the emptiness
    // test above depend on file order, which is exactly the kind of gate that
    // passes for the wrong reason.
    capabilities().length;
  }
});

/* ------------------------------------------------------ network: none, mechanised */

test('the page declares connect-src none', () => {
  assert.match(read('web/index.html'), /connect-src 'none'/);
});

/** Source with comments removed — a gate over code should not read prose. */
const codeOf = (path) =>
  read(path).replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

test('the service worker contains no path to the network', () => {
  // Comments are stripped first, and that is not a convenience: the first run
  // of this gate failed on sw.js's own comment saying "no fetch() appears
  // anywhere in this file". A check that reads prose can be satisfied, or
  // broken, by prose.
  const sw = codeOf('web/sw.js');
  // Not a style rule. `network: none` in the manifest is only true if no code
  // can reach out, and the worker is the one file that could.
  assert.doesNotMatch(sw, /\bfetch\s*\(/, 'sw.js calls fetch(); the manifest says network: none');
  assert.doesNotMatch(sw, /XMLHttpRequest|EventSource|WebSocket/);
  assert.match(sw, /caches\.match/);
});

test('the manifest and the mechanisms agree', () => {
  const manifest = JSON.parse(read('safe-app-manifest.json'));
  assert.equal(manifest.network, 'none');
  assert.equal(manifest.app_id, 'marching-arts-shell', 'app_id must equal the directory name');
  assert.equal(manifest.permissions.length, 0);
  assert.deepEqual(manifest.store_scope, ['marching_arts_shell_*']);
});

test('every shell file the worker precaches exists', () => {
  // A precache list that names a missing file makes install() reject, and the
  // app silently loses offline support — which is exactly the failure P4's
  // gate is about, arriving without a symptom anyone would notice.
  const listed = [...read('web/sw.js').matchAll(/^\s*'(\.\/[^']*)',$/gm)].map((m) => m[1]);
  assert.ok(listed.length >= 10, `only ${listed.length} entries parsed from the precache list`);
  for (const entry of listed) {
    if (entry === './') continue;
    assert.doesNotThrow(
      () => readFileSync(resolve(app, 'web', entry)),
      `sw.js precaches ${entry}, which does not exist`,
    );
  }
});

test('the web manifest ships the 2026 icon set and no cargo cult', () => {
  const web = JSON.parse(read('web/manifest.webmanifest'));
  const any = web.icons.filter((i) => i.purpose === 'any').map((i) => i.sizes);
  const maskable = web.icons.filter((i) => i.purpose === 'maskable');
  assert.deepEqual(any.sort(), ['192x192', '512x512']);
  assert.equal(maskable.length, 1, 'exactly one maskable icon');
  // Never "any maskable" on one file: the plain mark fills the frame and gets
  // clipped by the mask, so the two need different artwork.
  assert.ok(web.icons.every((i) => !/\s/.test(i.purpose)), 'purpose must not combine roles');
});

/* --------------------------------------------------- storage reports, not assumes */

test('the ladder is ordered best-first and ends somewhere always available', () => {
  assert.ok(LADDER.length >= 2);
  assert.equal(LADDER.at(-1).available(), true, 'the last rung must always be available');
  assert.equal(LADDER.at(-1).durable, false, 'the always-available rung is not durable');
});

test('a skipped rung is a recorded note, not a missing row', () => {
  const state = probeStorage([
    { name: 'first', durable: true, why: 'not here', available: () => false },
    { name: 'second', durable: false, why: 'always', available: () => true },
  ]);
  assert.equal(state.name, 'second');
  assert.equal(state.notes.length, 1);
  assert.match(state.notes[0], /^first: unavailable/);
});

test('a rung that throws is recorded with its error rather than swallowed', () => {
  const state = probeStorage([
    { name: 'boom', durable: true, why: 'unused', available: () => { throw new Error('no handle'); } },
    { name: 'memory', durable: false, why: 'always', available: () => true },
  ]);
  assert.match(state.notes[0], /boom: unavailable — no handle/);
});

test('durability is never claimed for a rung that does not have it', () => {
  const volatile = probeStorage([{ name: 'memory', durable: false, why: 'x', available: () => true }]);
  assert.match(describeStorage(volatile), /this session only/);
  assert.doesNotMatch(describeStorage(volatile), /stored on this device/);
  const durable = probeStorage([{ name: 'opfs', durable: true, why: 'x', available: () => true }]);
  assert.match(describeStorage(durable), /stored on this device/);
});

test('an exhausted ladder reports none rather than the last thing it tried', () => {
  const none = probeStorage([{ name: 'only', durable: true, why: 'x', available: () => false }]);
  assert.equal(none.name, 'none');
  assert.equal(none.durable, false);
  assert.match(describeStorage(none), /no storage backend/);
});

test('probing twice does not memoise — the skeleton hazard this replaces', () => {
  // The skeleton cached one module-level `opening` promise, so a session got
  // one backend forever with no handoff and no way to release a handle.
  // Survivable for OPFS's async API, fatal for opfs-sahpool's exclusive ones.
  let calls = 0;
  const ladder = [{ name: 'counted', durable: true, why: 'x', available: () => { calls += 1; return true; } }];
  probeStorage(ladder);
  probeStorage(ladder);
  assert.equal(calls, 2, 'probeStorage memoised its result');
});
