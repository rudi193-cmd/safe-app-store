/**
 * Invariants the kernel must not violate.
 *
 * These are the load-bearing tests from `test_dcisim.py`, ported. They are not
 * a substitute for the differential test — they check that the model still
 * makes physical sense, where the differential test checks that the port agrees
 * with the original. A port can pass one and fail the other.
 *
 * Skipped deliberately: everything in `test_dcisim.py` that exercises the SOFA
 * loader, the provenance ledger, the CSV round-trip or `dcisim.drill`'s file
 * handling — none of which is part of the propagation kernel.
 *
 * Usage: node kernel/test/invariants.mjs
 */

import {
  A_WEIGHT,
  BANDS,
  CATALOG,
  DEFAULT_FRONT_TO_BACK,
  DEFAULT_STADIUM,
  Directivity,
  FT_PER_M,
  Instrument,
  REFERENCE_DI,
  absorptionCoefficients,
  applyFacing,
  arcForm,
  blockForm,
  brightness,
  dba,
  makeConditions,
  makeStadium,
  namedSeats,
  reflectedRatioDb,
  seatGrid,
  simulate,
} from '../dist/index.js';

const REF = new Float64Array([0.0, -30.0, 12.0, 90.0, -60.0, 40.0]);

let passed = 0;
const failures = [];

function test(name, fn) {
  try {
    fn();
    passed += 1;
    console.log(`ok    ${name}`);
  } catch (err) {
    failures.push([name, err]);
    console.error(`FAIL  ${name}\n      ${err.message}`);
  }
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg ?? 'assertion failed');
}
/**
 * `numpy.allclose` semantics for a single pair: `|a - b| <= atol + rtol*|b|`.
 * The Python tests these are ported from use `np.allclose`, whose default
 * `rtol=1e-5` does most of the work at 70-100 dB levels. Porting the assertion
 * as a bare absolute tolerance would have been a *stricter* test than the
 * original, which is not the same thing as a faithful one.
 */
function close(a, b, atol, msg, rtol = 1e-5) {
  const tol = atol + rtol * Math.abs(b);
  assert(Math.abs(a - b) <= tol, `${msg ?? ''} |${a} - ${b}| = ${Math.abs(a - b)} > ${tol}`);
}
function expectThrow(fn, msg) {
  let threw = false;
  try {
    fn();
  } catch {
    threw = true;
  }
  assert(threw, msg ?? 'expected a throw');
}
function mean(a) {
  let s = 0;
  for (const v of a) s += v;
  return s / a.length;
}

const NO_REFL = makeConditions({ farSideReflection: false });

// --- directivity ------------------------------------------------------------

test('pattern is unity on axis', () => {
  const d = new Directivity(0.062);
  for (const v of d.patternDb(0.0)) close(v, 0.0, 1e-6, 'on-axis pattern');
});

test('on-axis gain equals the directivity index', () => {
  // If `gainDb` were normalised to 0 dB on axis instead, `Lw` would silently
  // stop meaning sound power and the radiated spectrum would tilt by the DI —
  // about 13 dB at 8 kHz, wrecking every A-weighted and HF/LF number.
  const d = new Directivity(0.13);
  const g = d.gainDb(0.0);
  const di = d.directivityIndexDb();
  for (let b = 0; b < 8; b++) close(g[b], di[b], 1e-9, `band ${b}`);
});

test('no direction is louder than the axis', () => {
  for (const [radius] of Object.values(REFERENCE_DI)) {
    const d = new Directivity(radius);
    const nT = d.nTheta;
    for (const v of d.table) assert(v <= 1.0 + 1e-9, 'table exceeds unity');
    for (let b = 0; b < 8; b++) {
      assert(d.table[b * nT + nT - 1] <= d.table[b * nT], 'rear exceeds axis');
    }
  }
});

