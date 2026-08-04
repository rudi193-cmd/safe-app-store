/*
 * Copyright 2026 The dcisim Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * The gates, run against the shipped mark.
 *
 *   node --test test/construct.test.mjs
 *
 * The geometric invariants live in invariants.mjs as predicates over any
 * geometry, and this file applies them to CANON. That split came out of
 * building explore.mjs: run the same checks over other specs and it becomes
 * visible which of them describe the construction and which only ever
 * described this logo. Two turned out to be the latter and now say so.
 *
 * What stays here is everything about the artefact rather than the geometry:
 * the committed files, the colours they carry, and the raster.
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { CANON, construct, glyph } from '../mark/construct.mjs';
import { check, hasVerticalMirror, verdict } from '../mark/invariants.mjs';
import { PATHS, accents, outputs } from '../mark/build.mjs';
import { RASTER, assertCropCaughtTheIcon } from '../mark/rasterise.mjs';
import { decodePng, distance, encodePng, pixelAt, rgb } from '../mark/png.mjs';

/* ------------------------------------------------------- the construction */

let geo = null;
let refusal = null;
try {
  geo = construct(CANON);
} catch (error) {
  // derive() refuses specs it cannot draw honestly, which is right — but the
  // refusal has to arrive as one named failure rather than as the whole file
  // failing to load, or a mutation run cannot tell which gate spoke.
  refusal = error.message;
}

test('the canonical spec is constructible', () => {
  assert.equal(refusal, null, `the generator refused CANON: ${refusal}`);
});

for (const result of geo ? check(geo) : []) {
  test(result.name, () => {
    assert.ok(result.applies, `does not apply to the canonical mark: ${result.detail}`);
    assert.ok(result.ok, result.detail);
  });
}

test('the canonical mark needs no more than the floor emission precision', () => {
  // Not a style preference. The precision is searched for, and a spec whose
  // arcs are shallow enough to need more decimals is telling you how close it
  // is to being unencodable. CANON sitting at the floor is the margin: N 5
  // span 2 needs 5 decimals, N 9 span 4 needs 7.
  assert.equal(geo?.derived.precision, 4, 'CANON no longer emits at 4 decimals');
});

/* -------------------------------------------------- the gates have gates */

/**
 * Known-bad specs, and the gate each one must trip.
 *
 * Everything above this point only ever feeds CANON to the invariants, which
 * means a gate could be gutted and stay green — and one was. Mutation testing
 * found that emptying `withinSweep()` in invariants.mjs survives: all other
 * tests pass while `no wavefront crosses another` reports zero crossings for a
 * mark that visibly tangles. That gate was added last round precisely to catch
 * tangling, and it had never once been shown to fire from inside the suite.
 *
 * These are positive controls. They come from explore.mjs, which had been
 * finding these failures all along — as a script someone runs and reads, which
 * is not a gate. `applies` is asserted separately from `ok` here for the same
 * reason it is reported separately: a check that stopped applying is not a
 * check that passed.
 */
const MUST_TRIP = [
  [{ N: 4, span: 1 }, 'no wavefront crosses another'],
  [{ N: 4, span: 1 }, 'wavefronts stay a stroke apart from each other'],
  [{ N: 6, span: 1 }, 'no wavefront crosses another'],
  [{ N: 9, span: 4 }, 'each wavefront is longer than the stroke is thick'],
  [{ N: 5, span: 2, gapRatio: 0.5 }, 'the gap leaves the source it lands on visible'],
  [{ N: 5, span: 2, gapRatio: 0.5 }, 'no wavefront runs through a source'],
  [{ phase: 15 }, 'the grid is no larger than the mark needs'],
];

for (const [spec, gate] of MUST_TRIP) {
  test(`${JSON.stringify(spec)} trips: ${gate}`, () => {
    const result = check(construct({ ...CANON, ...spec })).find((r) => r.name === gate);
    assert.ok(result, `no such gate: ${gate}`);
    assert.ok(result.applies, `gate stopped applying rather than failing: ${result.detail}`);
    assert.equal(result.ok, false, `gate did not fire: ${result.detail}`);
  });
}

