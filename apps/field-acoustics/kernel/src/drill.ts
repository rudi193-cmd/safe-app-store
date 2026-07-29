/**
 * Performer placement and facing. Port of `dcisim/drill.py`.
 *
 * A form is just a list of `Performer` records, so swapping in real drill means
 * writing a CSV with the same columns rather than touching any of the physics.
 *
 * Facing is stored as a vector in the field plane. `applyFacing` rewrites it for
 * the whole ensemble, which is the experiment this simulator exists to run:
 *
 *   "front"   every performer faces the front sideline, bells into the house
 *   "center"  every performer faces the middle of the field
 *   "focus"   every performer faces an arbitrary point you nominate
 *
 * Percussion can be pinned to front-facing independently, since in practice a
 * battery often stays out while the hornline turns in.
 */

import type { Performer } from './engine.js';
import { FIELD_CENTER, STEP_FT } from './field.js';

export type { Performer };

export type FacingMode = 'front' | 'center' | 'focus';

/** A representative modern corps: 50 brass, 19 battery, 8 amplified front ensemble. */
export const DEFAULT_INSTRUMENTATION: readonly [string, number][] = [
  ['trumpet', 16],
  ['mellophone', 12],
  ['baritone', 14],
  ['contra', 8],
];
export const DEFAULT_BATTERY: readonly [string, number][] = [
  ['snare', 9],
  ['tenor', 5],
  ['bass', 5],
];
export const DEFAULT_PIT: readonly [string, number][] = [['pit', 8]];

const BATTERY_NAMES = new Set(['snare', 'tenor', 'bass']);

function normalize(x: number, y: number): [number, number] {
  const n = Math.sqrt(x * x + y * y);
  return n > 1e-9 ? [x / n, y / n] : [0.0, -1.0];
}

/** Return a new performer list with facing rewritten. Does not mutate. */
export function applyFacing(
  performers: readonly Performer[],
  mode: FacingMode = 'front',
  focus: readonly [number, number] = FIELD_CENTER,
  batteryFacesFront = false,
): Performer[] {
  return performers.map((p) => {
    let f: [number, number];
    const isBattery = BATTERY_NAMES.has(p.instrument);
    if (p.instrument === 'pit') {
      f = [0.0, -1.0]; // amplified, always into the house
    } else if (mode === 'front' || (batteryFacesFront && isBattery)) {
      f = [0.0, -1.0];
    } else if (mode === 'center' || mode === 'focus') {
      f = normalize(focus[0] - p.x, focus[1] - p.y);
    } else {
      throw new RangeError(`unknown facing mode: ${JSON.stringify(mode)}`);
    }
    return { instrument: p.instrument, x: p.x, y: p.y, fx: f[0], fy: f[1] };
  });
}

function batteryLine(
  battery: readonly [string, number][],
  y: number,
  dx: number,
  sectionDepthFt = 6.0,
): Performer[] {
  // One centred rank per section. Laying every section end to end in a single
  // rank instead puts the whole snare line on side 1 and the basses onto side 2;
  // that asymmetry leaks into results as if it were a finding.
  const out: Performer[] = [];
  battery.forEach(([name, count], depth) => {
    if (count < 1) return;
    const rowY = y + depth * sectionDepthFt;
    for (let i = 0; i < count; i++) {
      const x = (i - (count - 1) / 2.0) * dx;
      out.push({ instrument: name, x, y: rowY, fx: 0.0, fy: -1.0 });
    }
  });
  return out;
}

function pitLine(pit: readonly [string, number][]): Performer[] {
  const names: string[] = [];
  for (const [n, c] of pit) for (let i = 0; i < c; i++) names.push(n);
  if (names.length === 0) return [];
  const out: Performer[] = [];
  for (let i = 0; i < names.length; i++) {
    const x = names.length > 1 ? -60.0 + (120.0 * i) / (names.length - 1) : 0.0;
    out.push({ instrument: names[i], x, y: -6.0, fx: 0.0, fy: -1.0 });
  }
  if (names.length > 1) out[names.length - 1].x = 60.0;
  return out;
}