test('rear response never dips below the stated front-to-back ratio', () => {
  // Tapering the sidelobe floor along with everything else lets the response
  // dive past the stated ratio around 140-170 degrees before climbing back to
  // it — up to 12 dB past, for percussion at 8 kHz. It is invisible to the
  // directivity-index calibration and it is not common-mode across the facing
  // experiment, so it gets its own test.
  for (const [name, inst] of [...CATALOG].sort((a, b) => (a[0] < b[0] ? -1 : 1))) {
    const d = inst.directivity();
    const nT = d.nTheta;
    for (let b = 0; b < 8; b++) {
      const floor = -inst.frontToBack[b];
      let worst = Infinity;
      for (let i = 0; i < nT; i++) {
        if (d.theta[i] < Math.PI / 2) continue;
        worst = Math.min(worst, 20 * Math.log10(d.table[b * nT + i]));
      }
      assert(
        worst >= floor - 1e-6,
        `${name} band ${b} dips to ${worst.toFixed(2)} dB against a stated ${floor}`,
      );
      close(20 * Math.log10(d.table[b * nT + nT - 1]), floor, 1e-6, `${name} band ${b} at 180 deg`);
    }
  }
});

test('directivity falls monotonically through the rear hemisphere', () => {
  for (const [radius] of Object.values(REFERENCE_DI)) {
    const d = new Directivity(radius);
    const nT = d.nTheta;
    for (let b = 0; b < 8; b++) {
      for (let i = 0; i + 1 < nT; i++) {
        if (d.theta[i] < Math.PI / 2) continue;
        assert(d.table[b * nT + i + 1] - d.table[b * nT + i] <= 1e-9, `band ${b} rises at ${i}`);
      }
    }
  }
});

test('directivity index matches published values', () => {
  for (const [name, [radius, target]] of Object.entries(REFERENCE_DI)) {
    const di = new Directivity(radius).directivityIndexDb();
    let s = 0;
    for (let b = 0; b < 8; b++) s += (di[b] - target[b]) ** 2;
    assert(Math.sqrt(s / 8) < 2.0, `${name} drifted`);
  }
});

test('high frequencies are more directional than low', () => {
  const di = new Directivity(0.13).directivityIndexDb();
  for (let b = 1; b < 8; b++) assert(di[b] - di[b - 1] > 0.0, `band ${b} is not more directional`);
});

// --- propagation ------------------------------------------------------------

test('radiated sound power matches the declared Lw', () => {
  // Integrate intensity over a sphere at 10 m and recover Lw. The only
  // legitimate shortfall is air absorption over that radius.
  const h = CATALOG.get('trumpet').bellHeightM * FT_PER_M;
  const nT = 160;
  const nP = 320;
  const th = new Float64Array(nT);
  for (let i = 0; i < nT; i++) th[i] = 1e-3 + ((Math.PI - 2e-3) * i) / (nT - 1);
  const dFt = 10.0 * FT_PER_M;

  const rcv = new Float64Array(nT * nP * 3);
  let k = 0;
  for (let i = 0; i < nT; i++) {
    for (let j = 0; j < nP; j++) {
      const ph = (2 * Math.PI * j) / nP;
      rcv[k++] = dFt * Math.sin(th[i]) * Math.cos(ph);
      rcv[k++] = 60.0 + dFt * Math.sin(th[i]) * Math.sin(ph);
      rcv[k++] = h + dFt * Math.cos(th[i]);
    }
  }

  const res = simulate(
    [{ instrument: 'trumpet', x: 0.0, y: 60.0, fx: 0.0, fy: -1.0 }],
    rcv,
    DEFAULT_STADIUM,
    NO_REFL,
  );
  const alpha = absorptionCoefficients();
  const pw = CATALOG.get('trumpet').powerDb;
  for (let b = 0; b < 8; b++) {
    let num = 0;
    let den = 0;
    for (let i = 0; i < nT; i++) {
      const w = Math.sin(th[i]);
      for (let j = 0; j < nP; j++) {
        num += w * Math.pow(10, res.bandSpl[(i * nP + j) * 8 + b] / 10);
        den += w;
      }
    }
    const implied = 10 * Math.log10(num / den) + 20 * Math.log10(10.0) + 11.0;
    const err = implied - pw[b] + alpha[b] * 10.0;
    assert(Math.abs(err) < 0.15, `band ${b} radiated power off by ${err.toFixed(3)} dB`);
  }
});

