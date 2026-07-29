/**
 * Atmospheric sound absorption, ISO 9613-1. Port of `dcisim/atmosphere.py`.
 *
 * Returns pure-tone attenuation coefficients in dB/m.
 */

/** Octave band centres used throughout the simulator. */
export const BANDS = Object.freeze([63.0, 125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0]);
export const N_BANDS = 8;

/** A-weighting corrections at those band centres (IEC 61672). */
export const A_WEIGHT = Object.freeze([-26.2, -16.1, -8.6, -3.2, 0.0, 1.2, 1.0, -1.1]);

/** Linear A-weighting factors, 10^(A/10). Precomputed: used per (source, receiver, band). */
export const A_WEIGHT_LIN: Float64Array = (() => {
  const out = new Float64Array(N_BANDS);
  for (let b = 0; b < N_BANDS; b++) out[b] = Math.pow(10.0, A_WEIGHT[b] / 10.0);
  return out;
})();

const T0 = 293.15; // reference air temperature, K
const T01 = 273.16; // triple-point isotherm, K
export const PR = 101.325; // reference ambient pressure, kPa

/**
 * Atmospheric attenuation in dB/m for each frequency in `freqs`.
 *
 * The range checks are load-bearing, not decoration: below absolute zero the
 * relaxation terms raise a negative base to a fractional power, which in Python
 * silently produced a complex number and in JavaScript silently produces NaN.
 * Either way the caller gets convincing garbage, so reject it here.
 */
export function absorptionCoefficients(
  freqs: ArrayLike<number> = BANDS,
  tempC = 24.0,
  humidityPct = 55.0,
  pressureKpa = PR,
): Float64Array {
  if (!(tempC >= -60.0 && tempC <= 60.0)) {
    throw new RangeError(
      `temperature ${tempC.toFixed(1)} C is outside the modelled range (-60 to 60 C)`,
    );
  }
  if (!(humidityPct >= 0.0 && humidityPct <= 100.0)) {
    throw new RangeError(`relative humidity must be 0-100%, got ${humidityPct.toFixed(1)}`);
  }
  if (!(pressureKpa > 0.0)) {
    throw new RangeError(`ambient pressure must be positive, got ${pressureKpa.toFixed(1)} kPa`);
  }

  const T = tempC + 273.15;
  const pa = pressureKpa;

  // Molar concentration of water vapour, in percent.
  const psatRatio = Math.pow(10.0, -6.8346 * Math.pow(T01 / T, 1.261) + 4.6151);
  const h = (humidityPct * psatRatio) / (pa / PR);

  // Relaxation frequencies of oxygen and nitrogen.
  const frO = (pa / PR) * (24.0 + (4.04e4 * h * (0.02 + h)) / (0.391 + h));
  const frN =
    (pa / PR) *
    Math.pow(T / T0, -0.5) *
    (9.0 + 280.0 * h * Math.exp(-4.17 * (Math.pow(T / T0, -1.0 / 3.0) - 1.0)));

  const classical = 1.84e-11 * Math.pow(pa / PR, -1.0) * Math.pow(T / T0, 0.5);
  const relaxScale = Math.pow(T / T0, -2.5);
  const oTerm = 0.01275 * Math.exp(-2239.1 / T);
  const nTerm = 0.1068 * Math.exp(-3352.0 / T);

  const out = new Float64Array(freqs.length);
  for (let i = 0; i < freqs.length; i++) {
    const f = freqs[i];
    const f2 = f * f;
    const relaxation = relaxScale * (oTerm / (frO + f2 / frO) + nTerm / (frN + f2 / frN));
    out[i] = 8.686 * f2 * (classical + relaxation);
  }
  return out;
}

/** Speed of sound in m/s for dry air at the given temperature. */
export function speedOfSound(tempC = 24.0): number {
  if (tempC <= -273.15) {
    throw new RangeError(`temperature ${tempC.toFixed(1)} C is below absolute zero`);
  }
  return 331.3 * Math.sqrt(1.0 + tempC / 273.15);
}
