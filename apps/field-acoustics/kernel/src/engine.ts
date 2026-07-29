/**
 * The propagation engine. Port of `dcisim/engine.py`, algebraically restructured.
 *
 * For every (performer, receiver) pair, per octave band, the Python model
 * evaluates
 *
 *     Lp = Lw + D(theta, f) - 20*log10(r) - 11 - alpha(f)*r
 *     e  = 10^(Lp/10)
 *
 * summed on an energy basis across the ensemble, because independent players
 * are mutually incoherent. Optionally a specular image source across the
 * far-side grandstand is added.
 *
 * ---------------------------------------------------------------------------
 * The restructuring
 * ---------------------------------------------------------------------------
 * The browser spike measured that ~75% of that loop's runtime is transcendental
 * evaluation — `log10`, `10^x` and the `acos` behind `theta` — not arithmetic.
 * Replacing them with deliberately-wrong stand-ins gave a 4.07x ceiling, and the
 * following algebra reaches most of it *without changing the physics*:
 *
 *     10^((Lw + D - 20*log10(r) - 11 - alpha*r)/10)
 *       == P_lin * G_lin * 10^-1.1 * r^-2 * exp(-alpha*r*ln10/10)
 *
 * so:
 *   - `log10` cancels against `10^x` outright, leaving `r^-2`;
 *   - `D(theta)` is `20*log10(amp) + DI`, and `10^(D/10)` is therefore
 *     `amp^2 * 10^(DI/10)` — the directivity table is stored pre-squared and DI
 *     is folded into a per-source constant, so no logs survive;
 *   - the directivity table is indexed by `cos(theta)` rather than `theta`,
 *     which deletes the `acos` per (source, receiver);
 *   - `exp(-alpha*r*ln10/10)` becomes a per-band lookup table in `r`.
 *
 * Measured cost of the approximation (both tables, f64): max relative error
 * ~5.5e-5 in the spike's own probe, i.e. ~2.4e-4 dB. `test/differential.mjs`
 * re-measures it against the Python implementation directly.
 *
 * Everything the engine touches is metres and radians. Feet stay at the edges.
 */

import {
  A_WEIGHT,
  A_WEIGHT_LIN,
  BANDS,
  N_BANDS,
  absorptionCoefficients,
  speedOfSound,
} from './atmosphere.js';
import { CosDirectivityTable, buildCosTable } from './directivity.js';
import { DEFAULT_STADIUM, FT_PER_M, Stadium, farSidePlaneYFt } from './field.js';
import { CATALOG, Instrument } from './instruments.js';
import { linspace } from './numeric.js';

export const LF_BANDS: readonly number[] = [1, 2, 3]; // 125 / 250 / 500
export const HF_BANDS: readonly number[] = [5, 6, 7]; // 2k / 4k / 8k

/**
 * Sources are point radiators, so the spreading term diverges as r -> 0. Clamp
 * well inside any real listening position; a receiver closer than this to a bell
 * is not a seat, it is the inside of the instrument.
 */
export const MIN_RANGE_M = 0.5;
export const SILENT_DB = -300.0;

/** `10^(-11/10)`, the constant in the spherical spreading term. */
const SPREAD_LIN = Math.pow(10.0, -1.1);
const LN10_OVER_10 = Math.LN10 / 10.0;
/** `10^(-300/10)` — the reflection gate's "off" state, kept exact. */
const GATE_OFF = 1e-30;

export interface Conditions {
  tempC: number;
  humidityPct: number;
  pressureKpa: number;
  /** See the README; near common-mode here, and off by default. */
  groundEffect: boolean;
  farSideReflection: boolean;
}

export const DEFAULT_CONDITIONS: Readonly<Conditions> = Object.freeze({
  tempC: 24.0,
  humidityPct: 55.0,
  pressureKpa: 101.325,
  groundEffect: false,
  farSideReflection: true,
});

export function makeConditions(o: Partial<Conditions> = {}): Conditions {
  return { ...DEFAULT_CONDITIONS, ...o };
}

export interface Performer {
  instrument: string;
  /** feet, 0 at the 50 */
  x: number;
  /** feet, 0 at the front sideline */
  y: number;
  /** facing vector in the field plane; need not be normalised */
  fx: number;
  fy: number;
}