test('inverse square holds for a single source', () => {
  const p = [{ instrument: 'trumpet', x: 0.0, y: 60.0, fx: 0.0, fy: -1.0 }];
  const near = simulate(p, [[0.0, 60.0 - 32.8, 5.2]], DEFAULT_STADIUM, NO_REFL);
  const far = simulate(p, [[0.0, 60.0 - 65.6, 5.2]], DEFAULT_STADIUM, NO_REFL);
  // 10 m -> 20 m, low band so air absorption is negligible.
  close(near.bandSpl[1] - far.bandSpl[1], 6.02, 0.15, 'inverse square');
});

test('direction cosines use the true range, not the clamped one', () => {
  // Normalising by the clamped range shortens the direction vector, pulling
  // every angle toward 90 degrees and flattening the instrument out: a
  // trumpet's 8 kHz front-to-back ratio fell from 24 dB to 1 dB at 0.1 m.
  const p = [{ instrument: 'trumpet', x: 0.0, y: 60.0, fx: 0.0, fy: -1.0 }];
  const h = CATALOG.get('trumpet').bellHeightM * FT_PER_M;
  for (const dist of [0.3, 1.0, 3.0, 30.0]) {
    const front = simulate(p, [[0.0, 60.0 - dist, h]], DEFAULT_STADIUM, NO_REFL);
    const back = simulate(p, [[0.0, 60.0 + dist, h]], DEFAULT_STADIUM, NO_REFL);
    const ratio = front.bandSpl[7] - back.bandSpl[7];
    assert(ratio > 20.0, `8 kHz front/back collapsed to ${ratio.toFixed(1)} dB at ${dist} ft`);
  }
});

test('sections sum energetically to the whole ensemble', () => {
  const base = applyFacing(arcForm(), 'front');
  const st = makeStadium({ nRows: 6 });
  const seats = seatGrid(st).points;
  const whole = simulate(base, seats, st);
  const total = new Float64Array(whole.bandSpl.length);
  for (const name of new Set(base.map((p) => p.instrument))) {
    const part = base.filter((p) => p.instrument === name);
    const r = simulate(part, seats, st);
    for (let i = 0; i < total.length; i++) total[i] += Math.pow(10, r.bandSpl[i] / 10);
  }
  let worst = 0;
  for (let i = 0; i < total.length; i++) {
    worst = Math.max(worst, Math.abs(10 * Math.log10(total[i]) - whole.bandSpl[i]));
  }
  // The Python assertion is `np.allclose(..., atol=1e-9)`, i.e. 1e-9 + 1e-5*|Lp|
  // — about 7e-4 dB at these levels. Additivity is *not* exact in the
  // restructured kernel: the air-absorption table's domain is sized from the
  // bounding box of whichever sources are present, so a section and the whole
  // ensemble quantise `r` slightly differently. Measured drift is ~3e-8 dB;
  // pass `absorptionTableSize: 0` to make additivity exact to round-off.
  assert(worst < 1e-5, `sections drift from the whole by ${worst.toExponential(2)} dB`);
});

test('a symmetric form produces a symmetric field', () => {
  const band = [-40.0, -20.0, 0.0, 20.0, 40.0].map((x) => ({
    instrument: 'trumpet',
    x,
    y: 60.0,
    fx: 0.0,
    fy: -1.0,
  }));
  const pair = [
    [-80.0, -30.0, 12.0],
    [80.0, -30.0, 12.0],
  ];
  for (const mode of ['front', 'center']) {
    const r = simulate(applyFacing(band, mode, [0.0, 80.0]), pair);
    const l = dba(r);
    assert(Math.abs(l[0] - l[1]) < 1e-9, `${mode}: field is asymmetric by ${l[0] - l[1]}`);
  }
});

test('an omnidirectional source does not care which way it faces', () => {
  const omni = new Instrument({
    name: 'omni',
    powerDb: new Array(8).fill(110.0),
    bellRadiusM: 0.0,
    bellHeightM: 1.6,
    frontToBack: new Array(8).fill(0.0),
  });
  const catalog = new Map([...CATALOG, ['omni', omni]]);
  const band = [-30.0, 0.0, 30.0].map((x) => ({
    instrument: 'omni',
    x,
    y: 60.0,
    fx: 0.0,
    fy: -1.0,
  }));
  const opt = { catalog };
  const fwd = dba(simulate(applyFacing(band, 'front'), REF, DEFAULT_STADIUM, undefined, opt));
  const ctr = dba(simulate(applyFacing(band, 'center'), REF, DEFAULT_STADIUM, undefined, opt));
  for (let i = 0; i < fwd.length; i++) close(fwd[i], ctr[i], 1e-6, 'omni facing');
});

