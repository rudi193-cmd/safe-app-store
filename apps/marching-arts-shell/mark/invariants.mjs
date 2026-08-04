/*
 * Copyright 2026 The dcisim Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * What the mark claims, as predicates over a geometry rather than assertions
 * about one logo. construct.test.mjs runs these against CANON; explore.mjs
 * runs them against everything else. That split is the point: an invariant
 * that only ever saw one mark cannot tell you whether it is a property of the
 * construction or a property of that mark, and until this file existed every
 * invariant here was in the second category without anyone knowing which.
 *
 * Each check reports `applies` separately from `ok`. A check that does not
 * apply to a spec is not a pass, and rolling the two together is how a
 * conditional invariant gets quoted as if it were universal.
 */

import { elements, extent, fold, samples } from './construct.mjs';
import { centreOf } from './endpoint.mjs';

export { centreOf };

const RAD = Math.PI / 180;
const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
const bearing = (from, to) => Math.atan2(to.y - from.y, to.x - from.x) / RAD;

/** Is `point` on the drawn part of `arc`, as opposed to on its circle? */
function withinSweep(arc, point, tolerance = 1e-9) {
  const delta = fold(bearing(arc.centre, point) - arc.startBearing);
  const swept = arc.sweptDegrees;
  return swept > 0
    ? delta >= -tolerance && delta <= swept + tolerance
    : delta <= tolerance && delta >= swept - tolerance;
}

/**
 * Distance from a point to a drawn arc, in closed form. The furthest/nearest
 * point on a circle in a given direction is exact; the only question is whether
 * it lies on the drawn span, and if not the nearest point is an endpoint.
 *
 * This replaces comparing every sample on one arc against every sample on
 * another, which was O(samples squared) per pair and made the suite take 21
 * seconds — long enough that a mutation run over it needed more than an hour.
 */
function distanceToArc(point, arc) {
  const delta = fold(bearing(arc.centre, point) - arc.startBearing);
  const swept = arc.sweptDegrees;
  const onSpan = swept > 0 ? delta >= 0 && delta <= swept : delta <= 0 && delta >= swept;
  if (onSpan) return Math.abs(dist(point, arc.centre) - arc.r);
  return Math.min(dist(point, arc.from), dist(point, arc.to));
}

/** Where two equal-radius circles meet, if they meet. */
function circleIntersections(c1, c2, r) {
  const d = dist(c1, c2);
  if (d === 0 || d > 2 * r) return [];
  const h = Math.sqrt(Math.max(0, r * r - (d / 2) ** 2));
  const mid = { x: (c1.x + c2.x) / 2, y: (c1.y + c2.y) / 2 };
  const u = { x: -(c2.y - c1.y) / d, y: (c2.x - c1.x) / d };
  return [
    { x: mid.x + h * u.x, y: mid.y + h * u.y },
    { x: mid.x - h * u.x, y: mid.y - h * u.y },
  ];
}

/** Does the source set map onto itself under x -> box - x? */
export function hasVerticalMirror(geo, tolerance = 1e-3) {
  const key = (p) => `${p.x.toFixed(4)},${p.y.toFixed(4)}`;
  const original = new Set(geo.sources.map((s) => key(s.at)));
  return geo.sources.every((s) => {
    const mirrored = { x: geo.derived.box - s.at.x, y: s.at.y };
    return [...original].some((k) => {
      const [x, y] = k.split(',').map(Number);
      return Math.abs(x - mirrored.x) < tolerance && Math.abs(y - mirrored.y) < tolerance;
    });
  });
}

/**
 * @returns {Array<{name:string, applies:boolean, ok:boolean, detail:string}>}
 */