/** Specs the generator must refuse outright, and why. */
const MUST_REFUSE = [
  [{ N: 4, span: 2 }, /2\*span < N/],
  [{ N: 3, span: 1, gapRatio: 20 }, /gap .* cannot exceed the wavefront radius/],
  [{ N: 3, span: 0 }, /span must be an integer/],
  [{ N: 2, span: 1 }, /N must be an integer/],
];

for (const [spec, expected] of MUST_REFUSE) {
  test(`${JSON.stringify(spec)} is refused`, () => {
    // The README's mutation table claims three defects are caught by "the
    // generator refuses". Until this ran, every one of those refusal branches
    // could be deleted without a single test noticing.
    assert.throws(() => construct({ ...CANON, ...spec }), expected);
  });
}

test('a second, non-canonical mark passes every gate it should', () => {
  // Guards against the opposite failure: gates so strict that only CANON can
  // satisfy them would make the whole construction a spec of one.
  const { failed, applicable } = verdict(construct({ ...CANON, N: 5, span: 2 }));
  assert.deepEqual(failed.map((f) => f.name), []);
  assert.ok(applicable >= 15, `only ${applicable} gates applied to N5 span2`);
});

test('constant width applies to the Reuleaux cases and not to the others', () => {
  const widthOf = (spec) =>
    check(construct({ ...CANON, ...spec })).find(
      (r) => r.name === 'the closed curve has the same width in every direction',
    );
  for (const spec of [{}, { N: 5, span: 2 }, { N: 7, span: 3 }]) {
    const r = widthOf(spec);
    assert.ok(r.applies && r.ok, `${JSON.stringify(spec)}: ${r.detail}`);
  }
  for (const spec of [{ N: 4, span: 1 }, { N: 5, span: 1 }]) {
    assert.equal(widthOf(spec).applies, false, `${JSON.stringify(spec)} should not apply`);
  }
});

test('the precision search returns the smallest precision that works', () => {
  // The search's result was tested; the search was not. `if (worst <= TARGET)
  // return decimals` mutated to `true` survives against CANON alone, because
  // CANON needs exactly the floor.
  const cases = [[{}, 4], [{ N: 5, span: 2 }, 5], [{ N: 9, span: 4 }, 7]];
  for (const [spec, expected] of cases) {
    assert.equal(construct({ ...CANON, ...spec }).derived.precision, expected, JSON.stringify(spec));
  }
});

/* ------------------------------------------------ tolerances, from both sides */

/**
 * Near-miss corruptions: perturb a valid geometry by just over each gate's
 * tolerance, and by just under it.
 *
 * The gates above can only be fed specs, and a spec cannot put a source off the
 * basis circle — the construction derives it there. So those gates had no
 * reachable failure at all, and mutation testing found the obvious consequence:
 * replacing the condition with `true` survives, because nothing constructible
 * distinguishes a working check from one that always passes.
 *
 * Perturbing the geometry object directly reaches what a spec cannot. Checking
 * *both* sides is what makes the tolerance itself the subject: over must fail,
 * under must pass. Loosen a tolerance and the over case stops failing; tighten
 * it and the under case starts. A gate that always returns true fails the first
 * immediately.
 *
 * The magnitudes below are measured, not assumed — each was found by sweeping
 * until the gate flipped, which is also how the `sources lie on the basis
 * circle` entry got its `at.y`: perturbing `at.x` at the apex is a tangential
 * move, and a radial-distance check is right to report zero error for it.
 */
const NEAR_MISS = [
  ['sources lie on the basis circle', 1e-12, (g, d) => { g.sources[0].at.y += d; }],
  ['the wavefront radius is the distance to the peers it reaches', 1e-12,
    (g, d) => { g.derived.side += d; }, 'peer spacing'],
  // The radius half of that gate needs its own probe. Until a named mutation
  // run reported the gate by the wrong name, it compared peer spacing to
  // `side` and never looked at an arc's radius at all — so half of what its
  // title claims was unchecked, and perturbing `side` alone cannot tell.
  ['the wavefront radius is the distance to the peers it reaches', 1e-12,
    (g, d) => { g.wavefronts[0].r += d; }, 'arc radius'],
  // 1e-4, not 1e-12: this gate compares coordinates rounded to four decimals,
  // so its real tolerance is four orders looser than it looks in the source.
  ['the mark maps onto itself under rotation by 360/N', 1e-4,
    (g, d) => { g.sources[0].at.x += d; }],
  ['untrimmed, each wavefront lands on both its peers', 1e-12,
    (g, d) => { g.wavefronts[0].touches[0].x += d; }],
  ['each wavefront is trimmed back by exactly the gap', 1e-12,
    (g, d) => { g.wavefronts[0].from.x += d; }],
  ['every drawn arc is centred on a source', 1e-4,
    (g, d) => { g.wavefronts[0].from.y += d; }],
  ['the ink stays inside the clear space', 1e-9, (g, d) => { g.derived.clearance += d; }],
  // 1e-9, not 1e-4: the support function is now exact rather than sampled, so
  // the gate was tightened five orders and this magnitude had to follow it.
  ['the closed curve has the same width in every direction', 1e-9,
    (g, d) => { g.wavefronts[0].r += d; }],
];

