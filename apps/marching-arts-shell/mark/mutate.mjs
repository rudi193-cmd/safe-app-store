/*
 * Copyright 2026 The dcisim Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * A gate that cannot fail is not a gate.
 *
 *   node mark/mutate.mjs        # or: npm run mutate:named
 *
 * This breaks the mark on purpose, one defect at a time, and asserts that the
 * suite catches each one **by name** — not that something went red, but that
 * the specific gate written for that defect is the gate that fired.
 *
 * It exists alongside Stryker rather than instead of it, because the two
 * measure different things and neither subsumes the other:
 *
 *   Stryker  generates ~900 mutants nobody thought to write. That breadth is
 *            how the gutted-withinSweep hole was found at all. But `node --test`
 *            can only be driven through its TAP runner, which reports one test
 *            per *file*, so every mutant comes back killedBy ["0"]. It can tell
 *            you a gate is missing. It cannot tell you which gate caught what.
 *
 *   this     a dozen defects that matter, each naming the gate that must catch
 *            it. No breadth at all. Full attribution, and it fails if the
 *            *wrong* gate catches a defect — which is a real outcome: an
 *            earlier version of the endpoint mutation was caught by a different
 *            test while the one under examination stayed green.
 *
 * The design is borrowed from apps/marching-arts/browser/test/mutate.mjs in
 * safe-app-store, which had all of this before this repo did — including the
 * restore verification and the green-after-restore control. One departure: that
 * harness mutates in place and hashes to prove the restore took. This one never
 * writes to the working tree at all. It copies into a sandbox, because the
 * throwaway harness this replaces used `git checkout -- .` to restore and
 * destroyed uncommitted work doing it.
 */