export interface KernelOptions {
  /**
   * Points in the cos(theta) directivity grid. The default of 16384 puts the
   * disagreement with the Python model (1.4e-4 dB) at the floor set by the
   * Python model's own 721-point theta grid — going finer does not improve it.
   * 4096 is ~25% faster and costs 1.3e-3 dB; see README.
   */
  cosTableSize?: number;
  /** Points in the range grid for air absorption; 0 uses `Math.exp` directly. */
  absorptionTableSize?: number;
  /**
   * Float64Array or Float32Array for the two lookup tables. Measured: f32 is
   * *not* faster in V8 (each read costs a widening conversion, which offsets the
   * halved footprint) and its extra error is invisible next to the resampling
   * error. f64 is the default; f32 exists for memory-constrained callers.
   */
  tablePrecision?: 'f64' | 'f32';
  catalog?: Map<string, Instrument>;
}

const DEFAULT_KERNEL: Required<Omit<KernelOptions, 'catalog'>> = {
  cosTableSize: 16384,
  absorptionTableSize: 8192,
  tablePrecision: 'f64',
};

export interface SimResult {
  nReceivers: number;
  nBands: number;
  /** (nReceivers * nBands), direct + reflected, dB. */
  bandSpl: Float64Array;
  directSpl: Float64Array;
  reflectedSpl: Float64Array;
  /** (nReceivers), energy-weighted and A-weighted arrival time, ms. */
  arrivalMeanMs: Float64Array;
  /** (nReceivers), energy-weighted standard deviation of arrival time, ms. */
  arrivalSpreadMs: Float64Array;
}

// ---------------------------------------------------------------------------
// Derived quantities (the Python `Result` properties)
// ---------------------------------------------------------------------------

/** A-weighted overall level per receiver, dB. */
export function dba(res: SimResult): Float64Array {
  const out = new Float64Array(res.nReceivers);
  for (let r = 0; r < res.nReceivers; r++) {
    let s = 0.0;
    for (let b = 0; b < N_BANDS; b++) {
      s += Math.pow(10.0, (res.bandSpl[r * N_BANDS + b] + A_WEIGHT[b]) / 10.0);
    }
    out[r] = 10.0 * Math.log10(s);
  }
  return out;
}

/** HF-to-LF energy ratio in dB. The timbre headline. */
export function brightness(res: SimResult): Float64Array {
  const out = new Float64Array(res.nReceivers);
  for (let r = 0; r < res.nReceivers; r++) {
    let hf = 0.0;
    let lf = 0.0;
    for (const b of HF_BANDS) hf += Math.pow(10.0, res.bandSpl[r * N_BANDS + b] / 10.0);
    for (const b of LF_BANDS) lf += Math.pow(10.0, res.bandSpl[r * N_BANDS + b] / 10.0);
    out[r] = 10.0 * Math.log10(hf / lf);
  }
  return out;
}

/** Reflected energy relative to direct, A-weighted, dB. */
export function reflectedRatioDb(res: SimResult): Float64Array {
  const out = new Float64Array(res.nReceivers);
  for (let r = 0; r < res.nReceivers; r++) {
    let rr = 0.0;
    let dd = 0.0;
    for (let b = 0; b < N_BANDS; b++) {
      rr += Math.pow(10.0, (res.reflectedSpl[r * N_BANDS + b] + A_WEIGHT[b]) / 10.0);
      dd += Math.pow(10.0, (res.directSpl[r * N_BANDS + b] + A_WEIGHT[b]) / 10.0);
    }
    out[r] = 10.0 * Math.log10(Math.max(rr, 1e-30) / Math.max(dd, 1e-30));
  }
  return out;
}

// ---------------------------------------------------------------------------

function toReceiverArray(receiversFt: Float64Array | number[][] | number[]): Float64Array {
  if (receiversFt instanceof Float64Array) {
    if (receiversFt.length % 3 !== 0) {
      throw new RangeError(
        `receivers must be an (n, 3) array of feet, got ${receiversFt.length} values`,
      );
    }
    return receiversFt;
  }
  if (Array.isArray(receiversFt) && receiversFt.length > 0 && Array.isArray(receiversFt[0])) {
    const rows = receiversFt as number[][];
    const out = new Float64Array(rows.length * 3);
    for (let i = 0; i < rows.length; i++) {
      if (rows[i].length !== 3) {
        throw new RangeError(
          `receivers must be an (n, 3) array of feet, row ${i} has ${rows[i].length}`,
        );
      }
      out[i * 3] = rows[i][0];
      out[i * 3 + 1] = rows[i][1];
      out[i * 3 + 2] = rows[i][2];
    }
    return out;
  }
  const flat = receiversFt as number[];
  if (flat.length % 3 !== 0) {
    throw new RangeError(`receivers must be an (n, 3) array of feet, got ${flat.length} values`);
  }
  return Float64Array.from(flat);
}