export interface FormOptions {
  /** `[]` is a legitimate "no hornline" request and is honoured, not replaced. */
  instrumentation?: readonly [string, number][];
  battery?: readonly [string, number][];
  pit?: readonly [string, number][];
}

/** A rectangular block centred upfield of the 50 — the classic 'wall'. */
export function blockForm(
  o: FormOptions & {
    center?: [number, number];
    intervalSteps?: number;
    rowsSpacingSteps?: number;
    perRow?: number;
  } = {},
): Performer[] {
  const instrumentation = o.instrumentation ?? DEFAULT_INSTRUMENTATION;
  const battery = o.battery ?? DEFAULT_BATTERY;
  const pit = o.pit ?? DEFAULT_PIT;
  const center = o.center ?? [0.0, 55.0];
  const intervalSteps = o.intervalSteps ?? 2.0;
  const rowsSpacingSteps = o.rowsSpacingSteps ?? 2.0;
  const perRow = o.perRow ?? 12;
  if (perRow < 1) throw new RangeError(`per_row must be at least 1, got ${perRow}`);

  const performers: Performer[] = [];
  const dx = intervalSteps * STEP_FT;
  const dy = rowsSpacingSteps * STEP_FT;
  let row = 0;

  for (const [name, count] of instrumentation) {
    let placed = 0;
    while (placed < count) {
      const n = Math.min(perRow, count - placed);
      const y = center[1] + row * dy;
      for (let i = 0; i < n; i++) {
        const x = (i - (n - 1) / 2.0) * dx + center[0];
        performers.push({ instrument: name, x, y, fx: 0.0, fy: -1.0 });
      }
      placed += n;
      row += 1;
    }
  }

  performers.push(...batteryLine(battery, center[1] - 5 * dy, dx));
  performers.push(...pitLine(pit));
  return applyFacing(performers, 'front');
}

/** A concave arc opening toward the audience. */
export function arcForm(
  o: FormOptions & {
    center?: [number, number];
    radiusFt?: number;
    spreadDeg?: number;
    rankSpacingFt?: number;
    perRank?: number;
  } = {},
): Performer[] {
  const instrumentation = o.instrumentation ?? DEFAULT_INSTRUMENTATION;
  const battery = o.battery ?? DEFAULT_BATTERY;
  const pit = o.pit ?? DEFAULT_PIT;
  const center = o.center ?? [0.0, 118.0];
  const radiusFt = o.radiusFt ?? 88.0;
  const spreadDeg = o.spreadDeg ?? 120.0;
  const rankSpacingFt = o.rankSpacingFt ?? 6.0;
  const perRank = o.perRank ?? 18;
  if (perRank < 1) throw new RangeError(`per_rank must be at least 1, got ${perRank}`);

  const performers: Performer[] = [];
  let rank = 0;
  for (const [name, count] of instrumentation) {
    let placed = 0;
    while (placed < count) {
      const n = Math.min(perRank, count - placed);
      const r = radiusFt + rank * rankSpacingFt;
      for (let i = 0; i < n; i++) {
        // A linspace of length 1 returns the *start* of the range, which would
        // strand a leftover single performer on the end of the arc.
        let deg: number;
        if (n === 1) deg = 0.0;
        else deg = -spreadDeg / 2.0 + (spreadDeg * i) / (n - 1);
        if (n > 1 && i === n - 1) deg = spreadDeg / 2.0;
        const a = (deg * Math.PI) / 180.0;
        performers.push({
          instrument: name,
          x: center[0] + r * Math.sin(a),
          y: center[1] - r * Math.cos(a),
          fx: 0.0,
          fy: -1.0,
        });
      }
      placed += n;
      rank += 1;
    }
  }

  performers.push(...batteryLine(battery, 18.0, 2.0 * STEP_FT));
  performers.push(...pitLine(pit));
  return applyFacing(performers, 'front');
}

export const FORMS = { block: blockForm, arc: arcForm };
