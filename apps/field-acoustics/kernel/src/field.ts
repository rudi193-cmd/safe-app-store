/**
 * Field and stadium geometry. Port of `dcisim/field.py`.
 *
 * Coordinates are in feet:
 *   x  0 at the 50, negative toward side 1, positive toward side 2.
 *   y  0 at the front sideline, increasing upfield. Back sideline at 160.
 *   z  0 at the field surface, positive up.
 *
 * The audience lives at negative y on a raked grandstand. Metres are used
 * internally by the propagation engine; feet stay at the edges.
 */

import { N_BANDS } from './atmosphere.js';

export const FT_PER_M = 3.280839895;
export const STEP_FT = 22.5 / 12.0; // 8-to-5 marching step

export const FIELD_LENGTH_FT = 300.0;
export const FIELD_WIDTH_FT = 160.0;
export const FRONT_HASH_FT = 60.0;
export const BACK_HASH_FT = 100.0;
export const FIELD_CENTER: readonly [number, number] = [0.0, FIELD_WIDTH_FT / 2.0];

/** A raked grandstand along the front sideline plus an optional far-side reflector. */
export interface Stadium {
  apronFt: number;
  nRows: number;
  rowDepthFt: number;
  rowRiseFt: number;
  firstRowHeightFt: number;
  earHeightFt: number;
  halfWidthFt: number;
  seatsAcross: number;

  farSide: boolean;
  farSideSetbackFt: number;
  farSideHeightFt: number;
  /** Absorption coefficient per octave band for the far-side face. */
  farSideAbsorption: readonly number[];
}

export const DEFAULT_STADIUM: Readonly<Stadium> = Object.freeze({
  apronFt: 25.0,
  nRows: 40,
  rowDepthFt: 2.6,
  rowRiseFt: 1.35,
  firstRowHeightFt: 3.0,
  earHeightFt: 3.6,
  halfWidthFt: 165.0,
  seatsAcross: 41,
  farSide: true,
  farSideSetbackFt: 30.0,
  farSideHeightFt: 45.0,
  farSideAbsorption: Object.freeze([0.45, 0.55, 0.7, 0.8, 0.85, 0.85, 0.85, 0.85]),
});

export function makeStadium(overrides: Partial<Stadium> = {}): Stadium {
  const s = { ...DEFAULT_STADIUM, ...overrides } as Stadium;
  if (s.farSideAbsorption.length !== N_BANDS) {
    throw new RangeError(
      `far-side absorption needs ${N_BANDS} band values, got ${s.farSideAbsorption.length}`,
    );
  }
  return s;
}

export function farSidePlaneYFt(s: Stadium): number {
  return FIELD_WIDTH_FT + s.farSideSetbackFt;
}

export interface SeatGrid {
  /** (nSeats * 3) flat, feet. */
  points: Float64Array;
  xs: Float64Array;
  rows: Int32Array;
  count: number;
}

/** Receiver positions for every seat, flattened to (n, 3) in feet. */
export function seatGrid(s: Stadium): SeatGrid {
  const nx = s.seatsAcross;
  const nr = s.nRows;
  const xs = new Float64Array(nx);
  if (nx === 1) {
    xs[0] = -s.halfWidthFt;
  } else {
    const step = (2 * s.halfWidthFt) / (nx - 1);
    for (let i = 0; i < nx; i++) xs[i] = -s.halfWidthFt + i * step;
    xs[nx - 1] = s.halfWidthFt;
  }
  const rows = new Int32Array(nr);
  for (let i = 0; i < nr; i++) rows[i] = i;

  // numpy meshgrid(xs, rows, indexing='ij') then ravel: x varies slowest.
  const points = new Float64Array(nx * nr * 3);
  let k = 0;
  for (let i = 0; i < nx; i++) {
    for (let j = 0; j < nr; j++) {
      points[k++] = xs[i];
      points[k++] = -(s.apronFt + j * s.rowDepthFt);
      points[k++] = s.firstRowHeightFt + j * s.rowRiseFt + s.earHeightFt;
    }
  }
  return { points, xs, rows, count: nx * nr };
}

/**
 * A few reference seats worth quoting in a report. Row indices are clamped to
 * the stand that actually exists, so a short grandstand reports real seats.
 */
export function namedSeats(s: Stadium): Map<string, [number, number, number]> {
  if (s.nRows < 1) {
    throw new RangeError(`a grandstand needs at least one row, got ${s.nRows}`);
  }
  const top = s.nRows - 1;
  const low = Math.min(3, top);
  const mid = Math.min(Math.max(Math.floor(s.nRows / 2), low), top);

  const seat = (x: number, row: number): [number, number, number] => [
    x,
    -(s.apronFt + row * s.rowDepthFt),
    s.firstRowHeightFt + row * s.rowRiseFt + s.earHeightFt,
  ];

  const out = new Map<string, [number, number, number]>();
  for (const [label, x, row] of [
    ['low 50', 0.0, low],
    ['mid 50', 0.0, mid],
    ['high 50', 0.0, top],
    ['corner side 2', 120.0, mid],
  ] as [string, number, number][]) {
    out.set(`${label} (row ${row})`, seat(x, row));
  }
  return out;
}

export function yardsToX(yardLine: number, side: string | number): number {
  const offset = (50.0 - yardLine) * 3.0;
  return String(side) === '1' ? -offset : offset;
}

export function stepsFromSideline(nSteps: number): number {
  return nSteps * STEP_FT;
}