/** Fail loudly on inputs that would otherwise produce silent nonsense. */
function validate(
  performers: readonly Performer[],
  rcv: Float64Array,
  catalog: Map<string, Instrument>,
): void {
  for (let i = 0; i < performers.length; i++) {
    const p = performers[i];
    if (!catalog.has(p.instrument)) {
      throw new RangeError(
        `performer ${i} has unknown instrument ${JSON.stringify(p.instrument)}; known: ` +
          [...catalog.keys()].sort().join(', '),
      );
    }
    if (
      !Number.isFinite(p.x) ||
      !Number.isFinite(p.y) ||
      !Number.isFinite(p.fx) ||
      !Number.isFinite(p.fy)
    ) {
      throw new RangeError(
        `performer ${i} (${p.instrument}) has a non-finite coordinate or facing`,
      );
    }
    if (Math.sqrt(p.fx * p.fx + p.fy * p.fy) < 1e-9) {
      throw new RangeError(
        `performer ${i} (${p.instrument}) has a zero-length facing vector; a bell ` +
          'has to point somewhere',
      );
    }
  }
  for (let i = 0; i < rcv.length; i++) {
    if (!Number.isFinite(rcv[i])) {
      throw new RangeError('receiver positions contain non-finite values');
    }
  }
}

function silence(nR: number): SimResult {
  const spl = new Float64Array(nR * N_BANDS).fill(SILENT_DB);
  const nan = new Float64Array(nR).fill(NaN);
  return {
    nReceivers: nR,
    nBands: N_BANDS,
    bandSpl: spl,
    directSpl: spl.slice(),
    reflectedSpl: spl.slice(),
    arrivalMeanMs: nan,
    arrivalSpreadMs: nan.slice(),
  };
}

/**
 * 3D unit bell axes with power weights, one entry per *lobe*. Instruments with a
 * non-zero azimuth offset radiate from two opposed faces (marching bass drums),
 * so they get two half-power lobes.
 */
interface Lobes {
  n: number;
  axX: Float64Array;
  axY: Float64Array;
  axZ: Float64Array;
  weight: Float64Array;
  owner: Int32Array;
}

function bellAxes(
  performers: readonly Performer[],
  catalog: Map<string, Instrument>,
): Lobes {
  const axX: number[] = [];
  const axY: number[] = [];
  const axZ: number[] = [];
  const weight: number[] = [];
  const owner: number[] = [];

  for (let i = 0; i < performers.length; i++) {
    const p = performers[i];
    const inst = catalog.get(p.instrument)!;
    let offsets = [inst.bellAzimuthOffsetDeg];
    let w = [1.0];
    if (Math.abs(inst.bellAzimuthOffsetDeg) > 1e-6) {
      offsets = [inst.bellAzimuthOffsetDeg, -inst.bellAzimuthOffsetDeg];
      w = [0.5, 0.5];
    }
    const el = (inst.bellElevationDeg * Math.PI) / 180.0;
    const cel = Math.cos(el);
    const sel = Math.sin(el);
    for (let j = 0; j < offsets.length; j++) {
      const phi = (offsets[j] * Math.PI) / 180.0;
      const cp = Math.cos(phi);
      const sp = Math.sin(phi);
      const ax = p.fx * cp - p.fy * sp;
      const ay = p.fx * sp + p.fy * cp;
      const n = Math.sqrt(ax * ax + ay * ay) || 1.0;
      axX.push((ax / n) * cel);
      axY.push((ay / n) * cel);
      axZ.push(sel);
      weight.push(w[j]);
      owner.push(i);
    }
  }
  return {
    n: axX.length,
    axX: Float64Array.from(axX),
    axY: Float64Array.from(axY),
    axZ: Float64Array.from(axZ),
    weight: Float64Array.from(weight),
    owner: Int32Array.from(owner),
  };
}

// --- ground effect ---------------------------------------------------------

const GROUND_R_MAG = [0.9, 0.85, 0.75, 0.62, 0.48, 0.35, 0.25, 0.18];
const GROUND_N_SUB = 61;