export function check(geo) {
  const d = geo.derived;
  const results = [];
  const add = (name, ok, detail = '', applies = true) =>
    results.push({ name, applies, ok: applies ? ok : false, detail });

  /* ---- the sources ---- */

  const offCircle = Math.max(...geo.sources.map((s) => Math.abs(dist(s.at, d.center) - d.R)));
  add('sources lie on the basis circle', offCircle < 1e-12, `worst ${offCircle.toExponential(2)}`);

  const spacings = geo.sources.map((s, i) => dist(s.at, geo.sources[(i + d.span) % d.N].at));
  const spacingError = Math.max(...spacings.map((v) => Math.abs(v - d.side)));
  // The radius half was missing until a named mutation run reported this gate
  // by the wrong name: setting a wavefront's r to 1.01 * side was caught by
  // half the suite and not by the one check whose title says it covers exactly
  // that. It compared peer spacing to `side` and never looked at any arc.
  const radiusError = Math.max(...geo.wavefronts.map((w) => Math.abs(w.r - d.side)));
  add(
    'the wavefront radius is the distance to the peers it reaches',
    Math.max(spacingError, radiusError) < 1e-12,
    `spacing ${spacingError.toExponential(2)}, radius ${radiusError.toExponential(2)}`,
  );

  const turn = ((360 / d.N) * Math.PI) / 180;
  const key = (p) => `${p.x.toFixed(4)},${p.y.toFixed(4)}`;
  const before = new Set(geo.sources.map((s) => key(s.at)));
  const after = geo.sources.map((s) => {
    const dx = s.at.x - d.center.x;
    const dy = s.at.y - d.center.y;
    return key({
      x: d.center.x + dx * Math.cos(turn) - dy * Math.sin(turn),
      y: d.center.y + dx * Math.sin(turn) + dy * Math.cos(turn),
    });
  });
  add(
    'the mark maps onto itself under rotation by 360/N',
    after.every((k) => before.has(k)),
    `order ${d.N}`,
  );

  /* ---- the wavefronts ---- */

  const missesPeer = Math.max(
    ...geo.wavefronts.flatMap((w) => w.touches.map((p) => Math.abs(dist(w.centre, p) - w.r))),
  );
  add('untrimmed, each wavefront lands on both its peers', missesPeer < 1e-12,
    `worst ${missesPeer.toExponential(2)}`);

  const trimError = Math.max(
    ...geo.wavefronts.flatMap((w) => [
      Math.abs(dist(w.from, w.touches[0]) - d.gap),
      Math.abs(dist(w.to, w.touches[1]) - d.gap),
    ]),
  );
  add('each wavefront is trimmed back by exactly the gap', trimError < 1e-12,
    `worst ${trimError.toExponential(2)}`);

  add(
    'the gap leaves the source it lands on visible',
    d.gap > d.source + d.stroke / 2,
    `gap ${d.gap.toFixed(3)} vs dot+cap ${(d.source + d.stroke / 2).toFixed(3)}`,
  );

  /* ---- the drawn artefact, read back ---- */

  const drawn = elements(geo).paths.map((p) => centreOf(/ d="([^"]+)"/.exec(p)[1]));
  const worstCentre = Math.max(
    ...drawn.map((a) => Math.min(...geo.sources.map((s) => dist(a, s.at)))),
  );
  add('every drawn arc is centred on a source', worstCentre < 1e-3, `worst ${worstCentre.toFixed(6)}`);

  const distinct = new Set(drawn.map((a) => `${a.x.toFixed(4)},${a.y.toFixed(4)}`));
  add('no two drawn arcs share a centre', distinct.size === d.N, `${distinct.size} of ${d.N}`);

  /* ---- legibility: nothing here was checked before the explorer existed ---- */

  let crossings = 0;
  for (let i = 0; i < geo.wavefronts.length; i += 1) {
    for (let j = i + 1; j < geo.wavefronts.length; j += 1) {
      const a = geo.wavefronts[i];
      const b = geo.wavefronts[j];
      for (const p of circleIntersections(a.centre, b.centre, a.r)) {
        if (withinSweep(a, p, 1e-6) && withinSweep(b, p, 1e-6)) crossings += 1;
      }
    }
  }
  add('no wavefront crosses another', crossings === 0, `${crossings} crossing(s)`);

  const sampled = geo.wavefronts.map((w) => samples(w, 400));
  let closest = Infinity;
  for (let i = 0; i < sampled.length; i += 1) {
    for (let j = 0; j < geo.wavefronts.length; j += 1) {
      if (i === j) continue;
      for (const p of sampled[i]) closest = Math.min(closest, distanceToArc(p, geo.wavefronts[j]));
    }
  }
  add(
    'wavefronts stay a stroke apart from each other',
    closest >= d.stroke,
    `closest ${closest === Infinity ? 'n/a' : closest.toFixed(3)} vs stroke ${d.stroke}`,
    geo.wavefronts.length > 1,
  );

  // A wavefront shorter than the line is thick is swallowed by its own round
  // caps and renders as a dot. Every other invariant here is satisfied by such
  // a mark — N 7 span 3 and N 9 span 4 passed all twelve while drawing a ring
  // of dots — because correctness of a construction says nothing about whether
  // the thing constructed is still legible as what it depicts.
  const arcLength = d.side * d.sweep * RAD;
  add(
    'each wavefront is longer than the stroke is thick',
    arcLength >= d.stroke,
    `arc ${arcLength.toFixed(3)} vs stroke ${d.stroke}`,
  );

  let nearestSource = Infinity;
  for (const arc of sampled) {
    for (const p of arc) {
      for (const s of geo.sources) nearestSource = Math.min(nearestSource, dist(p, s.at));
    }
  }
  add(
    'no wavefront runs through a source',
    nearestSource >= d.source + d.stroke / 2,
    `nearest ${nearestSource.toFixed(3)} vs dot+cap ${(d.source + d.stroke / 2).toFixed(3)}`,
  );

  /* ---- the grid ---- */

  const ink = extent(geo);
  const margins = {
    left: ink.minX,
    top: ink.minY,
    right: d.box - ink.maxX,
    bottom: d.box - ink.maxY,
  };
  const tightest = Math.min(...Object.values(margins));
  add(
    'the ink stays inside the clear space',
    tightest >= d.clearance - 1e-9,
    `tightest margin ${tightest.toFixed(4)} vs clearance ${d.clearance}`,
  );
  add(
    'the grid is no larger than the mark needs',
    // Met exactly, which is what makes the box derived rather than merely
    // large enough. It holds whenever a source lands on one of the four axes
    // the box formula assumes the extreme ink sits on — true at phase -90, 0
    // and 30 for N 3, and false at phase 15, where the same mark floats in a
    // box 0.82 larger than it asked for.
    Math.abs(tightest - d.clearance) < 1e-9,
    `slack ${(tightest - d.clearance).toFixed(4)}`,
  );

  /* ---- constant width: only ever true for the Reuleaux case ---- */

  const isReuleaux = d.N % 2 === 1 && d.span === (d.N - 1) / 2;
  if (isReuleaux) {
    // Exact, not sampled. The furthest point of a circle in direction u is
    // centre + r*u, and it lies on the arc exactly when u's bearing falls in
    // the arc's span; otherwise the extreme is an endpoint. Sampling this used
    // to dominate the suite's runtime and carried an "only ever undershoots"
    // caveat that no longer applies.
    const support = (deg) => {
      const u = { x: Math.cos(deg * RAD), y: Math.sin(deg * RAD) };
      const project = (p) => (p.x - d.center.x) * u.x + (p.y - d.center.y) * u.y;
      let best = -Infinity;
      for (const w of geo.wavefronts) {
        const start = bearing(w.centre, w.touches[0]);
        const swept = fold(bearing(w.centre, w.touches[1]) - start);
        const delta = fold(deg - start);
        const onSpan = swept > 0 ? delta >= 0 && delta <= swept : delta <= 0 && delta >= swept;
        if (onSpan) best = Math.max(best, project(w.centre) + w.r);
        for (const p of w.touches) best = Math.max(best, project(p));
      }
      return best;
    };
    let worst = 0;
    for (let deg = 0; deg < 360; deg += 1) {
      worst = Math.max(worst, Math.abs(support(deg) + support(deg + 180) - d.side));
    }
    add('the closed curve has the same width in every direction', worst < 1e-9,
      `worst ${worst.toExponential(2)}`);
  } else {
    add('the closed curve has the same width in every direction', false,
      `needs odd N with span (N-1)/2; this is N ${d.N} span ${d.span}`, false);
  }

  return results;
}

/** Only the checks that apply, and whether all of them held. */
export function verdict(geo) {
  const results = check(geo);
  const applicable = results.filter((r) => r.applies);
  return {
    results,
    applicable: applicable.length,
    failed: applicable.filter((r) => !r.ok),
    ok: applicable.every((r) => r.ok),
  };
}
