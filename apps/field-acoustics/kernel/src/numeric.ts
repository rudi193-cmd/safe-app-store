/**
 * Small numeric helpers that reproduce the specific numpy routines the Python
 * model depends on. They exist so the port can be checked term-by-term against
 * `dcisim/`, not because a general array library was wanted.
 *
 * Every function here runs at table-build time only. None of it is on the
 * per-(source, receiver, band) path.
 */

/** `np.linspace(start, stop, num)`, including numpy's exact endpoint pinning. */
export function linspace(start: number, stop: number, num: number): Float64Array {
  const out = new Float64Array(num);
  if (num === 0) return out;
  if (num === 1) {
    out[0] = start;
    return out;
  }
  const step = (stop - start) / (num - 1);
  for (let i = 0; i < num; i++) out[i] = start + i * step;
  // numpy overwrites the last element with `stop` rather than trusting the
  // accumulated arithmetic. Matching that keeps band edges bit-identical.
  out[num - 1] = stop;
  return out;
}

/**
 * `np.geomspace(start, stop, num)`. numpy routes this through `logspace` with
 * base 10 and then pins both endpoints, so a naive `exp(linspace(log ...))`
 * differs in the last bits. Reproduced exactly.
 */
export function geomspace(start: number, stop: number, num: number): Float64Array {
  const t = linspace(Math.log10(start), Math.log10(stop), num);
  const out = new Float64Array(num);
  for (let i = 0; i < num; i++) out[i] = Math.pow(10, t[i]);
  if (num > 0) out[0] = start;
  if (num > 1) out[num - 1] = stop;
  return out;
}

/** `np.trapezoid(y, x)` — composite trapezoidal rule over a non-uniform grid. */
export function trapezoid(y: ArrayLike<number>, x: ArrayLike<number>): number {
  let acc = 0.0;
  for (let i = 0; i + 1 < y.length; i++) {
    acc += (x[i + 1] - x[i]) * (y[i + 1] + y[i]) * 0.5;
  }
  return acc;
}

/**
 * `np.interp(v, xp, fp)` for a single point, with numpy's clamp-at-the-ends
 * behaviour and its slope form (`slope * (v - xp[i]) + fp[i]`).
 * `xp` must be increasing.
 */
export function interp(v: number, xp: ArrayLike<number>, fp: ArrayLike<number>): number {
  const n = xp.length;
  if (n === 0) return NaN;
  if (n === 1 || v <= xp[0]) return fp[0];
  if (v >= xp[n - 1]) return fp[n - 1];

  let lo = 0;
  let hi = n - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (xp[mid] <= v) lo = mid;
    else hi = mid;
  }
  const slope = (fp[lo + 1] - fp[lo]) / (xp[lo + 1] - xp[lo]);
  return slope * (v - xp[lo]) + fp[lo];
}

export function clamp(v: number, lo: number, hi: number): number {
  return v < lo ? lo : v > hi ? hi : v;
}