const corrupted = (perturb, amount) => {
  // structuredClone drops the freeze and preserves shared references, so a
  // source and the wavefront centred on it move together, as they would.
  const copy = structuredClone(construct(CANON));
  perturb(copy, amount);
  return check(copy);
};

for (const [gate, tolerance, perturb, label] of NEAR_MISS) {
  const who = label ? `${gate} [${label}]` : gate;
  test(`${who}: fails ${tolerance * 10} past tolerance`, () => {
    const r = corrupted(perturb, tolerance * 10).find((x) => x.name === gate);
    assert.ok(r.applies, `gate stopped applying rather than failing: ${r.detail}`);
    assert.equal(r.ok, false, `tolerance is looser than stated: ${r.detail}`);
  });

  test(`${who}: still passes ${tolerance / 10} inside tolerance`, () => {
    const r = corrupted(perturb, tolerance / 10).find((x) => x.name === gate);
    assert.ok(r.applies && r.ok, `tolerance is tighter than stated: ${r.detail}`);
  });
}

test('two arcs sharing a centre is caught', () => {
  const copy = structuredClone(construct(CANON));
  copy.wavefronts[1] = structuredClone(copy.wavefronts[0]);
  const r = check(copy).find((x) => x.name === 'no two drawn arcs share a centre');
  assert.equal(r.ok, false, r.detail);
});

/* ---------------------------------------------------------- the artefact */

test('the committed files are what the generator produces', () => {
  // build.mjs is the only way these change. If this fails, something was
  // hand-edited, and a hand-edited coordinate is exactly the class of defect
  // the rest of this file exists to make impossible.
  for (const [path, expected] of Object.entries(outputs())) {
    assert.equal(readFileSync(path, 'utf8'), expected, `${path} is stale; run build.mjs`);
  }
});