/**
 * Two-path interference over soft ground, power-averaged within each band.
 *
 * Deliberately NOT restructured: it is off by default, it is the one term whose
 * value depends on (source, receiver, band) jointly, and the spike measured no
 * need for it. Enabling it costs ~488 `cos` evaluations per (source, receiver)
 * and dominates everything else in this file.
 */
function groundExcessLin(
  hs: number,
  hr: number,
  dHoriz: number,
  c: number,
  subFreqs: Float64Array[],
  out: Float64Array,
): void {
  const dz1 = hs - hr;
  const dz2 = hs + hr;
  const direct = Math.sqrt(dz1 * dz1 + dHoriz * dHoriz);
  const image = Math.sqrt(dz2 * dz2 + dHoriz * dHoriz);
  const delta = image - direct;
  const kd = (2.0 * Math.PI * delta) / c;

  for (let b = 0; b < N_BANDS; b++) {
    const R = GROUND_R_MAG[b];
    const sf = subFreqs[b];
    let acc = 0.0;
    for (let j = 0; j < GROUND_N_SUB; j++) {
      acc += 1.0 - 2.0 * R * Math.cos(kd * sf[j]) + R * R;
    }
    const mean = acc / GROUND_N_SUB;
    // 10^( (10*log10(max(mean, 0.1))) / 10 ) == max(mean, 0.1), exactly.
    out[b] = mean > 0.1 ? mean : 0.1;
  }
}

// --- the hot loop ----------------------------------------------------------

interface PathArgs {
  lobes: Lobes;
  srcX: Float64Array;
  srcY: Float64Array;
  srcZ: Float64Array;
  /** per-lobe index into `tables` */
  tabOf: Int32Array;
  tables: (Float64Array | Float32Array)[];
  nCos: number;
  uScale: number;
  /** per-lobe, per-band linear constant (power * DI * lobe weight * 10^-1.1 * [reflection]) */
  baseE: Float64Array;
  nR: number;
  rcvX: Float64Array;
  rcvY: Float64Array;
  rcvZ: Float64Array;
  absTab: Float64Array | Float32Array | null;
  absScale: number;
  absN: number;
  /** alpha * ln10/10 per band, used when no absorption table is built */
  kAbs: Float64Array;
  energy: Float64Array;
  t0: Float64Array;
  wsum: Float64Array;
  wt: Float64Array;
  wtt: Float64Array;
  msPerM: number;
  gate: {
    planeY: number;
    halfW: number;
    maxH: number;
  } | null;
  ground: { c: number; subFreqs: Float64Array[] } | null;
}

