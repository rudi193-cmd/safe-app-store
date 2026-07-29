/**
 * The "before" picture, for measuring what the restructuring is actually worth.
 *
 * Structurally identical to `src/engine.ts` — same flat typed arrays, same
 * de-interleaved source and receiver coordinates, same band-interleaved table,
 * same loop nest, same outputs — and different in exactly one respect: it
 * evaluates the propagation equation as written.
 *
 *     theta = acos(cos_t)                       (an acos per source-receiver)
 *     Lp    = Lw + 20*log10(amp) + DI - 20*log10(r) - 11 - alpha*r
 *     e     = 10^(Lp/10)                        (a log10 and a 10^x per band)
 *
 * `test/reference_kernel.mjs` is the *correctness* reference and is written for
 * legibility, so it allocates per evaluation and is far slower than any honest
 * baseline. This file is the *performance* baseline. Quoting a speedup against
 * the other one would be flattering nonsense.
 */

import {
  A_WEIGHT,
  BANDS,
  CATALOG,
  FT_PER_M,
  MIN_RANGE_M,
  absorptionCoefficients,
  farSidePlaneYFt,
  speedOfSound,
} from '../dist/index.js';

const N_BANDS = 8;
const AW = A_WEIGHT.map((v) => Math.pow(10, v / 10));
/**
 * `10^(x/10)` written as `exp(x * ln10/10)`. V8's `Math.pow(10, x)` is 4.7x
 * slower than `Math.exp` (measured: 79 ns vs 17 ns), and a naive port that used
 * `pow` would inflate the restructuring's apparent speedup by ~2.5x. This
 * baseline gets the benefit of the doubt.
 */
const LN10_OVER_10 = Math.LN10 / 10;

const thetaTables = new Map();
function thetaTable(name, tempC) {
  const key = `${name}@${tempC}`;
  let t = thetaTables.get(key);
  if (t) return t;
  const d = CATALOG.get(name).directivity(tempC);
  const nT = d.nTheta;
  const data = new Float64Array(nT * N_BANDS);
  for (let b = 0; b < N_BANDS; b++) {
    for (let i = 0; i < nT; i++) data[i * N_BANDS + b] = d.table[b * nT + i];
  }
  t = { data, nT, scale: (nT - 1) / Math.PI, di: d.directivityIndexDb() };
  thetaTables.set(key, t);
  return t;
}