test('the icon states the accent from tokens.css and nothing else', () => {
  const { light, dark } = accents();
  const svg = readFileSync(PATHS.icon, 'utf8');
  assert.match(svg, new RegExp(`:root \\{ color: ${light}; \\}`));
  assert.match(svg, new RegExp(`prefers-color-scheme: dark\\) \\{ :root \\{ color: ${dark}; \\}`));
  const literals = new Set([...svg.matchAll(/#[0-9a-fA-F]{3,8}/g)].map((m) => m[0]));
  assert.deepEqual([...literals].sort(), [light, dark].sort());
});

test('the app bar carries the generated glyph, not a copy of it', () => {
  assert.ok(readFileSync(PATHS.index, 'utf8').includes(glyph(' '.repeat(10))));
});

/* ------------------------------------------------------------ the raster */

test('the touch icon rasterised to the mark and not to an empty square', () => {
  const image = decodePng(readFileSync(RASTER.out));
  assert.equal(image.width, RASTER.size);
  assert.equal(image.height, RASTER.size);

  const css = readFileSync(PATHS.tokens, 'utf8');
  const background = rgb(/--bg:\s*(#[0-9a-fA-F]{6})/.exec(css)[1]);
  const foreground = rgb(accents(css).light);

  // The corners are outside the clear space and the centre is inside the
  // curve, where the mark draws nothing. Both must be background, so a solid
  // fill and an empty canvas both fail.
  for (const [x, y] of [[0, 0], [RASTER.size - 1, 0], [0, RASTER.size - 1], [95, 95]]) {
    assert.ok(distance(pixelAt(image, x, y), background) < 8, `pixel ${x},${y} is not background`);
  }

  let ink = 0;
  for (let y = 0; y < image.height; y += 1) {
    for (let x = 0; x < image.width; x += 1) {
      if (distance(pixelAt(image, x, y), foreground) < 40) ink += 1;
    }
  }
  const fraction = ink / (image.width * image.height);
  // Measured 0.1185 at 192 px under Chromium 1194. The band is wide because
  // antialiasing and colour management differ between renderers; it is here to
  // catch a rasteriser that drew nothing or everything, not to pin a number.
  assert.ok(fraction > 0.04 && fraction < 0.2, `ink fraction ${fraction.toFixed(4)}`);
});

test('the committed PNG is encoded the way this repo encodes PNGs', () => {
  // Round-trip: decode the committed icon and re-encode its own pixels. This
  // is stable across Chromium versions in a way a fresh rasterisation is not,
  // because it never re-renders — it only asserts that whatever pixels are on
  // disk were written with our encoder settings.
  //
  // It exists because mutation testing showed the ENCODE object in png.mjs
  // could be emptied with nothing noticing. That object is what keeps the icon
  // at 4,178 bytes instead of 6,182: pngjs defaults to adaptive filtering and
  // the Z_RLE strategy, which are wrong for flat two-colour art. The byte
  // budget below checks the committed file; this checks the encoder that made
  // it, and only together do they catch a regression in either.
  const onDisk = readFileSync(RASTER.out);
  const reencoded = encodePng(decodePng(onDisk));
  assert.deepEqual(
    reencoded,
    onDisk,
    `re-encoding the committed pixels gives ${reencoded.length} bytes, not the ${onDisk.length} on disk`,
  );
});

test('the rasteriser refuses a crop that caught the page instead of the icon', () => {
  // The guard lives in rasterise.mjs, which no browserless test reaches, and it
  // guards a condition that cannot be induced on demand — asking Chromium for a
  // 4096px icon just yields a 4096px icon. Extracting it makes the logic
  // testable here. Whether a real viewport ever trips it stays unverified, and
  // that is a smaller unknown than the whole guard being unexercised.
  const size = 8;
  const flat = (r, g, b) => ({
    width: size, height: size, channels: 4,
    pixels: Uint8Array.from({ length: size * size * 4 }, (_, i) => [r, g, b, 255][i % 4]),
  });
  const good = flat(0xf6, 0xf5, 0xf2);
  assert.doesNotThrow(() => assertCropCaughtTheIcon(good, size));
  for (const corner of [0, size - 1, size * (size - 1), size * size - 1]) {
    const bad = flat(0xf6, 0xf5, 0xf2);
    bad.pixels.set([255, 255, 255], corner * 4);
    assert.throws(() => assertCropCaughtTheIcon(bad, size), /viewport smaller than/);
  }
});

test('the touch icon stays inside its byte budget', () => {
  // A budget, not a derived quantity, and the only gate here that watches the
  // size of what we ship. It exists because swapping the hand-rolled PNG
  // encoder for pngjs inflated this file from 4,178 to 6,182 bytes — the
  // library's defaults are tuned for photographs — and all 22 other gates
  // passed without noticing. 6,144 is 1.5x the current size: loose enough for
  // renderer drift, tight enough to have caught that.
  const bytes = readFileSync(RASTER.out).length;
  assert.ok(bytes <= 6144, `icon-192.png is ${bytes} bytes, over the 6144 budget`);
});

test('the rasterised mark is mirror-symmetric about its vertical axis', () => {
  // Conditional, and it took the explorer to notice. This holds because CANON
  // puts a source at phase -90, on the vertical axis. Spin the same mark to
  // phase 0 and it is still a correct mark with no vertical mirror at all, so
  // asserting this unconditionally would be asserting a fact about one spec.
  assert.ok(geo && hasVerticalMirror(geo), 'CANON no longer has a vertical mirror to check');

  const image = decodePng(readFileSync(RASTER.out));
  let mismatched = 0;
  for (let y = 0; y < image.height; y += 1) {
    for (let x = 0; x < image.width / 2; x += 1) {
      if (distance(pixelAt(image, x, y), pixelAt(image, image.width - 1 - x, y)) > 12) {
        mismatched += 1;
      }
    }
  }
  const fraction = mismatched / ((image.width / 2) * image.height);
  assert.ok(fraction < 0.005, `${(fraction * 100).toFixed(2)}% of pixels break mirror symmetry`);
});
