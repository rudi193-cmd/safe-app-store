/**
 * Frequency-dependent directivity for bell-radiating instruments.
 * Port of `dcisim/directivity.py`.
 *
 * Two pieces combined:
 *   1. a circular-piston term `2*J1(u)/u`, `u = k*a*sin(theta)`, power-averaged
 *      across each octave band;
 *   2. a sidelobe floor and a rear taper carrying the response from its
 *      90-degree value down to a published front-to-back ratio at 180.
 *
 * The rear hemisphere is *not* built from the piston term — that would mirror
 * the front lobe back in, which has no physical content. See the Python module
 * docstring for why this matters to the experiment the model exists to run.
 */

import { BANDS, N_BANDS, speedOfSound } from './atmosphere.js';
import { pistonFactor } from './bessel.js';
import { geomspace, interp, linspace, trapezoid } from './numeric.js';

/** Front-to-back ratio (dB at 180 deg re. on-axis) by octave band. */
export const DEFAULT_FRONT_TO_BACK = Object.freeze([2.0, 3.0, 5.0, 9.0, 14.0, 18.0, 22.0, 25.0]);

/** Off-axis floor (dB below on-axis) the piston term may not fall below. */
export const DEFAULT_SIDELOBE_FLOOR = Object.freeze(Array.from(linspace(4.0, 14.0, 8)));

export const A_REF = 0.13;
export const APERTURE_COMPRESSION = 0.45;
export const FLARE_EXPONENT = 0.5;
export const MAX_EFFECTIVE_RADIUS = 0.6;

const N_THETA = 721;

/** `np.radians(np.linspace(0, 180, 721))`. */
export const THETA_GRID: Float64Array = (() => {
  const deg = linspace(0.0, 180.0, N_THETA);
  const out = new Float64Array(N_THETA);
  const k = Math.PI / 180.0;
  for (let i = 0; i < N_THETA; i++) out[i] = deg[i] * k;
  return out;
})();

/** Frequency-dependent radiating aperture (empirical flare correction). */
export function effectiveRadius(radiusM: number, freqHz: number): number {
  const a = A_REF * Math.pow(radiusM / A_REF, APERTURE_COMPRESSION);
  return Math.min(a * Math.pow(1000.0 / freqHz, FLARE_EXPONENT), MAX_EFFECTIVE_RADIUS);
}

/** Power-averaged piston directivity across one octave band, on a theta grid. */
function bandAveragedPiston(
  radiusM: number,
  bandHz: number,
  theta: ArrayLike<number>,
  c: number,
  nSub = 9,
): Float64Array {
  const sub = geomspace(bandHz / Math.SQRT2, bandHz * Math.SQRT2, nSub);
  const ka = new Float64Array(nSub);
  for (let j = 0; j < nSub; j++) ka[j] = ((2.0 * Math.PI * sub[j]) / c) * radiusM;

  const out = new Float64Array(theta.length);
  for (let i = 0; i < theta.length; i++) {
    const st = Math.sin(theta[i]);
    let acc = 0.0;
    for (let j = 0; j < nSub; j++) {
      const d = pistonFactor(st * ka[j]);
      acc += d * d;
    }
    out[i] = Math.sqrt(acc / nSub);
  }
  return out;
}

/**
 * Linear directivity *amplitude* on a (band, theta) grid, 1.0 on axis.
 * Returned flat, row-major: `table[b * theta.length + i]`.
 */
export function buildDirectivityTable(
  radiusM: number,
  frontToBack: ArrayLike<number> = DEFAULT_FRONT_TO_BACK,
  sidelobeFloor: ArrayLike<number> = DEFAULT_SIDELOBE_FLOOR,
  tempC = 24.0,
  theta: ArrayLike<number> = THETA_GRID,
): Float64Array {
  const c = speedOfSound(tempC);
  const nT = theta.length;
  const table = new Float64Array(N_BANDS * nT);

  // Index of theta = pi/2 on the grid, found the same way numpy does it
  // (interpolate the index axis, then round).
  const idxAxis = new Float64Array(nT);
  for (let i = 0; i < nT; i++) idxAxis[i] = i;
  const at90 = Math.round(interp(Math.PI / 2.0, theta, idxAxis));

  for (let b = 0; b < N_BANDS; b++) {
    const off = b * nT;

    // 1. piston (or a flat 1.0 for the explicit omnidirectional escape hatch).
    if (radiusM <= 0.0) {
      table.fill(1.0, off, off + nT);
    } else {
      const p = bandAveragedPiston(effectiveRadius(radiusM, BANDS[b]), BANDS[b], theta, c);
      table.set(p, off);
    }

    // 2. sidelobe floor. A floor deeper than the front-to-back ratio would
    //    contradict it, so it is capped by the ratio (percussion hits this).
    const floor = Math.pow(10.0, -Math.min(sidelobeFloor[b], frontToBack[b]) / 20.0);
    for (let i = 0; i < nT; i++) if (table[off + i] < floor) table[off + i] = floor;

    // 3. rear taper: carry the 90-degree value down to the published ratio at
    //    180, interpolated smoothly in dB via a smoothstep in theta.
    const d90 = table[off + at90];
    const rearTarget = Math.pow(10.0, -frontToBack[b] / 20.0);
    const ratio = rearTarget / d90;
    const halfPi = Math.PI / 2.0;
    for (let i = 0; i < nT; i++) {
      if (theta[i] <= halfPi) continue;
      let s = (theta[i] - halfPi) / halfPi;
      s = s < 0 ? 0 : s > 1 ? 1 : s;
      s = s * s * (3.0 - 2.0 * s);
      table[off + i] = d90 * Math.pow(ratio, s);
    }
  }
  return table;
}