export function naiveSimulate(performers, receiversFt, stadium, conditions) {
  const nR = receiversFt.length / 3;
  const c = speedOfSound(conditions.tempC);
  const alpha = absorptionCoefficients(
    BANDS,
    conditions.tempC,
    conditions.humidityPct,
    conditions.pressureKpa,
  );

  const rcvX = new Float64Array(nR);
  const rcvY = new Float64Array(nR);
  const rcvZ = new Float64Array(nR);
  for (let r = 0; r < nR; r++) {
    rcvX[r] = receiversFt[r * 3] / FT_PER_M;
    rcvY[r] = receiversFt[r * 3 + 1] / FT_PER_M;
    rcvZ[r] = receiversFt[r * 3 + 2] / FT_PER_M;
  }

  const axX = [];
  const axY = [];
  const axZ = [];
  const wLobe = [];
  const owner = [];
  for (let i = 0; i < performers.length; i++) {
    const p = performers[i];
    const inst = CATALOG.get(p.instrument);
    let offs = [inst.bellAzimuthOffsetDeg];
    let ws = [1.0];
    if (Math.abs(inst.bellAzimuthOffsetDeg) > 1e-6) {
      offs = [inst.bellAzimuthOffsetDeg, -inst.bellAzimuthOffsetDeg];
      ws = [0.5, 0.5];
    }
    const el = (inst.bellElevationDeg * Math.PI) / 180;
    for (let j = 0; j < offs.length; j++) {
      const phi = (offs[j] * Math.PI) / 180;
      const ax = p.fx * Math.cos(phi) - p.fy * Math.sin(phi);
      const ay = p.fx * Math.sin(phi) + p.fy * Math.cos(phi);
      const n = Math.hypot(ax, ay) || 1.0;
      axX.push((ax / n) * Math.cos(el));
      axY.push((ay / n) * Math.cos(el));
      axZ.push(Math.sin(el));
      wLobe.push(ws[j]);
      owner.push(i);
    }
  }
  const nL = owner.length;

  const srcX = new Float64Array(nL);
  const srcY = new Float64Array(nL);
  const srcZ = new Float64Array(nL);
  const srcYFt = new Float64Array(nL);
  const tabs = [];
  const powers = [];
  for (let l = 0; l < nL; l++) {
    const p = performers[owner[l]];
    const inst = CATALOG.get(p.instrument);
    srcX[l] = p.x / FT_PER_M;
    srcYFt[l] = p.y;
    srcY[l] = p.y / FT_PER_M;
    srcZ[l] = (inst.bellHeightM * FT_PER_M) / FT_PER_M;
    tabs.push(thetaTable(p.instrument, conditions.tempC));
    powers.push(inst.powerDb);
  }

  const energyDirect = new Float64Array(nR * N_BANDS);
  const energyRefl = new Float64Array(nR * N_BANDS);
  const wsum = new Float64Array(nR);
  const wt = new Float64Array(nR);
  const wtt = new Float64Array(nR);
  const msPerM = 1000.0 / c;

  function pass(sy, ayArr, energy, extraDb, gate) {
    for (let l = 0; l < nL; l++) {
      const sx = srcX[l];
      const syl = sy[l];
      const sz = srcZ[l];
      const ax = axX[l];
      const ay = ayArr[l];
      const az = axZ[l];
      const tab = tabs[l];
      const di = tab.di;
      const pw = powers[l];
      const lw = 10.0 * Math.log10(wLobe[l]);
      for (let r = 0; r < nR; r++) {
        const dx = rcvX[r] - sx;
        const dy = rcvY[r] - syl;
        const dz = rcvZ[r] - sz;
        const trueR = Math.sqrt(dx * dx + dy * dy + dz * dz);
        let gateDb = 0;
        if (gate) {
          const den = syl - rcvY[r];
          let ok = false;
          if (Math.abs(den) >= 1e-9) {
            const t = (syl - gate.planeY) / den;
            const px = sx + t * (rcvX[r] - sx);
            const pz = sz + t * (rcvZ[r] - sz);
            ok = t > 0 && t < 1 && Math.abs(px) <= gate.halfW && pz >= 0 && pz <= gate.maxH;
          }
          gateDb = ok ? 0 : -300;
        }
        const inv = 1.0 / (trueR > 1e-12 ? trueR : 1e-12);
        let ct = (ax * dx + ay * dy + az * dz) * inv;
        if (ct > 1) ct = 1;
        else if (ct < -1) ct = -1;
        const rr = trueR > MIN_RANGE_M ? trueR : MIN_RANGE_M;

        const theta = Math.acos(ct);
        const spread = -20.0 * Math.log10(rr) - 11.0;

        const fp = theta * tab.scale;
        let ti = fp | 0;
        if (ti > tab.nT - 2) ti = tab.nT - 2;
        const tf = fp - ti;
        const o = ti * N_BANDS;
        const o2 = o + N_BANDS;

        const eo = r * N_BANDS;
        let wacc = 0;
        for (let b = 0; b < N_BANDS; b++) {
          const a0 = tab.data[o + b];
          const amp = a0 + (tab.data[o2 + b] - a0) * tf;
          const lp =
            pw[b] +
            20.0 * Math.log10(amp > 1e-6 ? amp : 1e-6) +
            di[b] +
            spread -
            alpha[b] * rr +
            lw +
            (extraDb ? extraDb[b] : 0) +
            gateDb;
          const e = Math.exp(lp * LN10_OVER_10);
          energy[eo + b] += e;
          wacc += e * AW[b];
        }
        const t = rr * msPerM;
        wsum[r] += wacc;
        wt[r] += wacc * t;
        wtt[r] += wacc * t * t;
      }
    }
  }

  pass(srcY, axY, energyDirect, null, null);

  if (conditions.farSideReflection && stadium.farSide) {
    const planeYFt = farSidePlaneYFt(stadium);
    const imgY = new Float64Array(nL);
    for (let l = 0; l < nL; l++) imgY[l] = (2 * planeYFt - srcYFt[l]) / FT_PER_M;
    const imgAxY = axY.map((v) => -v);
    const reflDb = new Float64Array(N_BANDS);
    for (let b = 0; b < N_BANDS; b++) {
      reflDb[b] = 10 * Math.log10(Math.max(1 - stadium.farSideAbsorption[b], 1e-4));
    }
    pass(imgY, imgAxY, energyRefl, reflDb, {
      planeY: planeYFt / FT_PER_M,
      halfW: stadium.halfWidthFt / FT_PER_M,
      maxH: stadium.farSideHeightFt / FT_PER_M,
    });
  }

  const bandSpl = new Float64Array(nR * N_BANDS);
  for (let i = 0; i < nR * N_BANDS; i++) {
    bandSpl[i] = 10 * Math.log10(Math.max(energyDirect[i] + energyRefl[i], 1e-30));
  }
  const arrivalMeanMs = new Float64Array(nR);
  const arrivalSpreadMs = new Float64Array(nR);
  for (let r = 0; r < nR; r++) {
    const w = Math.max(wsum[r], 1e-30);
    const m = wt[r] / w;
    arrivalMeanMs[r] = m;
    arrivalSpreadMs[r] = Math.sqrt(Math.max(wtt[r] / w - m * m, 0));
  }
  return { nReceivers: nR, nBands: N_BANDS, bandSpl, arrivalMeanMs, arrivalSpreadMs };
}