test('the amplified pit is unaffected by the drill facing', () => {
  const pit = [
    { instrument: 'pit', x: -20.0, y: 2.0, fx: 0.0, fy: -1.0 },
    { instrument: 'pit', x: 20.0, y: 2.0, fx: 0.0, fy: -1.0 },
  ];
  const fwd = dba(simulate(applyFacing(pit, 'front'), REF));
  const ctr = dba(simulate(applyFacing(pit, 'center'), REF));
  for (let i = 0; i < fwd.length; i++) close(fwd[i], ctr[i], 1e-12, 'pit facing');
});

test('a centred bass line barely notices turning in', () => {
  // Two opposed half-power lobes nearly map onto each other under the flip, so
  // any apparent bass-drum "result" is really a report on how far off centre
  // the bass line was placed.
  const st = makeStadium({ nRows: 8 });
  const seats = seatGrid(st).points;
  const basses = [-7.5, -2.5, 2.5, 7.5].map((x) => ({
    instrument: 'bass',
    x,
    y: 30.0,
    fx: 0.0,
    fy: -1.0,
  }));
  const fwd = dba(simulate(applyFacing(basses, 'front'), seats, st));
  const ctr = dba(simulate(applyFacing(basses, 'center'), seats, st));
  let worst = 0;
  for (let i = 0; i < fwd.length; i++) worst = Math.max(worst, Math.abs(ctr[i] - fwd[i]));
  assert(worst < 0.15, `bass line moved by ${worst.toFixed(3)} dB`);

  const horns = [-7.5, -2.5, 2.5, 7.5].map((x) => ({
    instrument: 'trumpet',
    x,
    y: 30.0,
    fx: 0.0,
    fy: -1.0,
  }));
  const hf = dba(simulate(applyFacing(horns, 'front'), seats, st));
  const hc = dba(simulate(applyFacing(horns, 'center'), seats, st));
  const hornDelta = Math.abs(mean(hc) - mean(hf));
  const bassDelta = Math.abs(mean(ctr) - mean(fwd));
  assert(hornDelta > 20 * bassDelta, 'bass responds comparably to a hornline');
});

test('turning in costs level and costs more treble than bass', () => {
  const base = arcForm();
  const st = makeStadium({ nRows: 20 });
  const seats = seatGrid(st).points;
  const fwd = simulate(applyFacing(base, 'front'), seats, st);
  const ctr = simulate(applyFacing(base, 'center'), seats, st);
  const lf = dba(fwd);
  const lc = dba(ctr);
  for (let i = 0; i < lf.length; i++) {
    assert(lc[i] < lf[i], 'facing in should never be louder in the house');
  }
  const perBand = new Float64Array(8);
  for (let b = 0; b < 8; b++) {
    let s = 0;
    for (let r = 0; r < fwd.nReceivers; r++) s += ctr.bandSpl[r * 8 + b] - fwd.bandSpl[r * 8 + b];
    perBand[b] = s / fwd.nReceivers;
  }
  assert(perBand[7] < perBand[0], '8 kHz must suffer more than 63 Hz');
  const db = brightness(ctr);
  const fb = brightness(fwd);
  let acc = 0;
  for (let i = 0; i < db.length; i++) acc += db[i] - fb[i];
  assert(acc / db.length < -1.0, 'brightness barely moved');
});

test('turning in increases arrival spread and reflected ratio', () => {
  const base = arcForm();
  const st = makeStadium({ nRows: 12 });
  const seats = seatGrid(st).points;
  const cond = makeConditions({ farSideReflection: true });
  const fwd = simulate(applyFacing(base, 'front'), seats, st, cond);
  const ctr = simulate(applyFacing(base, 'center'), seats, st, cond);
  assert(mean(ctr.arrivalSpreadMs) > mean(fwd.arrivalSpreadMs), 'arrival spread did not grow');
  assert(
    mean(reflectedRatioDb(ctr)) > mean(reflectedRatioDb(fwd)),
    'reflected ratio did not grow',
  );
});