function accumulatePath(a: PathArgs): void {
  const {
    lobes,
    srcX,
    srcY,
    srcZ,
    tabOf,
    tables,
    nCos,
    uScale,
    baseE,
    nR,
    rcvX,
    rcvY,
    rcvZ,
    absTab,
    absScale,
    absN,
    kAbs,
    energy,
    t0,
    wsum,
    wt,
    wtt,
    msPerM,
    gate,
    ground,
  } = a;

  const nLobes = lobes.n;
  const axXs = lobes.axX;
  const axYs = lobes.axY;
  const axZs = lobes.axZ;
  const aw = A_WEIGHT_LIN;
  const nCosLast = nCos - 2;
  const absLast = absN - 2;
  const gscratch = ground ? new Float64Array(N_BANDS) : null;

  const planeY = gate ? gate.planeY : 0;
  const halfW = gate ? gate.halfW : 0;
  const maxH = gate ? gate.maxH : 0;

  for (let l = 0; l < nLobes; l++) {
    const sx = srcX[l];
    const sy = srcY[l];
    const sz = srcZ[l];
    const ax = axXs[l];
    const ay = axYs[l];
    const az = axZs[l];
    const tab = tables[tabOf[l]];
    const bo = l * N_BANDS;
    const b0 = baseE[bo];
    const b1 = baseE[bo + 1];
    const b2 = baseE[bo + 2];
    const b3 = baseE[bo + 3];
    const b4 = baseE[bo + 4];
    const b5 = baseE[bo + 5];
    const b6 = baseE[bo + 6];
    const b7 = baseE[bo + 7];

    for (let r = 0; r < nR; r++) {
      const dx = rcvX[r] - sx;
      const dy = rcvY[r] - sy;
      const dz = rcvZ[r] - sz;
      const trueR = Math.sqrt(dx * dx + dy * dy + dz * dz);

      let gateF = 1.0;
      if (gate !== null) {
        // Does the image-source ray actually strike the far grandstand face?
        const denom = sy - rcvY[r];
        if (Math.abs(denom) < 1e-9) {
          gateF = GATE_OFF;
        } else {
          const t = (sy - planeY) / denom;
          const px = sx + t * (rcvX[r] - sx);
          const pz = sz + t * (rcvZ[r] - sz);
          const ok = t > 0.0 && t < 1.0 && Math.abs(px) <= halfW && pz >= 0.0 && pz <= maxH;
          gateF = ok ? 1.0 : GATE_OFF;
        }
      }

      // Direction must be normalised by the TRUE range. Using the clamped range
      // here leaves the direction short inside MIN_RANGE_M, dragging every
      // cosine toward zero and collapsing the pattern toward 90 degrees.
      const inv = 1.0 / (trueR > 1e-12 ? trueR : 1e-12);
      let ct = (ax * dx + ay * dy + az * dz) * inv;
      if (ct > 1.0) ct = 1.0;
      else if (ct < -1.0) ct = -1.0;

      const rr = trueR > MIN_RANGE_M ? trueR : MIN_RANGE_M;
      const scale = (gateF / (rr * rr)) * SPREAD_LIN;

      // directivity: index by cos(theta), no acos, table already squared
      const fp = (ct + 1.0) * uScale;
      let di = fp | 0;
      if (di > nCosLast) di = nCosLast;
      const df = fp - di;

      const t = rr * msPerM - t0[r];
      const eo = r * N_BANDS;
      let wacc = 0.0;

      let g: number;
      let e: number;
      // Both tables are band-interleaved, so one lookup is two adjacent groups
      // of eight — two cache lines, not sixteen.
      let o = di * N_BANDS;

      if (gscratch !== null) {
        // Ground effect is the one term that depends on (source, receiver,
        // band) jointly, so it gets a general — and much slower — path.
        groundExcessLin(
          sz,
          rcvZ[r],
          Math.sqrt(dx * dx + dy * dy),
          ground!.c,
          ground!.subFreqs,
          gscratch,
        );
        for (let b = 0; b < N_BANDS; b++) {
          const g0 = tab[o + b];
          const gg = g0 + (tab[o + N_BANDS + b] - g0) * df;
          const abs =
            absTab !== null
              ? absLookup(absTab, rr * absScale, absLast, b)
              : Math.exp(-kAbs[b] * rr);
          const ee = baseE[bo + b] * gg * scale * abs * gscratch[b];
          energy[eo + b] += ee;
          wacc += ee * aw[b];
        }
      } else if (absTab !== null) {
        const ap = rr * absScale;
        let ai = ap | 0;
        if (ai > absLast) ai = absLast;
        const af = ap - ai;
        const ao = ai * N_BANDS;
        const o2 = o + N_BANDS;
        const ao2 = ao + N_BANDS;

        g = tab[o] + (tab[o2] - tab[o]) * df;
        e = b0 * g * scale * (absTab[ao] + (absTab[ao2] - absTab[ao]) * af);
        energy[eo] += e;
        wacc += e * aw[0];
        g = tab[o + 1] + (tab[o2 + 1] - tab[o + 1]) * df;
        e = b1 * g * scale * (absTab[ao + 1] + (absTab[ao2 + 1] - absTab[ao + 1]) * af);
        energy[eo + 1] += e;
        wacc += e * aw[1];
        g = tab[o + 2] + (tab[o2 + 2] - tab[o + 2]) * df;
        e = b2 * g * scale * (absTab[ao + 2] + (absTab[ao2 + 2] - absTab[ao + 2]) * af);
        energy[eo + 2] += e;
        wacc += e * aw[2];
        g = tab[o + 3] + (tab[o2 + 3] - tab[o + 3]) * df;
        e = b3 * g * scale * (absTab[ao + 3] + (absTab[ao2 + 3] - absTab[ao + 3]) * af);
        energy[eo + 3] += e;
        wacc += e * aw[3];
        g = tab[o + 4] + (tab[o2 + 4] - tab[o + 4]) * df;
        e = b4 * g * scale * (absTab[ao + 4] + (absTab[ao2 + 4] - absTab[ao + 4]) * af);
        energy[eo + 4] += e;
        wacc += e * aw[4];
        g = tab[o + 5] + (tab[o2 + 5] - tab[o + 5]) * df;
        e = b5 * g * scale * (absTab[ao + 5] + (absTab[ao2 + 5] - absTab[ao + 5]) * af);
        energy[eo + 5] += e;
        wacc += e * aw[5];
        g = tab[o + 6] + (tab[o2 + 6] - tab[o + 6]) * df;
        e = b6 * g * scale * (absTab[ao + 6] + (absTab[ao2 + 6] - absTab[ao + 6]) * af);
        energy[eo + 6] += e;
        wacc += e * aw[6];
        g = tab[o + 7] + (tab[o2 + 7] - tab[o + 7]) * df;
        e = b7 * g * scale * (absTab[ao + 7] + (absTab[ao2 + 7] - absTab[ao + 7]) * af);
        energy[eo + 7] += e;
        wacc += e * aw[7];
      } else {
        // No absorption table: eight `Math.exp` calls per pair. Kept as a
        // reference path and a way to isolate the table's error contribution.
        for (let b = 0; b < N_BANDS; b++) {
          const g0 = tab[o + b];
          const gg = g0 + (tab[o + N_BANDS + b] - g0) * df;
          const ee = baseE[bo + b] * gg * scale * Math.exp(-kAbs[b] * rr);
          energy[eo + b] += ee;
          wacc += ee * aw[b];
        }
      }

      wsum[r] += wacc;
      wt[r] += wacc * t;
      wtt[r] += wacc * t * t;
    }
  }
}

