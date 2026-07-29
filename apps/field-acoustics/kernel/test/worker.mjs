/**
 * Worker protocol and pool test.
 *
 * Runs the real worker entry point over `node:worker_threads`, which exercises
 * the same message handling a browser module worker uses. Checks that:
 *
 *  - a batch of jobs comes back with per-job results in job order;
 *  - an uploaded receiver grid can be referenced by id instead of resent;
 *  - transferred `Float64Array`s arrive intact and match `simulate()` exactly;
 *  - derived outputs (dBA, brightness) can be requested instead of raw bands;
 *  - a bad job produces an error reply rather than a hang.
 *
 * Usage: node kernel/test/worker.mjs
 */

import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { pathToFileURL } from 'node:url';

import {
  DEFAULT_STADIUM,
  WorkerPool,
  applyFacing,
  arcForm,
  dba,
  makeConditions,
  seatGrid,
  simulate,
} from '../dist/index.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const WORKER_URL = pathToFileURL(join(HERE, '..', 'dist', 'worker.js'));

let passed = 0;
const failures = [];
function check(name, cond, detail = '') {
  if (cond) {
    passed += 1;
    console.log(`ok    ${name}`);
  } else {
    failures.push(name);
    console.error(`FAIL  ${name} ${detail}`);
  }
}

const grid = seatGrid({ ...DEFAULT_STADIUM, nRows: 10 });
const front = applyFacing(arcForm(), 'front');
const center = applyFacing(arcForm(), 'center');
const conditions = { farSideReflection: true };

const expectFront = simulate(front, grid.points, DEFAULT_STADIUM, makeConditions(conditions));
const expectCenter = simulate(center, grid.points, DEFAULT_STADIUM, makeConditions(conditions));

const pool = new WorkerPool({ size: 2, workerUrl: WORKER_URL, batchSize: 2 });
await pool.ready();
check('pool spawned', pool.size === 2, `size=${pool.size}`);

await pool.uploadReceivers('house', grid.points);

// A whole "show": alternating facings, all referencing the uploaded grid.
const SETS = 12;
const jobs = [];
for (let i = 0; i < SETS; i++) {
  jobs.push({
    id: `set-${i}`,
    performers: i % 2 === 0 ? front : center,
    receiversRef: 'house',
    stadium: DEFAULT_STADIUM,
    conditions,
    outputs: ['bandSpl', 'arrivalMeanMs', 'arrivalSpreadMs'],
  });
}

const t0 = performance.now();
const results = await pool.run(jobs);
const elapsed = performance.now() - t0;

check('one result per job', results.length === SETS);
check(
  'results come back in job order',
  results.every((r, i) => r.id === `set-${i}`),
);

let worst = 0;
for (let i = 0; i < SETS; i++) {
  const want = i % 2 === 0 ? expectFront : expectCenter;
  const got = results[i].data.bandSpl;
  for (let k = 0; k < want.bandSpl.length; k++) {
    worst = Math.max(worst, Math.abs(got[k] - want.bandSpl[k]));
  }
}
check('worker results are bit-identical to in-process simulate', worst === 0, `worst ${worst}`);
check(
  'arrival arrays came back',
  results[0].data.arrivalMeanMs.length === grid.count &&
    results[0].data.arrivalSpreadMs.length === grid.count,
);
check(
  'unrequested outputs are omitted',
  results[0].data.directSpl === undefined && results[0].data.reflectedSpl === undefined,
);

// Derived outputs, computed worker-side.
const derived = await pool.run([
  {
    id: 'derived',
    performers: front,
    receiversRef: 'house',
    stadium: DEFAULT_STADIUM,
    conditions,
    outputs: ['dba', 'brightness'],
  },
]);
const wantDba = dba(expectFront);
let dbaWorst = 0;
for (let i = 0; i < wantDba.length; i++) {
  dbaWorst = Math.max(dbaWorst, Math.abs(derived[0].data.dba[i] - wantDba[i]));
}
check('derived dBA matches', dbaWorst === 0, `worst ${dbaWorst}`);
check('derived brightness present', derived[0].data.brightness.length === grid.count);

// Inline receivers, transferred rather than referenced.
const inline = Float64Array.from(grid.points);
const inlineRes = await pool.run([
  {
    id: 'inline',
    performers: front,
    receiversFt: inline,
    stadium: DEFAULT_STADIUM,
    conditions,
    outputs: ['bandSpl'],
  },
]);
check(
  'inline receivers work and the buffer was transferred (detached)',
  inlineRes[0].data.bandSpl.length === grid.count * 8 && inline.length === 0,
  `len=${inline.length}`,
);

// Errors surface as rejections, not hangs.
let rejected = false;
try {
  await pool.run([{ id: 'bad', performers: front, receiversRef: 'nope', outputs: ['bandSpl'] }]);
} catch {
  rejected = true;
}
check('a missing receiver grid rejects rather than hangs', rejected);

let rejected2 = false;
try {
  await pool.run([
    {
      id: 'kazoo',
      performers: [{ instrument: 'kazoo', x: 0, y: 60, fx: 0, fy: -1 }],
      receiversRef: 'house',
      outputs: ['bandSpl'],
    },
  ]);
} catch {
  rejected2 = true;
}
check('an invalid instrument rejects', rejected2);

await pool.dropReceivers('house');
await pool.terminate();

const perSet = elapsed / SETS;
console.log(
  `\n${SETS} sets across ${2} workers in ${elapsed.toFixed(0)} ms ` +
    `(${perSet.toFixed(1)} ms/set wall, ${grid.count} receivers)`,
);
console.log(`${passed} passed, ${failures.length} failed`);
if (failures.length) process.exit(1);
