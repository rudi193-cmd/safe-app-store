/*
 * Copyright 2026 The dcisim Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * The mark, constructed.
 *
 * Every coordinate is derived from a spec of eight numbers. Nothing is placed
 * by eye and nothing is a number someone liked the look of; even the viewBox is
 * a consequence rather than a choice. If a value cannot be traced back to the
 * spec through the code in this file, it does not belong in the mark.
 *
 * CANON is the dcisim mark. The spec is open so that other marks can be built
 * from the same construction and put through the same gates — see explore.mjs,
 * and README.md for which invariants turn out to hold for all of them and
 * which only ever held for this one.
 */

import { centreOf } from './endpoint.mjs';

/** The dcisim mark. Changing anything here changes the logo. */
export const CANON = Object.freeze({
  /** Order of rotational symmetry, and of the inscribed regular polygon. */
  N: 3,
  /** Radius of the basis circle. The only free length in the mark. */
  R: 24,
  /**
   * How far round the polygon each wavefront reaches: the arc centred on one
   * source is drawn between the sources `span` places either side of it. 1 is
   * the adjacent pair. For odd N, span = (N-1)/2 is the opposite pair and the
   * arcs close into a Reuleaux polygon of constant width.
   */
  span: 1,
  /** Bearing of the first source. -90 puts it at the top, upright. */
  phase: -90,
  /** Source dot radius, as R / sourceRatio. */
  sourceRatio: 6,
  /** Stroke weight, as a multiple of the source radius. */
  strokeRatio: 1,
  /** Chord each wavefront is trimmed back by, as a multiple of the source radius. */
  gapRatio: 2,
  /** Clear space demanded outside the ink, as a multiple of the source radius. */
  clearRatio: 1,
});

const RAD = Math.PI / 180;

/**
 * Emission precision. Four decimals is the floor and was, for a long time, the
 * only value — which made it an unexamined property of the canonical mark
 * rather than of the construction. Recovering an arc's centre from rounded
 * endpoints is ill-conditioned in proportion to how shallow the arc is: at
 * N 3 span 1 the recovered centre lands 7e-5 from its source, at N 7 span 3
 * 5.9e-4 away, and at N 9 span 4 5.6e-3 away — past the 1e-3 the invariant
 * allows, for a construction exactly as correct as the other two. So the
 * precision is searched for rather than assumed, and a spec whose arcs cannot
 * be encoded at any precision is refused instead of emitted.
 */
const MIN_PRECISION = 4;
const MAX_PRECISION = 12;
/** An order of magnitude under the tolerance the invariant checks at. */
const RECOVERY_TARGET = 1e-4;

export function derive(spec) {
  const { N, R, span, sourceRatio, strokeRatio, gapRatio, clearRatio } = { ...CANON, ...spec };

  if (!Number.isInteger(N) || N < 3) throw new Error(`N must be an integer >= 3, got ${N}`);
  if (!Number.isInteger(span) || span < 1) {
    throw new Error(`span must be an integer >= 1, got ${span}`);
  }
  if (2 * span >= N) {
    // At 2*span === N the two peers are the same point diametrically opposite
    // and the aperture is zero; beyond it the arc runs backwards. Refuse
    // rather than emit a path whose sweep is negative and whose flags lie.
    throw new Error(`span ${span} needs 2*span < N, got N = ${N}`);
  }

  const source = R / sourceRatio;
  /** Distance from a source to the peers it reaches: the wavefront radius. */
  const side = 2 * R * Math.sin((Math.PI * span) / N);
  /**
   * Angle the two peers subtend at the source between them. Inscribed angle
   * over the arc they cut off that does not contain it, so 180(N - 2*span)/N.
   * For span 1 this is the polygon's interior angle.
   */
  const aperture = (180 * (N - 2 * span)) / N;
  const gap = source * gapRatio;

  if (gap >= side) throw new Error(`gap ${gap} cannot exceed the wavefront radius ${side}`);
  const trim = (2 * Math.asin(gap / (2 * side))) / RAD;
  if (2 * trim >= aperture) {
    throw new Error(
      `trim ${trim.toFixed(3)} deg twice over exceeds the ${aperture.toFixed(3)} deg aperture: nothing is left to draw`,
    );
  }

  const clearance = source * clearRatio;
  return Object.freeze({
    ...{ N, R, span, sourceRatio, strokeRatio, gapRatio, clearRatio },
    center: Object.freeze({ x: R + source + clearance, y: R + source + clearance }),
    source,
    stroke: source * strokeRatio,
    side,
    aperture,
    gap,
    trim,
    sweep: aperture - 2 * trim,
    clearance,
    /**
     * Design grid. Derived: the ink reaches R + source from the centre and the
     * clear space is one further clearance, so the box follows from the mark
     * rather than the mark being fitted into a box someone chose.
     */
    box: 2 * (R + source + clearance),
  });
}