test('reflection only ever adds energy and can be switched off', () => {
  const base = applyFacing(arcForm(), 'front');
  const st = makeStadium({ nRows: 6 });
  const seats = seatGrid(st).points;
  const on = simulate(base, seats, st, makeConditions({ farSideReflection: true }));
  const off = simulate(base, seats, st, NO_REFL);
  for (let i = 0; i < on.bandSpl.length; i++) {
    assert(on.bandSpl[i] >= off.bandSpl[i] - 1e-9, `reflection removed energy at ${i}`);
  }
  const dead = simulate(
    base,
    seats,
    makeStadium({ nRows: 6, farSideAbsorption: new Array(8).fill(1.0) }),
    makeConditions({ farSideReflection: true }),
  );
  for (let i = 0; i < dead.bandSpl.length; i++) close(dead.bandSpl[i], off.bandSpl[i], 1e-6, 'dead');
  const distant = simulate(
    base,
    seats,
    makeStadium({ nRows: 6, farSideSetbackFt: 5000.0 }),
    makeConditions({ farSideReflection: true }),
  );
  for (let i = 0; i < distant.bandSpl.length; i++) {
    close(distant.bandSpl[i], off.bandSpl[i], 0.05, 'distant');
  }
});

test('level falls monotonically with distance', () => {
  const base = applyFacing(arcForm(), 'front');
  const line = [];
  for (let i = 0; i < 40; i++) line.push([0.0, -(30.0 + (370.0 * i) / 39), 12.0]);
  const lv = dba(simulate(base, line, DEFAULT_STADIUM, NO_REFL));
  for (let i = 1; i < lv.length; i++) assert(lv[i] < lv[i - 1], `level rose at step ${i}`);
});

test('levels land in a plausible range for a corps', () => {
  const fwd = dba(simulate(applyFacing(arcForm(), 'front'), [[0.0, -30.0, 12.0]]));
  assert(fwd[0] > 88.0 && fwd[0] < 105.0, `${fwd[0].toFixed(1)} dBA is not plausible`);
});

// --- input handling ---------------------------------------------------------

test('an empty ensemble is silence, not a crash', () => {
  const res = simulate([], REF);
  assert(res.bandSpl.length === 2 * 8, 'wrong shape');
  for (const v of res.bandSpl) assert(v < -200.0, 'not silent');
  for (const v of res.arrivalMeanMs) assert(Number.isNaN(v), 'arrival should be NaN');
});

test('unknown instruments and degenerate inputs are rejected', () => {
  let msg = '';
  try {
    simulate([{ instrument: 'kazoo', x: 0, y: 60, fx: 0, fy: -1 }], REF);
  } catch (e) {
    msg = e.message;
  }
  assert(msg.includes('kazoo') && msg.includes('trumpet'), `unhelpful message: ${msg}`);

  expectThrow(() => simulate([{ instrument: 'trumpet', x: NaN, y: 60, fx: 0, fy: -1 }], REF));
  expectThrow(() => simulate([{ instrument: 'trumpet', x: 0, y: 60, fx: 0, fy: 0 }], REF));
  expectThrow(() =>
    simulate([{ instrument: 'trumpet', x: 0, y: 60, fx: 0, fy: -1 }], [[0, Infinity, 5]]),
  );
  expectThrow(() =>
    simulate(
      [{ instrument: 'trumpet', x: 0, y: 60, fx: 0, fy: -1 }],
      new Float64Array([0, -30, 12, 4]),
    ),
  );
});

test('impossible atmospheres are rejected', () => {
  const p = [{ instrument: 'trumpet', x: 0, y: 60, fx: 0, fy: -1 }];
  expectThrow(() => simulate(p, REF, DEFAULT_STADIUM, makeConditions({ tempC: -300 })));
  expectThrow(() => simulate(p, REF, DEFAULT_STADIUM, makeConditions({ humidityPct: -5 })));
  expectThrow(() => simulate(p, REF, DEFAULT_STADIUM, makeConditions({ humidityPct: 150 })));
});

test('instruments do not share one front-to-back array', () => {
  assert(CATALOG.get('trumpet').frontToBack !== CATALOG.get('contra').frontToBack, 'brass share');
  assert(CATALOG.get('snare').frontToBack !== CATALOG.get('bass').frontToBack, 'battery share');
  for (let b = 0; b < 8; b++) close(CATALOG.get('trumpet').frontToBack[b], DEFAULT_FRONT_TO_BACK[b], 0);
});