/** Callable directivity lookup, interpolated over off-axis angle. */
export class Directivity {
  readonly radiusM: number;
  readonly theta: Float64Array;
  /** Linear amplitude, flat (N_BANDS * nTheta). */
  readonly table: Float64Array;
  private _di: Float64Array | null = null;

  constructor(
    radiusM: number,
    frontToBack: ArrayLike<number> = DEFAULT_FRONT_TO_BACK,
    sidelobeFloor: ArrayLike<number> = DEFAULT_SIDELOBE_FLOOR,
    tempC = 24.0,
    measured?: { table: ArrayLike<number>; theta?: ArrayLike<number> },
  ) {
    this.radiusM = radiusM;
    if (measured) {
      const t = Float64Array.from(measured.table);
      const nT = measured.theta ? measured.theta.length : t.length / N_BANDS;
      if (t.length !== N_BANDS * nT) {
        throw new RangeError(
          `measured table must be (${N_BANDS} bands, n_theta), got ${t.length} values`,
        );
      }
      this.theta = measured.theta ? Float64Array.from(measured.theta) : linspace(0, Math.PI, nT);
      this.table = t;
    } else {
      this.theta = THETA_GRID;
      this.table = buildDirectivityTable(radiusM, frontToBack, sidelobeFloor, tempC, THETA_GRID);
    }
  }

  static fromMeasured(table: ArrayLike<number>, theta?: ArrayLike<number>): Directivity {
    return new Directivity(0.0, DEFAULT_FRONT_TO_BACK, DEFAULT_SIDELOBE_FLOOR, 24.0, {
      table,
      theta,
    });
  }

  get nTheta(): number {
    return this.theta.length;
  }

  /** Radiation pattern in dB, normalised to 0 dB on axis. Not what the engine wants. */
  patternDb(thetaRad: number): Float64Array {
    const nT = this.nTheta;
    const t = thetaRad < 0 ? 0 : thetaRad > Math.PI ? Math.PI : thetaRad;
    const out = new Float64Array(N_BANDS);
    for (let b = 0; b < N_BANDS; b++) {
      const v = interp(t, this.theta, this.table.subarray(b * nT, (b + 1) * nT));
      out[b] = 20.0 * Math.log10(Math.max(v, 1e-6));
    }
    return out;
  }

  /**
   * Directivity index in a given direction, dB re. the sphere average — the
   * `DI(theta)` term in `Lp = Lw - 20*log10(r) - 11 + DI(theta)`.
   *
   * Normalising the pattern to 0 dB on axis instead would quietly redefine `Lw`
   * as "on-axis level" rather than sound power, throwing the radiated power off
   * by the directivity index: under a dB at 63 Hz, around 13 dB at 8 kHz.
   */
  gainDb(thetaRad: number): Float64Array {
    const di = this.directivityIndexDb();
    const out = this.patternDb(thetaRad);
    for (let b = 0; b < N_BANDS; b++) out[b] += di[b];
    return out;
  }

  /** DI per band: on-axis gain over the sphere-averaged power. */
  directivityIndexDb(): Float64Array {
    if (this._di) return this._di;
    const nT = this.nTheta;
    const w = new Float64Array(nT);
    for (let i = 0; i < nT; i++) w[i] = Math.sin(this.theta[i]);
    const denom = trapezoid(w, this.theta);
    const num = new Float64Array(nT);
    const di = new Float64Array(N_BANDS);
    for (let b = 0; b < N_BANDS; b++) {
      const off = b * nT;
      for (let i = 0; i < nT; i++) {
        const v = this.table[off + i];
        num[i] = v * v * w[i];
      }
      di[b] = -10.0 * Math.log10(trapezoid(num, this.theta) / denom);
    }
    this._di = di;
    return di;
  }
}