function polar(from, radius, deg) {
  return {
    x: from.x + radius * Math.cos(deg * RAD),
    y: from.y + radius * Math.sin(deg * RAD),
  };
}

function bearing(from, to) {
  return Math.atan2(to.y - from.y, to.x - from.x) / RAD;
}

/** Degrees folded into (-180, 180]. */
export function fold(degrees) {
  let d = degrees % 360;
  if (d > 180) d -= 360;
  if (d <= -180) d += 360;
  return d;
}

/**
 * The full construction. Angles are degrees measured from +x and increasing
 * toward +y, which is downward, as SVG has it.
 *
 * The N sources sit on the basis circle at the vertices of the inscribed
 * regular N-gon. Each wavefront is the circle centred on one source with
 * radius equal to the distance to the peers it reaches — the wavefront leaving
 * that source at the instant it arrives at them — drawn only over the span
 * between them, and trimmed back by `gap` at each end so it visibly arrives at
 * a source rather than merging into it.
 */
export function construct(spec = CANON) {
  const d = derive(spec);
  const { N, R, span, phase } = { ...CANON, ...spec };
  const O = d.center;

  const sources = Array.from({ length: N }, (_, index) => ({
    index,
    angle: phase + (360 / N) * index,
    at: polar(O, R, phase + (360 / N) * index),
  }));

  const wavefronts = sources.map((src) => {
    const from = sources[(src.index - span + N) % N].at;
    const to = sources[(src.index + span) % N].at;
    const fromBearing = bearing(src.at, from);
    const toBearing = bearing(src.at, to);

    // The drawn sweep runs from `from` to `to` the short way. Interpolating
    // raw atan2 output instead wraps the long way round for some sources and
    // traces a circle that is not the curve; that mistake is why this is
    // asserted here rather than assumed downstream.
    const swept = fold(toBearing - fromBearing);
    if (Math.abs(Math.abs(swept) - d.aperture) > 1e-9) {
      throw new Error(
        `source ${src.index}: peers subtend ${Math.abs(swept)} deg, not the derived ${d.aperture}`,
      );
    }
    const direction = Math.sign(swept);

    return {
      centre: src.at,
      r: d.side,
      /* the untrimmed ends: the peer sources themselves */
      touches: [from, to],
      from: polar(src.at, d.side, fromBearing + direction * d.trim),
      to: polar(src.at, d.side, toBearing - direction * d.trim),
      startBearing: fromBearing + direction * d.trim,
      sweptDegrees: direction * d.sweep,
      largeArc: d.sweep > 180 ? 1 : 0,
      sweepFlag: direction > 0 ? 1 : 0,
    };
  });

  return {
    spec: { ...CANON, ...spec },
    derived: Object.freeze({ ...d, precision: choosePrecision(wavefronts) }),
    sources,
    wavefronts,
  };
}

/**
 * The fewest decimals at which a renderer, doing SVG's endpoint-to-centre
 * conversion on the emitted string, puts every arc back on the source it is
 * centred on. Measured rather than predicted: the error depends on which way
 * each coordinate happened to round, and a formula fitted to one spec was out
 * by two orders of magnitude on another.
 *
 * This makes `every drawn arc is centred on a source` an enforced property as
 * well as a checked one. The check still earns its place — it catches a
 * hand-edited file, which this cannot — but it is no longer an independent
 * confirmation, and the README says so.
 */
function choosePrecision(wavefronts) {
  for (let decimals = MIN_PRECISION; decimals <= MAX_PRECISION; decimals += 1) {
    const worst = Math.max(
      ...wavefronts.map((w) => {
        const recovered = centreOf(arcPath(w, decimals));
        return Math.hypot(recovered.x - w.centre.x, recovered.y - w.centre.y);
      }),
    );
    if (worst <= RECOVERY_TARGET) return decimals;
  }
  throw new Error(
    `arcs are too shallow to encode: no precision up to ${MAX_PRECISION} decimals puts them back on their centres`,
  );
}

/** Fixed decimal places, no trailing zeros, no negative zero. */
export function n(value, decimals = MIN_PRECISION) {
  const rounded = Number(value.toFixed(decimals));
  return String(Object.is(rounded, -0) ? 0 : rounded);
}

export function arcPath(arc, decimals = MIN_PRECISION) {
  return (
    `M${n(arc.from.x, decimals)} ${n(arc.from.y, decimals)}` +
    `A${n(arc.r, decimals)} ${n(arc.r, decimals)} 0 ${arc.largeArc} ${arc.sweepFlag} ` +
    `${n(arc.to.x, decimals)} ${n(arc.to.y, decimals)}`
  );
}