test('the directivity cache respects temperature and geometry', () => {
  const inst = CATALOG.get('trumpet');
  const cold = inst.directivity(0.0);
  const hot = inst.directivity(50.0);
  assert(cold !== hot, 'cache ignored temperature');
  let same = true;
  for (let i = 0; i < cold.table.length; i++) {
    if (Math.abs(cold.table[i] - hot.table[i]) > 1e-12) {
      same = false;
      break;
    }
  }
  assert(!same, 'temperature did not change the table');

  const radius = inst.bellRadiusM;
  const ftb = inst.frontToBack;
  try {
    const before = Float64Array.from(inst.directivity().table);
    inst.bellRadiusM = 0.6;
    assert(inst.directivity().table.some((v, i) => Math.abs(v - before[i]) > 1e-12), 'radius');
    inst.bellRadiusM = radius;
    inst.frontToBack = new Array(8).fill(0.0);
    assert(inst.directivity().table.some((v, i) => Math.abs(v - before[i]) > 1e-12), 'ftb');
  } finally {
    inst.bellRadiusM = radius;
    inst.frontToBack = ftb;
  }
});

// --- geometry ---------------------------------------------------------------

test('facing is idempotent', () => {
  const base = blockForm();
  const once = applyFacing(base, 'front');
  const twice = applyFacing(once, 'front');
  for (let i = 0; i < once.length; i++) {
    assert(
      once[i].fx === twice[i].fx && once[i].fy === twice[i].fy && once[i].x === twice[i].x,
      `performer ${i} moved`,
    );
  }
});

test('an empty section list is honoured rather than replaced', () => {
  for (const form of [blockForm, arcForm]) {
    assert(
      form({ instrumentation: [], battery: [], pit: [] }).length === 0,
      'empty request was replaced',
    );
    const onlyBattery = form({ instrumentation: [], pit: [] });
    assert(onlyBattery.length > 0, 'battery vanished');
    for (const p of onlyBattery) {
      assert(['snare', 'tenor', 'bass'].includes(p.instrument), `stray ${p.instrument}`);
    }
  }
  expectThrow(() => blockForm({ perRow: 0 }));
  expectThrow(() => arcForm({ perRank: 0 }));
});

test('a leftover single performer lands on the arc centre', () => {
  const form = arcForm({
    instrumentation: [['mellophone', 19]],
    battery: [],
    pit: [],
    perRank: 18,
  });
  assert(Math.abs(form[form.length - 1].x) < 1e-6, `stranded at x=${form[form.length - 1].x}`);
});

test('the battery is laid out symmetrically', () => {
  const form = blockForm();
  for (const name of ['snare', 'tenor', 'bass']) {
    const xs = form.filter((p) => p.instrument === name).map((p) => p.x);
    const s = xs.reduce((a, b) => a + b, 0);
    assert(Math.abs(s) < 1e-6, `${name} line is off centre by ${s}`);
  }
});

test('reference seats stay inside a short grandstand', () => {
  for (const n of [1, 2, 3, 40]) {
    const st = makeStadium({ nRows: n });
    const lowest = -(st.apronFt + (n - 1) * st.rowDepthFt);
    for (const pos of namedSeats(st).values()) {
      assert(pos[1] >= lowest - 1e-9, `seat extrapolated past row ${n - 1}`);
    }
  }
  expectThrow(() => namedSeats(makeStadium({ nRows: 0 })));
});

test('the A-weighting and band tables are the published ones', () => {
  const bands = [63, 125, 250, 500, 1000, 2000, 4000, 8000];
  const aw = [-26.2, -16.1, -8.6, -3.2, 0.0, 1.2, 1.0, -1.1];
  for (let b = 0; b < 8; b++) {
    close(BANDS[b], bands[b], 0, `band ${b}`);
    close(A_WEIGHT[b], aw[b], 0, `A-weight ${b}`);
  }
});

// ---------------------------------------------------------------------------

console.log(`\n${passed} passed, ${failures.length} failed`);
if (failures.length) process.exit(1);
