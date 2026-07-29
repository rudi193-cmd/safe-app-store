/**
 * A deliberately slow, deliberately literal transcription of
 * `dcisim/engine.py:path()` — `acos`, `log10`, `10^x` and all.
 *
 * Its only job is to answer one question the fast kernel cannot answer about
 * itself: *is the port of the physics faithful, or is the algebraic
 * restructuring covering for a transcription error?* This file shares nothing
 * with `src/engine.ts` except the directivity and atmosphere tables (whose
 * agreement with Python is checked separately, element by element).
 *
 * If this matches Python to round-off and the fast kernel matches this to the
 * table-resampling budget, then the port is correct and the restructuring cost
 * is measured rather than assumed.
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

function bellAxes(performers) {
  const axes = [];
  for (let i = 0; i < performers.length; i++) {
    const p = performers[i];
    const inst = CATALOG.get(p.instrument);
    let offsets = [inst.bellAzimuthOffsetDeg];
    let ws = [1.0];
    if (Math.abs(inst.bellAzimuthOffsetDeg) > 1e-6) {
      offsets = [inst.bellAzimuthOffsetDeg, -inst.bellAzimuthOffsetDeg];
      ws = [0.5, 0.5];
    }
    const el = (inst.bellElevationDeg * Math.PI) / 180;
    for (let j = 0; j < offsets.length; j++) {
      const phi = (offsets[j] * Math.PI) / 180;
      const ax = p.fx * Math.cos(phi) - p.fy * Math.sin(phi);
      const ay = p.fx * Math.sin(phi) + p.fy * Math.cos(phi);
      const n = Math.hypot(ax, ay) || 1.0;
      axes.push({
        a: [(ax / n) * Math.cos(el), (ay / n) * Math.cos(el), Math.sin(el)],
        w: ws[j],
        owner: i,
      });
    }
  }
  return axes;
}

function groundExcessDb(hs, hr, d, c) {
  const rMag = [0.9, 0.85, 0.75, 0.62, 0.48, 0.35, 0.25, 0.18];
  const direct = Math.sqrt((hs - hr) ** 2 + d * d);
  const image = Math.sqrt((hs + hr) ** 2 + d * d);
  const delta = image - direct;
  const out = new Float64Array(N_BANDS);
  for (let b = 0; b < N_BANDS; b++) {
    const f = BANDS[b];
    const lo = f / Math.SQRT2;
    const hi = f * Math.SQRT2;
    let acc = 0;
    for (let k = 0; k < 61; k++) {
      const fk = k === 60 ? hi : lo + ((hi - lo) / 60) * k;
      const phase = (2 * Math.PI * fk * delta) / c;
      acc += 1 - 2 * rMag[b] * Math.cos(phase) + rMag[b] * rMag[b];
    }
    out[b] = 10 * Math.log10(Math.max(acc / 61, 0.1));
  }
  return out;
}

/** Literal port of `simulate()`. Returns the same shape as `SimResult`. */
export function referenceSimulate(performers, receiversFt, stadium, conditions) {
  const nR = receiversFt.length / 3;
  const nBands = N_BANDS;
  if (performers.length === 0) {
    const spl = new Float64Array(nR * nBands).fill(-300);
    return {
      nReceivers: nR,
      nBands,
      bandSpl: spl,
      directSpl: spl.slice(),
      reflectedSpl: spl.slice(),
      arrivalMeanMs: new Float64Array(nR).fill(NaN),
      arrivalSpreadMs: new Float64Array(nR).fill(NaN),
    };
  }

  const c = speedOfSound(conditions.tempC);
  const alpha = absorptionCoefficients(
    BANDS,
    conditions.tempC,
    conditions.humidityPct,
    conditions.pressureKpa,
  );

  const rcv = [];
  for (let r = 0; r < nR; r++) {
    rcv.push([
      receiversFt[r * 3] / FT_PER_M,
      receiversFt[r * 3 + 1] / FT_PER_M,
      receiversFt[r * 3 + 2] / FT_PER_M,
    ]);
  }

  const lobes = bellAxes(performers);
  const dirs = performers.map((p) => CATALOG.get(p.instrument).directivity(conditions.tempC));
  const power = performers.map((p) => CATALOG.get(p.instrument).powerDb);

  const srcFt = lobes.map((l) => {
    const p = performers[l.owner];
    return [p.x, p.y, CATALOG.get(p.instrument).bellHeightM * FT_PER_M];
  });
  const srcM = srcFt.map((s) => [s[0] / FT_PER_M, s[1] / FT_PER_M, s[2] / FT_PER_M]);

  // A record per (lobe, receiver) so the arrival statistics can be computed the
  // same two-pass way numpy does, rather than from raw moments.
  const samples = [];

  function path(src, axes, extraDb) {
    const energy = new Float64Array(nR * nBands);
    for (let s = 0; s < src.length; s++) {
      const owner = lobes[s].owner;
      const dir = dirs[owner];
      const pw = power[owner];
      const lw = lobes[s].w;
      for (let r = 0; r < nR; r++) {
        const vec = [rcv[r][0] - src[s][0], rcv[r][1] - src[s][1], rcv[r][2] - src[s][2]];
        const trueR = Math.sqrt(vec[0] ** 2 + vec[1] ** 2 + vec[2] ** 2);
        const denom = Math.max(trueR, 1e-12);
        const unit = [vec[0] / denom, vec[1] / denom, vec[2] / denom];
        const rr = Math.max(trueR, MIN_RANGE_M);
        let cosT = axes[s][0] * unit[0] + axes[s][1] * unit[1] + axes[s][2] * unit[2];
        cosT = Math.min(1, Math.max(-1, cosT));
        const theta = Math.acos(cosT);
        const spread = -20 * Math.log10(rr) - 11;
        const g = dir.gainDb(theta);
        const ge = conditions.groundEffect
          ? groundExcessDb(src[s][2], rcv[r][2], Math.hypot(vec[0], vec[1]), c)
          : null;
        let wSample = 0;
        for (let b = 0; b < nBands; b++) {
          let lp = pw[b] + g[b] + spread - alpha[b] * rr + 10 * Math.log10(lw);
          if (extraDb) lp += extraDb(s, r, b);
          if (ge) lp += ge[b];
          const e = Math.pow(10, lp / 10);
          energy[r * nBands + b] += e;
          wSample += e * Math.pow(10, A_WEIGHT[b] / 10);
        }
        samples.push([r, wSample, (rr / c) * 1000]);
      }
    }
    return energy;
  }

  const directE = path(
    srcM,
    lobes.map((l) => l.a),
    null,
  );

  let reflE = new Float64Array(nR * nBands);
  const doReflection = conditions.farSideReflection && stadium.farSide;
  if (doReflection) {
    const planeYFt = farSidePlaneYFt(stadium);
    const imgM = srcFt.map((s) => [
      s[0] / FT_PER_M,
      (2 * planeYFt - s[1]) / FT_PER_M,
      s[2] / FT_PER_M,
    ]);
    const imgAxes = lobes.map((l) => [l.a[0], -l.a[1], l.a[2]]);
    const reflDb = BANDS.map((_, b) =>
      10 * Math.log10(Math.max(1 - stadium.farSideAbsorption[b], 1e-4)),
    );
    const planeY = planeYFt / FT_PER_M;
    const halfW = stadium.halfWidthFt / FT_PER_M;
    const maxH = stadium.farSideHeightFt / FT_PER_M;

    const valid = (s, r) => {
      const sy = imgM[s][1];
      const ry = rcv[r][1];
      const den = sy - ry;
      if (Math.abs(den) < 1e-9) return false;
      const t = (sy - planeY) / den;
      const x = imgM[s][0] + t * (rcv[r][0] - imgM[s][0]);
      const z = imgM[s][2] + t * (rcv[r][2] - imgM[s][2]);
      return t > 0 && t < 1 && Math.abs(x) <= halfW && z >= 0 && z <= maxH;
    };
    reflE = path(imgM, imgAxes, (s, r, b) => reflDb[b] + (valid(s, r) ? 0 : -300));
  }

  const bandSpl = new Float64Array(nR * nBands);
  const directSpl = new Float64Array(nR * nBands);
  const reflectedSpl = new Float64Array(nR * nBands);
  for (let i = 0; i < nR * nBands; i++) {
    bandSpl[i] = 10 * Math.log10(Math.max(directE[i] + reflE[i], 1e-30));
    directSpl[i] = 10 * Math.log10(Math.max(directE[i], 1e-30));
    reflectedSpl[i] = 10 * Math.log10(Math.max(reflE[i], 1e-30));
  }

  // Two-pass arrival statistics, exactly as numpy computes them.
  const wsum = new Float64Array(nR);
  const wt = new Float64Array(nR);
  for (const [r, w, t] of samples) {
    wsum[r] += w;
    wt[r] += w * t;
  }
  const mean = new Float64Array(nR);
  for (let r = 0; r < nR; r++) mean[r] = wt[r] / Math.max(wsum[r], 1e-30);
  const varAcc = new Float64Array(nR);
  for (const [r, w, t] of samples) varAcc[r] += w * (t - mean[r]) ** 2;
  const spread = new Float64Array(nR);
  for (let r = 0; r < nR; r++) {
    spread[r] = Math.sqrt(Math.max(varAcc[r] / Math.max(wsum[r], 1e-30), 0));
  }

  return {
    nReceivers: nR,
    nBands,
    bandSpl,
    directSpl,
    reflectedSpl,
    arrivalMeanMs: mean,
    arrivalSpreadMs: spread,
  };
}
