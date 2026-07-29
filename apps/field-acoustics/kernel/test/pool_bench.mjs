/**
 * Worker-pool scaling over a 24-set show on the full 1640-seat grid.
 *
 * Each pool is warmed with one batch per worker before timing, because the
 * first job in a worker pays ~70 ms to build the directivity and cos tables for
 * all eight instruments. That cost is real but it is once per worker, not once
 * per set, so charging it to the first set would misrepresent a show.
 *
 * Usage: node kernel/test/pool_bench.mjs [--sets N] [--batch N]
 */

import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

import { DEFAULT_STADIUM, WorkerPool, applyFacing, arcForm, seatGrid } from '../dist/index.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const WORKER_URL = pathToFileURL(join(HERE, '..', 'dist', 'worker.js'));
const arg = (name, dflt) => {
  const i = process.argv.indexOf(name);
  return i >= 0 ? Number(process.argv[i + 1]) : dflt;
};

const SETS = arg('--sets', 24);
const BATCH = arg('--batch', 3);

const grid = seatGrid(DEFAULT_STADIUM);
const front = applyFacing(arcForm(), 'front');
const center = applyFacing(arcForm(), 'center');
const jobs = [];
for (let i = 0; i < SETS; i++) {
  jobs.push({
    id: i,
    performers: i % 2 ? front : center,
    receiversRef: 'house',
    stadium: DEFAULT_STADIUM,
    conditions: { farSideReflection: true },
    outputs: ['bandSpl'],
  });
}

const cores = (globalThis.navigator?.hardwareConcurrency) ?? 4;
console.log(
  `${SETS} sets x ${grid.count} receivers x 8 bands, batch ${BATCH} ` +
    `(node ${process.version}, ${cores} logical cores)\n`,
);

for (const n of [1, 2, 4, 8]) {
  const pool = new WorkerPool({ size: n, workerUrl: WORKER_URL, batchSize: BATCH });
  await pool.ready();
  await pool.uploadReceivers('house', grid.points);
  await pool.run(jobs.slice(0, n * BATCH)); // warm every worker's tables
  const t0 = performance.now();
  await pool.run(jobs);
  const elapsed = performance.now() - t0;
  console.log(
    `  ${String(n).padStart(2)} worker(s): ${elapsed.toFixed(0).padStart(5)} ms total, ` +
      `${(elapsed / SETS).toFixed(2)} ms/set wall`,
  );
  await pool.terminate();
}
