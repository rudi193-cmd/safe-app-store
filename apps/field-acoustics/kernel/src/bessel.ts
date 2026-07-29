/**
 * `J1`, the Bessel function of the first kind, order 1.
 *
 * The Python model gets this from `scipy.special.j1`. It is needed once per
 * (instrument, band, sub-frequency, theta) at table-build time and never on the
 * hot path, so this is written for accuracy and auditability rather than speed.
 *
 * Two regimes:
 *   |x| <= 15   ascending power series. The largest intermediate term at x = 15
 *               is ~9e3 against a result of ~0.2, so about five digits are lost
 *               to cancellation, leaving ~1e-11 relative. The model never asks
 *               for |x| beyond ~12.1 (see `directivity.ts`).
 *   |x| >  15   Hankel asymptotic expansion, four terms in each of P and Q.
 *
 * Checked against `scipy.special.j1` by `test/differential.mjs`.
 */

const SQRT_2_OVER_PI = 0.7978845608028654; // sqrt(2/pi)
const THREE_PI_OVER_4 = 2.356194490192345;

export function besselJ1(x: number): number {
  if (x < 0) return -besselJ1(-x);
  if (x === 0) return 0;

  if (x <= 15.0) {
    // j1(x) = (x/2) * sum_k (-1)^k (x^2/4)^k / (k! (k+1)!)
    const z = 0.25 * x * x;
    let term = 1.0;
    let sum = 1.0;
    for (let k = 1; k < 200; k++) {
      term *= -z / (k * (k + 1));
      sum += term;
      if (Math.abs(term) < 1e-19 * Math.abs(sum)) break;
    }
    return 0.5 * x * sum;
  }

  // Hankel asymptotic with mu = 4*nu^2 = 4, summed by recurrence:
  //
  //     c_0 = 1,  c_m = c_{m-1} * (mu - (2m-1)^2) / (m * 8x)
  //     P = c_0 - c_2 + c_4 - ...,   Q = c_1 - c_3 + c_5 - ...
  //
  // Truncated optimally — an asymptotic series eventually diverges, so the loop
  // stops as soon as a term stops shrinking. A fixed four-term truncation left
  // 5e-10 of absolute error at x = 15, which showed up in the differential test
  // against scipy; optimal truncation takes it to ~1e-13.
  const y = 8.0 * x;
  let c = 1.0;
  let p = 1.0;
  let q = 0.0;
  for (let m = 1; m <= 60; m++) {
    const prev = Math.abs(c);
    const t = 2 * m - 1;
    c *= (4.0 - t * t) / (m * y);
    const mag = Math.abs(c);
    if (mag > prev) break;
    if (m & 1) q += ((m - 1) / 2) % 2 === 0 ? c : -c;
    else p += (m / 2) % 2 === 0 ? c : -c;
    if (mag < 1e-18) break;
  }

  const xn = x - THREE_PI_OVER_4;
  return (SQRT_2_OVER_PI * (p * Math.cos(xn) - q * Math.sin(xn))) / Math.sqrt(x);
}

/**
 * `2*J1(u)/u`, the on-axis-normalised circular-piston directivity, with the
 * removable singularity at u = 0 filled in (numpy does the same thing via
 * `np.where(u == 0, 1.0, ...)` under `errstate`).
 */
export function pistonFactor(u: number): number {
  if (u === 0.0) return 1.0;
  return (2.0 * besselJ1(u)) / u;
}
