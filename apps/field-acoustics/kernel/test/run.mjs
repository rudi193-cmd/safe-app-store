/**
 * Run every check in order. `npm test`.
 *
 * The differential test needs `kernel/test/reference.json`, which is produced by
 * `gen_reference.py` and requires numpy + scipy + the `dcisim` package on the
 * path. If it is missing, that stage is reported as skipped rather than failed —
 * the invariants and the worker protocol do not need Python.
 */

import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));

const stages = [
  ['invariants', join(HERE, 'invariants.mjs')],
  ['worker protocol', join(HERE, 'worker.mjs')],
  ['differential vs Python', join(HERE, 'differential.mjs')],
];

let failed = 0;
for (const [name, script] of stages) {
  if (script.endsWith('differential.mjs') && !existsSync(join(HERE, 'reference.json'))) {
    console.log(`\n=== ${name}: SKIPPED (run \`python3 kernel/test/gen_reference.py\` first) ===`);
    continue;
  }
  console.log(`\n=== ${name} ===`);
  const r = spawnSync(process.execPath, [script], { stdio: 'inherit' });
  if (r.status !== 0) failed += 1;
}

if (failed) {
  console.error(`\n${failed} stage(s) failed`);
  process.exit(1);
}
console.log('\nall stages passed');
