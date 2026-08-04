/*
 * Copyright 2026 The dcisim Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * SVG's endpoint-to-centre arc conversion (spec F.6.5), circular case.
 *
 * Its own module because two callers need it and neither should own it:
 * construct.mjs uses it to decide how many decimals an arc has to be emitted
 * at before a renderer would put it back where the construction says, and
 * invariants.mjs uses it to check that a committed file still does. Those are
 * different jobs and the README says plainly that they share an implementation.
 */

/** @returns {{x:number, y:number, r:number}} the centre a renderer would use */
export function centreOf(d) {
  const m =
    /^M(-?[\d.]+) (-?[\d.]+)A(-?[\d.]+) (-?[\d.]+) 0 ([01]) ([01]) (-?[\d.]+) (-?[\d.]+)$/.exec(d);
  if (!m) throw new Error(`unparsed path: ${d}`);
  const [x1, y1, rx, ry, fA, fS, x2, y2] = m.slice(1).map(Number);
  if (rx !== ry) throw new Error('the mark has no elliptical arcs');
  const dx = (x1 - x2) / 2;
  const dy = (y1 - y2) / 2;
  const numerator = rx ** 4 - rx ** 2 * dy ** 2 - rx ** 2 * dx ** 2;
  const denominator = rx ** 2 * dy ** 2 + rx ** 2 * dx ** 2;
  const factor = Math.sqrt(Math.max(0, numerator / denominator)) * (fA !== fS ? 1 : -1);
  return { x: factor * dy + (x1 + x2) / 2, y: -factor * dx + (y1 + y2) / 2, r: rx };
}