function absLookup(
  tab: Float64Array | Float32Array,
  pos: number,
  last: number,
  band: number,
): number {
  let i = pos | 0;
  if (i > last) i = last;
  const f = pos - i;
  const base = i * N_BANDS + band;
  const a = tab[base];
  return a + (tab[base + N_BANDS] - a) * f;
}

// ---------------------------------------------------------------------------

/**
 * Run the model.
 *
 * `receiversFt` is (n, 3) in feet, either a flat `Float64Array` of length 3n or
 * an array of `[x, y, z]` triples.
 */
export function simulate(
  performers: readonly Performer[],
  receiversFt: Float64Array | number[][] | number[],
  stadium: Stadium = DEFAULT_STADIUM as Stadium,
  conditions: Conditions = DEFAULT_CONDITIONS as Conditions,
  options: KernelOptions = {},
): SimResult {
  const opt = { ...DEFAULT_KERNEL, ...options };
  const catalog = options.catalog ?? CATALOG;

  const rcvFt = toReceiverArray(receiversFt);
  validate(performers, rcvFt, catalog);
  const nR = rcvFt.length / 3;
  if (performers.length === 0) return silence(nR);

  const c = speedOfSound(conditions.tempC);
  const alpha = absorptionCoefficients(
    BANDS,
    conditions.tempC,
    conditions.humidityPct,
    conditions.pressureKpa,
  );

  // Receivers, feet -> metres, de-interleaved.
  const rcvX = new Float64Array(nR);
  const rcvY = new Float64Array(nR);
  const rcvZ = new Float64Array(nR);
  for (let r = 0; r < nR; r++) {
    rcvX[r] = rcvFt[r * 3] / FT_PER_M;
    rcvY[r] = rcvFt[r * 3 + 1] / FT_PER_M;
    rcvZ[r] = rcvFt[r * 3 + 2] / FT_PER_M;
  }

  const lobes = bellAxes(performers, catalog);
  const nL = lobes.n;

  // Source points, one per lobe (a two-lobe instrument radiates both from the
  // same point). Feet first, exactly as the Python does, then metres.
  const srcX = new Float64Array(nL);
  const srcY = new Float64Array(nL);
  const srcZ = new Float64Array(nL);
  const srcYFt = new Float64Array(nL);
  for (let l = 0; l < nL; l++) {
    const p = performers[lobes.owner[l]];
    const inst = catalog.get(p.instrument)!;
    srcX[l] = p.x / FT_PER_M;
    srcYFt[l] = p.y;
    srcY[l] = p.y / FT_PER_M;
    srcZ[l] = (inst.bellHeightM * FT_PER_M) / FT_PER_M;
  }

  // One cos-indexed table per distinct instrument at this temperature.
  const tables: (Float64Array | Float32Array)[] = [];
  const tabIndexByName = new Map<string, number>();
  const cosTables: CosDirectivityTable[] = [];
  const tabOf = new Int32Array(nL);
  for (let l = 0; l < nL; l++) {
    const name = performers[lobes.owner[l]].instrument;
    let idx = tabIndexByName.get(name);
    if (idx === undefined) {
      const inst = catalog.get(name)!;
      const ct = buildCosTable(
        inst.directivity(conditions.tempC),
        opt.cosTableSize,
        opt.tablePrecision,
      );
      idx = tables.length;
      tables.push(ct.data);
      cosTables.push(ct);
      tabIndexByName.set(name, idx);
    }
    tabOf[l] = idx;
  }
  const nCos = opt.cosTableSize;
  const uScale = (nCos - 1) / 2.0;

  // Per-lobe, per-band linear constant:
  //   10^(Lw/10) * 10^(DI/10) * lobe weight     (10^-1.1 folded in at use)
  const baseDirect = new Float64Array(nL * N_BANDS);
  for (let l = 0; l < nL; l++) {
    const p = performers[lobes.owner[l]];
    const inst = catalog.get(p.instrument)!;
    const di = cosTables[tabOf[l]].di;
    for (let b = 0; b < N_BANDS; b++) {
      baseDirect[l * N_BANDS + b] =
        Math.pow(10.0, inst.powerDb[b] / 10.0) * Math.pow(10.0, di[b] / 10.0) * lobes.weight[l];
    }
  }

  // Image sources across the far-side grandstand face.
  const doReflection = conditions.farSideReflection && stadium.farSide;
  let imgY: Float64Array | null = null;
  let imgAxY: Float64Array | null = null;
  let baseRefl: Float64Array | null = null;
  if (doReflection) {
    const planeYFt = farSidePlaneYFt(stadium);
    imgY = new Float64Array(nL);
    for (let l = 0; l < nL; l++) imgY[l] = (2.0 * planeYFt - srcYFt[l]) / FT_PER_M;
    imgAxY = new Float64Array(nL);
    for (let l = 0; l < nL; l++) imgAxY[l] = -lobes.axY[l];
    baseRefl = new Float64Array(nL * N_BANDS);
    for (let b = 0; b < N_BANDS; b++) {
      const refl = Math.max(1.0 - stadium.farSideAbsorption[b], 1e-4);
      for (let l = 0; l < nL; l++) {
        baseRefl[l * N_BANDS + b] = baseDirect[l * N_BANDS + b] * refl;
      }
    }
  }

  // Air absorption lookup table, exp(-alpha*ln10/10 * r) per band.
  const kAbs = new Float64Array(N_BANDS);
  for (let b = 0; b < N_BANDS; b++) kAbs[b] = alpha[b] * LN10_OVER_10;

  let rMax = maxRange(srcX, srcY, srcZ, rcvX, rcvY, rcvZ);
  if (imgY) rMax = Math.max(rMax, maxRange(srcX, imgY, srcZ, rcvX, rcvY, rcvZ));
  rMax = Math.max(rMax, 1.0) * 1.000001;

  let absTab: Float64Array | Float32Array | null = null;
  let absScale = 0;
  const absN = opt.absorptionTableSize;
  if (absN > 1) {
    absTab =
      opt.tablePrecision === 'f32'
        ? new Float32Array(N_BANDS * absN)
        : new Float64Array(N_BANDS * absN);
    const dr = rMax / (absN - 1);
    absScale = 1.0 / dr;
    // Band-interleaved, same reason as the directivity table.
    for (let b = 0; b < N_BANDS; b++) {
      // Geometric recurrence rather than `absN` calls to `Math.exp`: the ratio
      // is constant, so one exp per band suffices. Relative drift is i*eps,
      // i.e. ~1e-12 at the far end of an 8192-point table.
      const q = Math.exp(-kAbs[b] * dr);
      let v = 1.0;
      for (let i = 0; i < absN; i++) {
        absTab[i * N_BANDS + b] = v;
        v *= q;
      }
    }
  }

  const ground = conditions.groundEffect
    ? {
        c,
        subFreqs: BANDS.map((f) => linspace(f / Math.SQRT2, f * Math.SQRT2, GROUND_N_SUB)),
      }
    : null;

  // Arrival-time origin, one per receiver: the flight time from the ensemble
  // centroid. Subtracting it before accumulating the second moment removes the
  // catastrophic cancellation that E[t^2] - E[t]^2 otherwise suffers when every
  // source is at nearly the same range (spread -> 0).
  let cx = 0;
  let cy = 0;
  let cz = 0;
  for (let l = 0; l < nL; l++) {
    cx += srcX[l];
    cy += srcY[l];
    cz += srcZ[l];
  }
  cx /= nL;
  cy /= nL;
  cz /= nL;
  const msPerM = 1000.0 / c;
  const t0 = new Float64Array(nR);
  for (let r = 0; r < nR; r++) {
    const dx = rcvX[r] - cx;
    const dy = rcvY[r] - cy;
    const dz = rcvZ[r] - cz;
    t0[r] = Math.sqrt(dx * dx + dy * dy + dz * dz) * msPerM;
  }

  const directE = new Float64Array(nR * N_BANDS);
  const reflE = new Float64Array(nR * N_BANDS);
  const wsum = new Float64Array(nR);
  const wt = new Float64Array(nR);
  const wtt = new Float64Array(nR);

  accumulatePath({
    lobes,
    srcX,
    srcY,
    srcZ,
    tabOf,
    tables,
    nCos,
    uScale,
    baseE: baseDirect,
    nR,
    rcvX,
    rcvY,
    rcvZ,
    absTab,
    absScale,
    absN,
    kAbs,
    energy: directE,
    t0,
    wsum,
    wt,
    wtt,
    msPerM,
    gate: null,
    ground,
  });

  if (doReflection) {
    accumulatePath({
      lobes: { ...lobes, axY: imgAxY! },
      srcX,
      srcY: imgY!,
      srcZ,
      tabOf,
      tables,
      nCos,
      uScale,
      baseE: baseRefl!,
      nR,
      rcvX,
      rcvY,
      rcvZ,
      absTab,
      absScale,
      absN,
      kAbs,
      energy: reflE,
      t0,
      wsum,
      wt,
      wtt,
      msPerM,
      gate: {
        planeY: farSidePlaneYFt(stadium) / FT_PER_M,
        halfW: stadium.halfWidthFt / FT_PER_M,
        maxH: stadium.farSideHeightFt / FT_PER_M,
      },
      ground,
    });
  }

  const bandSpl = new Float64Array(nR * N_BANDS);
  const directSpl = new Float64Array(nR * N_BANDS);
  const reflectedSpl = new Float64Array(nR * N_BANDS);
  for (let i = 0; i < nR * N_BANDS; i++) {
    const d = directE[i];
    const rf = reflE[i];
    bandSpl[i] = 10.0 * Math.log10(Math.max(d + rf, 1e-30));
    directSpl[i] = 10.0 * Math.log10(Math.max(d, 1e-30));
    reflectedSpl[i] = 10.0 * Math.log10(Math.max(rf, 1e-30));
  }

  const arrivalMeanMs = new Float64Array(nR);
  const arrivalSpreadMs = new Float64Array(nR);
  for (let r = 0; r < nR; r++) {
    const w = Math.max(wsum[r], 1e-30);
    const m = wt[r] / w;
    arrivalMeanMs[r] = m + t0[r];
    const v = wtt[r] / w - m * m;
    arrivalSpreadMs[r] = Math.sqrt(v > 0 ? v : 0);
  }

  return {
    nReceivers: nR,
    nBands: N_BANDS,
    bandSpl,
    directSpl,
    reflectedSpl,
    arrivalMeanMs,
    arrivalSpreadMs,
  };
}

/**
 * A bound on the largest source-receiver range, from axis-aligned bounding
 * boxes. Deliberately an over-estimate: it costs O(S + R) instead of O(S*R) and
 * is only used to size the absorption table's domain.
 */
function maxRange(
  sx: Float64Array,
  sy: Float64Array,
  sz: Float64Array,
  rx: Float64Array,
  ry: Float64Array,
  rz: Float64Array,
): number {
  const span = (a: Float64Array, b: Float64Array): number => {
    let aMin = Infinity;
    let aMax = -Infinity;
    let bMin = Infinity;
    let bMax = -Infinity;
    for (let i = 0; i < a.length; i++) {
      if (a[i] < aMin) aMin = a[i];
      if (a[i] > aMax) aMax = a[i];
    }
    for (let i = 0; i < b.length; i++) {
      if (b[i] < bMin) bMin = b[i];
      if (b[i] > bMax) bMax = b[i];
    }
    return Math.max(Math.abs(aMax - bMin), Math.abs(bMax - aMin));
  };
  const dx = span(sx, rx);
  const dy = span(sy, ry);
  const dz = span(sz, rz);
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}