/**
 * The mark's elements, in paint order: wavefronts first, sources over them, so
 * a source is never split by a line passing beneath it.
 */
export function elements(geo = construct()) {
  const p = geo.derived.precision;
  return {
    paths: geo.wavefronts.map((w) => `<path d="${arcPath(w, p)}" />`),
    dots: geo.sources.map(
      (s) => `<circle cx="${n(s.at.x, p)}" cy="${n(s.at.y, p)}" r="${n(geo.derived.source, p)}" />`,
    ),
  };
}

/**
 * The mark's body: one stroked group, one filled group. Colour is deliberately
 * absent — it is currentColor, so the mark takes the colour of wherever it is
 * put and there is only ever one place a colour gets decided.
 */
export function body(geo = construct(), indent = '') {
  const { paths, dots } = elements(geo);
  const pad = `${indent}  `;
  const width = n(geo.derived.stroke, geo.derived.precision);
  return [
    `${indent}<g fill="none" stroke="currentColor" stroke-width="${width}" stroke-linecap="round">`,
    ...paths.map((p) => pad + p),
    `${indent}</g>`,
    `${indent}<g fill="currentColor" stroke="none">`,
    ...dots.map((d) => pad + d),
    `${indent}</g>`,
  ].join('\n');
}

const boxSize = (geo) => n(geo.derived.box);
const viewBox = (geo) => `0 0 ${boxSize(geo)} ${boxSize(geo)}`;

/** The inline glyph that sits in the app bar beside the wordmark. */
export function glyph(indent = '', geo = construct()) {
  return [
    `${indent}<svg class="wordmark-glyph" viewBox="${viewBox(geo)}" aria-hidden="true" focusable="false">`,
    body(geo, `${indent}  `),
    `${indent}</svg>`,
  ].join('\n');
}

/**
 * The standalone icon. Carries its own colour, because a document referenced
 * by <link rel="icon"> has no parent to inherit one from: currentColor there
 * resolves to black and stays black on a dark tab strip. Both values are
 * --accent from styles/tokens.css, and the test holds them to it.
 */
export function icon({ light, dark }, geo = construct()) {
  const size = boxSize(geo);
  return `${[
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox(geo)}" width="${size}" height="${size}" role="img" aria-label="dcisim">`,
    '  <title>dcisim</title>',
    '  <style>',
    `    :root { color: ${light}; }`,
    `    @media (prefers-color-scheme: dark) { :root { color: ${dark}; } }`,
    '  </style>',
    body(geo, '  '),
    '</svg>',
  ].join('\n')}\n`;
}

/**
 * Flattened for rasterising: explicit colours, opaque background. Used for the
 * touch icon, where the platform composites onto black if handed alpha.
 */
export function raster({ background, foreground }, geo = construct()) {
  const size = boxSize(geo);
  return `${[
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox(geo)}" width="${size}" height="${size}" role="img" aria-label="dcisim">`,
    '  <title>dcisim</title>',
    `  <rect width="${size}" height="${size}" fill="${background}" />`,
    `  <g color="${foreground}">`,
    body(geo, '    '),
    '  </g>',
    '</svg>',
  ].join('\n')}\n`;
}

/** Points along a wavefront's drawn sweep, endpoints included. */
export function samples(arc, steps = 512) {
  return Array.from({ length: steps + 1 }, (_, k) =>
    polar(arc.centre, arc.r, arc.startBearing + (arc.sweptDegrees * k) / steps),
  );
}

/**
 * Every point the ink actually reaches, stroke caps and source radii included.
 * The clear-space invariant is checked against this rather than against the
 * centres, because a cap is ink and an endpoint is not where a stroke stops.
 */
export function extent(geo = construct()) {
  const xs = [];
  const ys = [];
  const half = geo.derived.stroke / 2;

  for (const s of geo.sources) {
    xs.push(s.at.x - geo.derived.source, s.at.x + geo.derived.source);
    ys.push(s.at.y - geo.derived.source, s.at.y + geo.derived.source);
  }

  for (const w of geo.wavefronts) {
    // Sample the swept angle densely; an arc's extreme is not always at an
    // endpoint, and guessing which axis it crosses is how this goes wrong.
    for (const p of samples(w, 1024)) {
      xs.push(p.x - half, p.x + half);
      ys.push(p.y - half, p.y + half);
    }
  }

  return {
    minX: Math.min(...xs),
    maxX: Math.max(...xs),
    minY: Math.min(...ys),
    maxY: Math.max(...ys),
  };
}
