/**
 * Benchmark: one "set" is 77 sources x 1640 receivers x 8 bands.
 *
 * 77 is `arcForm()`'s default corps (50 brass + 19 battery + 8 front ensemble)
 * and 1640 is the default grandstand (41 seats across x 40 rows). Five bass
 * drums radiate from two heads apiece, so the kernel actually walks 82 lobes.
 * With the far-side reflection on that is 82 * 1640 * 8 * 2 = 2.15 M band
 * evaluations per set.
 *
 * **Each case runs in its own process.** Timing them all in one process
 * understated the default configuration by ~30%: `Float64Array` and
 * `Float32Array` tables both flowing through `accumulatePath` make the inner
 * loop polymorphic, and V8 does not recover the monomorphic code once it has
 * seen both. That is a deployment hazard as much as a benchmarking one — pick
 * one `tablePrecision` per process and stay with it.
 *
 * Usage: node kernel/test/bench.mjs [--reps N]
 *        node kernel/test/bench.mjs --case <name> --reps N     (one child)
 */

import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

import {
  DEFAULT_STADIUM,
  applyFacing,
  arcForm,
  makeConditions,
  seatGrid,
  simulate,
} from '../dist/index.js';
import { naiveSimulate } from './naive_kernel.mjs';
import { referenceSimulate } from './reference_kernel.mjs';

const SELF = fileURLToPath(import.meta.url);
const arg = (name, dflt) => {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : dflt;
};
const REPS = Number(arg('--reps', 21));

const performers = applyFacing(arcForm(), 'front');
const grid = seatGrid(DEFAULT_STADIUM);
const receivers = grid.points;
const ON = makeConditions({ farSideReflection: true });
const OFF = makeConditions({ farSideReflection: false });

const CASES = {
  'default (cos 16384, abs 8192, f64), reflection on': () =>
    simulate(performers, receivers, DEFAULT_STADIUM, ON),
  'default (cos 16384, abs 8192, f64), reflection off': () =>
    simulate(performers, receivers, DEFAULT_STADIUM, OFF),
  'cos 4096, abs 8192, f64, reflection on': () =>
    simulate(performers, receivers, DEFAULT_STADIUM, ON, { cosTableSize: 4096 }),
  'cos 4096, abs 8192, f64, reflection off': () =>
    simulate(performers, receivers, DEFAULT_STADIUM, OFF, { cosTableSize: 4096 }),
  'cos 16384, abs 8192, f32, reflection on': () =>
    simulate(performers, receivers, DEFAULT_STADIUM, ON, { tablePrecision: 'f32' }),
  'cos 16384, Math.exp, f64, reflection on': () =>
    simulate(performers, receivers, DEFAULT_STADIUM, ON, { absorptionTableSize: 0 }),
  'cos 65536, abs 8192, f64, reflection on': () =>
    simulate(performers, receivers, DEFAULT_STADIUM, ON, { cosTableSize: 65536 }),
  'naive kernel, reflection on': () => naiveSimulate(performers, receivers, DEFAULT_STADIUM, ON),
  'naive kernel, reflection off': () => naiveSimulate(performers, receivers, DEFAULT_STADIUM, OFF),
  'reference_kernel.mjs (NOT a baseline), reflection on': () =>
    referenceSimulate(performers, receivers, DEFAULT_STADIUM, ON),
};

const SLOW = new Set([
  'naive kernel, reflection on',
  'naive kernel, reflection off',
  'reference_kernel.mjs (NOT a baseline), reflection on',
]);

function median(xs) {
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
}

function runCase(name) {
  const fn = CASES[name];
  const reps = SLOW.has(name) ? Math.max(5, Math.round(REPS / 3)) : REPS;
  for (let i = 0; i < 5; i++) fn(); // let V8 tier up before anything is recorded
  const ts = [];
  for (let i = 0; i < reps; i++) {
    const t0 = performance.now();
    fn();
    ts.push(performance.now() - t0);
  }
  return { name, median: median(ts), min: Math.min(...ts), max: Math.max(...ts), reps };
}

// --- child mode -------------------------------------------------------------

const only = arg('--case', null);
if (only !== null) {
  if (!(only in CASES)) throw new Error(`unknown case ${JSON.stringify(only)}`);
  process.stdout.write(JSON.stringify(runCase(only)));
  process.exit(0);
}

// --- parent mode ------------------------------------------------------------

console.log(
  `set = ${performers.length} performers, ${grid.count} receivers, 8 bands ` +
    `(node ${process.version}); each case in its own process, median of ${REPS}\n`,
);

const results = {};
for (const name of Object.keys(CASES)) {
  const r = spawnSync(process.execPath, [SELF, '--case', name, '--reps', String(REPS)], {
    encoding: 'utf8',
  });
  if (r.status !== 0) {
    console.error(`  ${name}: FAILED\n${r.stderr}`);
    process.exitCode = 1;
    continue;
  }
  const out = JSON.parse(r.stdout);
  results[name] = out.median;
  console.log(
    `  ${name.padEnd(54)} ${out.median.toFixed(2).padStart(8)} ms   ` +
      `[${out.min.toFixed(1)} .. ${out.max.toFixed(1)}] n=${out.reps}`,
  );
}

// Sanity: the naive kernel must compute the same thing, or the ratio is noise.
{
  const a = simulate(performers, receivers, DEFAULT_STADIUM, ON);
  const b = naiveSimulate(performers, receivers, DEFAULT_STADIUM, ON);
  let worst = 0;
  for (let i = 0; i < a.bandSpl.length; i++) {
    worst = Math.max(worst, Math.abs(a.bandSpl[i] - b.bandSpl[i]));
  }
  console.log(`\n  restructured vs naive, same inputs: max ${worst.toExponential(3)} dB`);
}

const defOn = results['default (cos 16384, abs 8192, f64), reflection on'];
const defOff = results['default (cos 16384, abs 8192, f64), reflection off'];
const naiveOn = results['naive kernel, reflection on'];
const naiveOff = results['naive kernel, reflection off'];

console.log('\n-- headline --');
console.log(
  `  shipping default, reflection on : ${defOn.toFixed(2)} ms/set   ` +
    `${(naiveOn / defOn).toFixed(2)}x over naive   ` +
    `100-set show ${((defOn * 100) / 1000).toFixed(2)} s single-threaded`,
);
console.log(
  `  shipping default, reflection off: ${defOff.toFixed(2)} ms/set   ` +
    `${(naiveOff / defOff).toFixed(2)}x over naive`,
);