import { execFileSync } from 'node:child_process';
import { cpSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const app = resolve(here, '..');

/**
 * Each defect names the gate that must catch it. `expect` is matched against
 * the names of the tests that failed; if it is absent from them the run fails,
 * even when other tests went red.
 */
const DEFECTS = [
  {
    // Refused, not caught: with r 1% wrong, choosePrecision cannot recover any
    // arc centre at any precision, so construct() throws before an invariant
    // runs. A stronger outcome than a gate firing, and the first expectation
    // written here named the gate instead — which is what this harness is for.
    what: 'wavefront radius is no longer the peer spacing',
    file: 'mark/construct.mjs',
    from: '      r: d.side,',
    to: '      r: d.side * 1.01,',
    expect: 'the canonical spec is constructible',
  },
  {
    what: 'a source is moved off the basis circle',
    file: 'mark/construct.mjs',
    from: 'at: polar(O, R, phase + (360 / N) * index),',
    to: 'at: polar(O, index === 0 ? R + 0.5 : R, phase + (360 / N) * index),',
    expect: 'the canonical spec is constructible',
  },
  {
    what: 'an emitted endpoint drifts off its own arc',
    file: 'mark/construct.mjs',
    from: '`M${n(arc.from.x, decimals)} ${n(arc.from.y, decimals)}`',
    to: '`M${n(arc.from.x, decimals)} ${n(arc.from.y + 0.4, decimals)}`',
    expect: 'the canonical spec is constructible',
  },
  {
    what: 'the crossing detector is gutted',
    file: 'mark/invariants.mjs',
    from: '  const onSpan = swept > 0 ? delta >= 0 && delta <= swept : delta <= 0 && delta >= swept;\n  if (onSpan) return Math.abs(dist(point, arc.centre) - arc.r);\n  return Math.min(dist(point, arc.from), dist(point, arc.to));',
    to: '  return Infinity;',
    expect: '{"N":4,"span":1} trips: wavefronts stay a stroke apart from each other',
  },
  {
    what: 'withinSweep is emptied — the hole Stryker found',
    file: 'mark/invariants.mjs',
    from: '  const delta = fold(bearing(arc.centre, point) - arc.startBearing);\n  const swept = arc.sweptDegrees;\n  return swept > 0\n    ? delta >= -tolerance && delta <= swept + tolerance\n    : delta <= tolerance && delta >= swept - tolerance;',
    to: '  return false;',
    expect: '{"N":4,"span":1} trips: no wavefront crosses another',
  },
  {
    what: 'the legibility floor always passes',
    file: 'mark/invariants.mjs',
    from: '    arcLength >= d.stroke,',
    to: '    true,',
    expect: '{"N":9,"span":4} trips: each wavefront is longer than the stroke is thick',
  },
  {
    what: 'the basis-circle tolerance is loosened a millionfold',
    file: 'mark/invariants.mjs',
    from: "add('sources lie on the basis circle', offCircle < 1e-12,",
    to: "add('sources lie on the basis circle', offCircle < 1e-6,",
    expect: 'sources lie on the basis circle: fails 1e-11 past tolerance',
  },
  {
    what: 'the constant-width gate always passes',
    file: 'mark/invariants.mjs',
    from: "add('the closed curve has the same width in every direction', worst < 1e-9,",
    to: "add('the closed curve has the same width in every direction', true,",
    expect: 'the closed curve has the same width in every direction: fails 1e-8 past tolerance',
  },
  {
    what: 'a refusal branch is deleted',
    file: 'mark/construct.mjs',
    from: '  if (2 * span >= N) {',
    to: '  if (false) {',
    expect: '{"N":4,"span":2} is refused',
  },
  {
    what: 'the grid stops being derived',
    file: 'mark/construct.mjs',
    from: '    box: 2 * (R + source + clearance),',
    to: '    box: 60,',
    expect: 'the grid is no larger than the mark needs',
  },
  {
    what: 'the PNG encoder settings are dropped',
    file: 'mark/png.mjs',
    from: "const ENCODE = { colorType: 2, filterType: 0, deflateLevel: 9, deflateStrategy: 0 };",
    to: 'const ENCODE = {};',
    expect: 'the committed PNG is encoded the way this repo encodes PNGs',
  },
  {
    what: 'the committed icon is hand-edited',
    file: 'web/assets/icon.svg',
    from: 'cy="8"',
    to: 'cy="9"',
    expect: 'the committed files are what the generator produces',
  },
  {
    what: 'the accent changes in tokens.css only',
    file: 'web/styles/tokens.css',
    from: '--accent: #8a5a10;',
    to: '--accent: #8a5b10;',
    expect: 'the icon states the accent from tokens.css and nothing else',
  },
];

/** Every top-level test that failed, by name. */
function failingTests(root) {
  try {
    execFileSync('node', ['--test', join(root, 'test/construct.test.mjs'), join(root, 'test/shell.test.mjs')], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    return [];
  } catch (error) {
    const out = `${error.stdout ?? ''}${error.stderr ?? ''}`;
    const named = [...out.matchAll(/^not ok \d+ - (.+?)\s*$/gm)].map((m) => m[1]);
    return named.length > 0 ? named : ['(suite did not run)'];
  }
}

function sandbox() {
  const dir = mkdtempSync(join(tmpdir(), 'dcisim-mutate-'));
  for (const part of ['mark', 'test', 'web']) {
    cpSync(join(app, part), join(dir, part), { recursive: true });
  }
  // The shell gates read the manifest, so a sandbox without it is not the app.
  for (const file of ['safe-app-manifest.json', 'package.json']) {
    cpSync(join(app, file), join(dir, file));
  }
  // Symlinked, not copied: node resolves upward from the module, and copying
  // node_modules per defect would cost more than the whole run.
  symlinkSync(resolve(app, 'node_modules'), join(dir, 'node_modules'), 'dir');
  return dir;
}

const dir = sandbox();
let missed = 0;
let misattributed = 0;

try {
  const baseline = failingTests(dir);
  if (baseline.length > 0) {
    process.stdout.write(`baseline is not green: ${baseline.join(', ')}\n`);
    process.exit(1);
  }
  process.stdout.write(`baseline green, ${DEFECTS.length} defects\n\n`);

  for (const defect of DEFECTS) {
    const path = join(dir, defect.file);
    const original = readFileSync(path, 'utf8');
    if (!original.includes(defect.from)) {
      process.stdout.write(`STALE    ${defect.what}\n         pattern not found in ${defect.file}\n`);
      missed += 1;
      continue;
    }
    writeFileSync(path, original.replace(defect.from, defect.to));

    const failed = failingTests(dir);
    const hit = failed.includes(defect.expect);
    const verdict = failed.length === 0 ? 'MISSED  ' : hit ? 'caught  ' : 'WRONG   ';
    if (failed.length === 0) missed += 1;
    else if (!hit) misattributed += 1;

    process.stdout.write(`${verdict} ${defect.what}\n`);
    if (failed.length === 0) {
      process.stdout.write(`         nothing failed; expected: ${defect.expect}\n`);
    } else if (!hit) {
      process.stdout.write(`         expected: ${defect.expect}\n`);
      process.stdout.write(`         actually: ${failed.join('; ')}\n`);
    } else if (failed.length > 1) {
      // Collateral is expected and mostly uninteresting — a defect in the
      // construction fails everything downstream of it. Count it, show a few.
      const others = failed.filter((f) => f !== defect.expect);
      const shown = others.slice(0, 3).join('; ');
      const rest = others.length > 3 ? ` (+${others.length - 3} more)` : '';
      process.stdout.write(`         also ${others.length}: ${shown}${rest}\n`);
    }

    // Restore, and prove the restore took — a harness that fails on everything
    // is no more informative than one that fails on nothing.
    writeFileSync(path, original);
    if (readFileSync(path, 'utf8') !== original) {
      process.stdout.write(`FATAL: ${defect.file} was not restored\n`);
      process.exit(1);
    }
  }

  const after = failingTests(dir);
  if (after.length > 0) {
    process.stdout.write(`\nFATAL: suite is not green after restoring: ${after.join(', ')}\n`);
    process.exit(1);
  }
  process.stdout.write('\ngreen again after every restore\n');
} finally {
  rmSync(dir, { recursive: true, force: true });
}

process.stdout.write(`${DEFECTS.length - missed - misattributed} caught by the named gate, ` +
  `${misattributed} caught by the wrong one, ${missed} missed\n`);
process.exit(missed + misattributed > 0 ? 1 : 0);