/**
 * The engine-facing form of a directivity: the *linear energy* pattern
 * resampled onto a grid uniform in `cos(theta)` rather than `theta`.
 *
 * This is the second half of the restructuring the browser spike measured. The
 * propagation equation needs `10^(pattern_db/10) == max(amp, 1e-6)^2`, so the
 * `20*log10` and the `10^(x/10)` cancel outright; and indexing by `cos(theta)`
 * deletes the `acos` that would otherwise be evaluated once per
 * (source, receiver) pair. Between them these two changes account for most of
 * the ~3.1x the spike measured for restructured TypeScript.
 *
 * Uniform-in-cos is a *better*-conditioned grid than uniform-in-theta near the
 * poles, not a worse one: the main lobe goes as `1 - (ka)^2*theta^2/8`, which is
 * exactly linear in `cos(theta)` to leading order, and the rear taper is C1-flat
 * at 180 degrees. The resampling error concentrates around 90 degrees, where the
 * cos grid spacing equals the theta grid spacing, so `nCos` is chosen well above
 * the source grid's 721 points.
 */
export interface CosDirectivityTable {
  /**
   * Linear energy (amplitude squared), flat and **band-interleaved**:
   * `data[j * N_BANDS + b]`.
   *
   * Interleaved, not band-major. The inner loop reads all eight bands at one
   * cos index and the next, so this layout touches two cache lines per lookup
   * instead of sixteen. That is worth about 30% of the kernel's runtime on the
   * 77x1640x8 set, and it is what makes a 16384-point table (which is accurate
   * enough to sit at the reference implementation's own noise floor) cost the
   * same as a 4096-point one.
   */
  data: Float64Array | Float32Array;
  nCos: number;
  /** `(nCos - 1) / 2`; index = `(cosTheta + 1) * scale`. */
  scale: number;
  /** Directivity index per band, dB. Folded into the per-source constant, not here. */
  di: Float64Array;
}

/**
 * Cache keyed on the `Directivity` instance. Instruments memoise their
 * `Directivity` per (temperature, radius, front-to-back), so this makes the cos
 * table a once-per-process cost rather than a once-per-`simulate()` cost — which
 * matters: at the default 4096 points it is 32 768 `acos` calls per instrument,
 * comfortably more than a whole set's worth of work.
 */
const cosTableCache = new WeakMap<Directivity, Map<string, CosDirectivityTable>>();

export function buildCosTable(
  d: Directivity,
  nCos = 4096,
  precision: 'f64' | 'f32' = 'f64',
): CosDirectivityTable {
  let perDir = cosTableCache.get(d);
  if (!perDir) {
    perDir = new Map();
    cosTableCache.set(d, perDir);
  }
  const key = `${nCos}|${precision}`;
  const hit = perDir.get(key);
  if (hit) return hit;
  const built = computeCosTable(d, nCos, precision);
  perDir.set(key, built);
  return built;
}

function computeCosTable(
  d: Directivity,
  nCos: number,
  precision: 'f64' | 'f32',
): CosDirectivityTable {
  const nT = d.nTheta;
  const data =
    precision === 'f32' ? new Float32Array(N_BANDS * nCos) : new Float64Array(N_BANDS * nCos);
  const step = 2.0 / (nCos - 1);
  const theta = new Float64Array(nCos);
  for (let j = 0; j < nCos; j++) {
    let u = -1.0 + j * step;
    if (u > 1.0 || j === nCos - 1) u = 1.0;
    theta[j] = Math.acos(u);
  }

  // `theta` decreases monotonically in j, so the source grid can be walked once
  // per band instead of binary-searched per sample. Same arithmetic as
  // `interp`, ~4x less work: this runs 8 * nCos times per instrument at startup.
  const src0 = d.theta;
  for (let b = 0; b < N_BANDS; b++) {
    const src = d.table.subarray(b * nT, (b + 1) * nT);
    let k = 0;
    for (let j = nCos - 1; j >= 0; j--) {
      const t = theta[j];
      while (k + 2 < nT && src0[k + 1] <= t) k++;
      let amp: number;
      if (t <= src0[0]) amp = src[0];
      else if (t >= src0[nT - 1]) amp = src[nT - 1];
      else {
        const slope = (src[k + 1] - src[k]) / (src0[k + 1] - src0[k]);
        amp = slope * (t - src0[k]) + src[k];
      }
      const clamped = amp > 1e-6 ? amp : 1e-6;
      data[j * N_BANDS + b] = clamped * clamped;
    }
  }
  return { data, nCos, scale: (nCos - 1) / 2.0, di: d.directivityIndexDb() };
}

/** Published directivity indices for brass, used as the calibration target. */
export const REFERENCE_DI: Readonly<Record<string, readonly [number, readonly number[]]>> =
  Object.freeze({
    trumpet: [0.062, [0.3, 0.6, 1.2, 2.5, 4.5, 7.0, 10.0, 12.5]],
    mellophone: [0.13, [0.5, 1.2, 2.5, 4.5, 7.0, 9.5, 11.5, 13.0]],
    contra: [0.24, [1.0, 2.2, 4.2, 6.5, 9.0, 11.0, 12.5, 13.5]],
  });
