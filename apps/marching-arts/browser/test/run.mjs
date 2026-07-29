/**
 * Run every check in order. `npm test`.
 *
 * Stages:
 *
 *   gate           the P1 gate re-expressed against the port. No Python needed.
 *   owner protocol the MessagePort wire, over a real MessageChannel.
 *   differential   the port against the Python core, over a randomised corpus.
 *
 * The differential is **not skippable**. `gen_reference.py` is stdlib-only, so
 * any Python 3 that can run the app's own test suite can produce the reference;
 * if it is missing this runner generates it, and if that fails the run fails.
 * The sibling harness in `apps/field-acoustics/kernel` reports its differential
 * as skipped when the reference is absent, because that one needs numpy and
 * scipy and a skip there is honest. Here a skip would mean the browser resolver
 * shipped with nothing holding it to the semantics it is a copy of.
 *
 * Usage: node test/run.mjs
 */

import { spawnSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));

function python() {
  for (const exe of ['python3', 'python']) {
    const r = spawnSync(exe, ['--version'], { encoding: 'utf8' });
    if (r.status === 0) return exe;
  }
  return null;
}

// ALWAYS regenerate; never reuse what is on disk. Generating only when the file
// was absent made this a gate that stops being one the moment the core moves: a
// reference written before a policy change reports a clean pass against
// semantics the port no longer copies. It did exactly that here — a stale
// reference reported 27,528 comparisons and 0 disagreements while the port was
// missing the entire guardian-consent clause. Regeneration is seconds of
// stdlib Python, and a green run against yesterday's core is worse than no run
// because it is indistinguishable from a real one.
{
  const exe = python();
  if (!exe) {
    console.error(
      'FATAL: no python3 to generate reference.json.\n' +
        '  The differential is the only thing holding this port to the Python core.\n' +
        '  Refusing to report a pass without it.',
    );
    process.exit(2);
  }
  console.log('=== generating reference.json from the working tree ===');
  const r = spawnSync(exe, [join(HERE, 'gen_reference.py')], { stdio: 'inherit' });
  if (r.status !== 0) {
    console.error('FATAL: gen_reference.py failed; the differential cannot run.');
    process.exit(2);
  }
}

const stages = [
  ['gate', 'gate.mjs'],
  ['owner protocol', 'owner.mjs'],
  ['differential vs Python', 'differential.mjs'],
];

let failed = 0;
for (const [name, script] of stages) {
  console.log(`\n=== ${name} ===`);
  const r = spawnSync(process.execPath, [join(HERE, script)], { stdio: 'inherit' });
  if (r.status !== 0) failed += 1;
}

console.log(
  '\nnot covered by this runner: the opfs-sahpool VFS, the Web Locks election, and\n' +
    'the pauseVfs()/unpauseVfs() handoff. Node has no OPFS and no SharedWorker.\n' +
    'Open test/browser.html in a real browser for those; see README.md.',
);

if (failed) {
  console.error(`\n${failed} stage(s) failed`);
  process.exit(1);
}
console.log('\nall stages passed');
