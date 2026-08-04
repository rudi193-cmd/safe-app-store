/*
 * Copyright 2026 The dcisim Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * The rasteriser, gated. Needs a real Chromium.
 *
 *   node --test test/raster.test.mjs
 *
 * Separate from construct.test.mjs, and deliberately so. Mutation testing put
 * `rasterise.mjs` at 2 of 83 mutants killed with 88% never executed: no test
 * called it, because the raster assertions all read the committed PNG rather
 * than making one. The Chromium invocation, the window-chrome headroom crop and
 * the corner-white guard that refuses to write a wrong icon were all ungated.
 *
 * The obvious fix is a skipUnless(chromium) guard inside the main suite, and it
 * is the wrong one. safe-app-store already carries that scar: its
 * bureau-differential job exists because the Python leg "reports green having
 * compared nothing" — the tests are guarded with skipUnless(node), a skipped
 * test still exits 0, and the leg passed having compared nothing at all. Its
 * remedy is a dedicated job that "asserts they happened rather than trusting
 * the exit code".
 *
 * So this file does not skip. No Chromium is a failure, not an absence, and the
 * last test asserts a count of comparisons actually performed — a suite that
 * silently did nothing fails on that alone.
 */

import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { RASTER, findChrome, rasterise } from '../mark/rasterise.mjs';
import { decodePng, distance, pixelAt } from '../mark/png.mjs';

/** Counts what actually ran, so "did nothing" is distinguishable from "passed". */
const performed = { comparisons: 0 };

let chrome = null;
let discovery = null;
try {
  chrome = findChrome();
} catch (error) {
  discovery = error.message;
}

test('a browser is available — this gate does not skip', () => {
  // Failing here is the point. If this file cannot run, CI must go red rather
  // than green-by-omission, because green-by-omission is exactly how a raster
  // path stays unverified for as long as this one did.
  assert.ok(chrome, `no Chromium found, so nothing below can be checked:\n${discovery}`);
});

test('rasterising now reproduces the committed icon', () => {
  assert.ok(chrome, 'no Chromium');
  const work = mkdtempSync(join(tmpdir(), 'dcisim-raster-'));
  try {
    const out = join(work, 'fresh.png');
    rasterise({ chrome, out });
    assert.ok(existsSync(out), 'the rasteriser wrote nothing');

    const fresh = decodePng(readFileSync(out));
    const committed = decodePng(readFileSync(RASTER.out));
    assert.equal(fresh.width, committed.width);
    assert.equal(fresh.height, committed.height);

    // Not byte-equality: a different Chromium antialiases differently, which is
    // why the committed PNG is not byte-compared anywhere. Pixel agreement
    // within a tolerance is the strongest claim that survives that.
    let differing = 0;
    for (let y = 0; y < fresh.height; y += 1) {
      for (let x = 0; x < fresh.width; x += 1) {
        performed.comparisons += 1;
        if (distance(pixelAt(fresh, x, y), pixelAt(committed, x, y)) > 24) differing += 1;
      }
    }
    const fraction = differing / performed.comparisons;
    assert.ok(
      fraction < 0.01,
      `${(fraction * 100).toFixed(2)}% of pixels differ from the committed icon — ` +
        'either the mark changed without the PNG being regenerated, or this renderer disagrees',
    );
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
});

test('the comparisons above actually happened', () => {
  // The lesson from safe-app-store's bureau-differential, applied here: assert
  // the work occurred rather than trusting an exit code.
  assert.equal(
    performed.comparisons,
    RASTER.size * RASTER.size,
    `expected ${RASTER.size ** 2} pixel comparisons, counted ${performed.comparisons}`,
  );
});
