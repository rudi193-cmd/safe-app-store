/**
 * Differential test: the TypeScript kernel against the Python implementation.
 *
 * `gen_reference.py` runs `dcisim` over a randomised ensemble — mixed
 * instruments, unnormalised facings, both facing modes, reflection on and off,
 * ground effect on and off, varied atmospheres and stadium geometry — and dumps
 * inputs plus outputs. This replays every case through the port and reports the
 * disagreement in dB.
 *
 * It also runs several kernel configurations so the error can be attributed:
 *
 *   exact         cos table 1<<20, no absorption table (Math.exp)  — isolates
 *                 everything that is *not* the two lookup tables
 *   f64           the shipping default (cos 4096, absorption 8192, Float64)
 *   f32           the same tables in Float32
 *   noAbsTable    default cos table, exact exponential
 *
 * Usage: node kernel/test/differential.mjs [--verbose]
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  BANDS,
  Directivity,
  absorptionCoefficients,
  besselJ1,
  brightness,
  dba,
  makeConditions,
  makeStadium,
  reflectedRatioDb,
  simulate,
  speedOfSound,
} from '../dist/index.js';
import { CATALOG } from '../dist/instruments.js';
import { referenceSimulate } from './reference_kernel.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const VERBOSE = process.argv.includes('--verbose');

const ref = JSON.parse(readFileSync(join(HERE, 'reference.json'), 'utf8'));

let failures = 0;
function fail(msg) {
  failures += 1;
  console.error(`FAIL  ${msg}`);
}
function ok(msg) {
  if (VERBOSE) console.log(`ok    ${msg}`);
}

class Acc {
  constructor(label, unit = 'dB') {
    this.label = label;
    this.unit = unit;
    this.max = 0;
    this.sum2 = 0;
    this.n = 0;
    this.worst = null;
  }
  add(got, want, where) {
    if (want === null || Number.isNaN(want)) {
      if (!(got === null || Number.isNaN(got))) {
        fail(`${this.label}: expected NaN at ${where}, got ${got}`);
      }
      return;
    }
    const d = Math.abs(got - want);
    this.sum2 += d * d;
    this.n += 1;
    if (d > this.max) {
      this.max = d;
      this.worst = where;
    }
  }
  get rms() {
    return this.n ? Math.sqrt(this.sum2 / this.n) : 0;
  }
  report() {
    return `${this.label}: max ${this.max.toExponential(3)} ${this.unit}, rms ${this.rms.toExponential(
      3,
    )} ${this.unit} over ${this.n} values${this.worst ? ` (worst at ${this.worst})` : ''}`;
  }
}

// ---------------------------------------------------------------------------
// 1. Isolated probes
// ---------------------------------------------------------------------------

function probeBessel() {
  const { x, y } = ref.probes.besselJ1;
  let maxAbs = 0;
  let maxRel = 0;
  for (let i = 0; i < x.length; i++) {
    const got = besselJ1(x[i]);
    const d = Math.abs(got - y[i]);
    maxAbs = Math.max(maxAbs, d);
    if (Math.abs(y[i]) > 1e-3) maxRel = Math.max(maxRel, d / Math.abs(y[i]));
  }
  const line = `besselJ1 vs scipy: max abs ${maxAbs.toExponential(3)}, max rel ${maxRel.toExponential(3)}`;
  if (maxAbs > 1e-11) fail(line);
  else ok(line);
  return line;
}

function probeAtmosphere() {
  let maxC = 0;
  for (let i = 0; i < ref.probes.speedOfSound.tempC.length; i++) {
    maxC = Math.max(
      maxC,
      Math.abs(speedOfSound(ref.probes.speedOfSound.tempC[i]) - ref.probes.speedOfSound.c[i]),
    );
  }
  let maxA = 0;
  for (const p of ref.probes.absorption) {
    const got = absorptionCoefficients(BANDS, p.tempC, p.humidityPct, p.pressureKpa);
    for (let b = 0; b < 8; b++) {
      maxA = Math.max(maxA, Math.abs(got[b] - p.alpha[b]) / Math.abs(p.alpha[b]));
    }
  }
  const line = `speedOfSound max abs ${maxC.toExponential(3)} m/s; absorption max rel ${maxA.toExponential(3)}`;
  if (maxC > 1e-12 || maxA > 1e-13) fail(line);
  else ok(line);
  return line;
}

function probeDirectivity() {
  const di = new Acc('directivity index', 'dB');
  const amp = new Acc('directivity amplitude', 'rel');
  for (const [key, want] of Object.entries(ref.probes.directivityIndex)) {
    const [name, temp] = key.split('@');
    const d = CATALOG.get(name).directivity(Number(temp));
    const got = d.directivityIndexDb();
    for (let b = 0; b < 8; b++) di.add(got[b], want[b], `${key} band ${b}`);

    const t = ref.probes.directivityTable[key];
    const nT = d.nTheta;
    for (let b = 0; b < 8; b++) {
      for (let k = 0; k < t.thetaIndex.length; k++) {
        const i = t.thetaIndex[k];
        const g = d.table[b * nT + i];
        const w = t.amp[b * t.thetaIndex.length + k];
        amp.add(w === 0 ? g : g / w - 1, 0, `${key} b${b} i${i}`);
      }
    }
  }
  if (di.max > 1e-10) fail(di.report());
  else ok(di.report());
  if (amp.max > 1e-11) fail(amp.report());
  else ok(amp.report());
  return [di.report(), amp.report()];
}

// ---------------------------------------------------------------------------
// 2. Full-model cases
// ---------------------------------------------------------------------------

const CONFIGS = {
  literal: { literal: true },
  fine: { cosTableSize: 1 << 17, absorptionTableSize: 1 << 17, tablePrecision: 'f64' },
  f64: { cosTableSize: 16384, absorptionTableSize: 8192, tablePrecision: 'f64' },
  f32: { cosTableSize: 16384, absorptionTableSize: 8192, tablePrecision: 'f32' },
  coarse: { cosTableSize: 4096, absorptionTableSize: 8192, tablePrecision: 'f64' },
};

function runConfig(label, options) {
  const spl = new Acc(`${label} band SPL`, 'dB');
  const direct = new Acc(`${label} direct SPL`, 'dB');
  const refl = new Acc(`${label} reflected SPL`, 'dB');
  const dbaAcc = new Acc(`${label} dBA`, 'dB');
  const brightAcc = new Acc(`${label} brightness`, 'dB');
  const ratioAcc = new Acc(`${label} reflected ratio`, 'dB');
  const meanAcc = new Acc(`${label} arrival mean`, 'ms');
  const spreadAcc = new Acc(`${label} arrival spread`, 'ms');

  for (const c of ref.cases) {
    const rcv = Float64Array.from(c.receiversFt);
    const res = options.literal
      ? referenceSimulate(c.performers, rcv, makeStadium(c.stadium), makeConditions(c.conditions))
      : simulate(
          c.performers,
          rcv,
          makeStadium(c.stadium),
          makeConditions(c.conditions),
          options,
        );
    if (res.nReceivers !== c.nReceivers) {
      fail(`${label} ${c.name}: receiver count ${res.nReceivers} != ${c.nReceivers}`);
      continue;
    }
    const n = c.nReceivers;
    for (let i = 0; i < n * 8; i++) {
      // Values pinned at the -300 dB silence floor carry no information; both
      // sides land there exactly, so they are compared but never dominate.
      spl.add(res.bandSpl[i], c.bandSpl[i], `${c.name}[${i}]`);
      direct.add(res.directSpl[i], c.directSpl[i], `${c.name}[${i}]`);
      refl.add(res.reflectedSpl[i], c.reflectedSpl[i], `${c.name}[${i}]`);
    }
    const gotDba = dba(res);
    const gotBright = brightness(res);
    const gotRatio = reflectedRatioDb(res);
    for (let r = 0; r < n; r++) {
      dbaAcc.add(gotDba[r], c.dba[r], `${c.name}[${r}]`);
      brightAcc.add(gotBright[r], c.brightness[r], `${c.name}[${r}]`);
      ratioAcc.add(gotRatio[r], c.reflectedRatioDb[r], `${c.name}[${r}]`);
      meanAcc.add(res.arrivalMeanMs[r], c.arrivalMeanMs[r], `${c.name}[${r}]`);
      spreadAcc.add(res.arrivalSpreadMs[r], c.arrivalSpreadMs[r], `${c.name}[${r}]`);
    }
  }
  return { spl, direct, refl, dbaAcc, brightAcc, ratioAcc, meanAcc, spreadAcc };
}

// ---------------------------------------------------------------------------

console.log(`differential test: ${ref.cases.length} cases from ${ref.generator}\n`);
console.log('-- isolated probes --');
console.log(' ', probeBessel());
console.log(' ', probeAtmosphere());
for (const l of probeDirectivity()) console.log(' ', l);

console.log('\n-- full model, per kernel configuration --');
const TOLERANCE = {
  // `literal` is the unrestructured transcription in test/reference_kernel.mjs.
  // It evaluates the same acos/log10/10^x the Python does, so the only thing
  // separating it from numpy is summation order: it must agree at round-off.
  // This is what establishes that the *port* is faithful; every other row
  // measures what the restructuring costs on top of a correct port.
  literal: { spl: 1e-10, arrival: 1e-9 },
  fine: { spl: 1e-3, arrival: 1e-3 },
  f64: { spl: 1e-3, arrival: 1e-3 },
  f32: { spl: 1e-3, arrival: 1e-3 },
  coarse: { spl: 5e-3, arrival: 1e-3 },
};

const summary = {};
for (const [label, options] of Object.entries(CONFIGS)) {
  const t0 = performance.now();
  const r = runConfig(label, options);
  const elapsed = performance.now() - t0;
  const tol = TOLERANCE[label];
  const worstSpl = Math.max(r.spl.max, r.direct.max, r.refl.max, r.dbaAcc.max, r.brightAcc.max);
  const worstT = Math.max(r.meanAcc.max, r.spreadAcc.max);
  summary[label] = { worstSpl, worstT, rms: r.spl.rms };

  console.log(`\n[${label}] ${JSON.stringify(options)}  (${elapsed.toFixed(0)} ms)`);
  for (const acc of [
    r.spl,
    r.direct,
    r.refl,
    r.dbaAcc,
    r.brightAcc,
    r.ratioAcc,
    r.meanAcc,
    r.spreadAcc,
  ]) {
    console.log('   ' + acc.report());
  }
  if (worstSpl > tol.spl) fail(`${label}: worst level error ${worstSpl.toExponential(3)} dB > ${tol.spl}`);
  if (worstT > tol.arrival) {
    fail(`${label}: worst arrival error ${worstT.toExponential(3)} ms > ${tol.arrival}`);
  }
}

console.log('\n-- headline --');
for (const [label, s] of Object.entries(summary)) {
  console.log(
    `  ${label.padEnd(11)} max level ${s.worstSpl.toExponential(3)} dB   rms ${s.rms.toExponential(
      3,
    )} dB   max arrival ${s.worstT.toExponential(3)} ms`,
  );
}

if (failures) {
  console.error(`\n${failures} differential check(s) failed`);
  process.exit(1);
}
console.log('\nall differential checks passed');
