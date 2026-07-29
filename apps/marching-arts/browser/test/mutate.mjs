/**
 * A gate that cannot fail is not a gate.
 *
 * This breaks the port on purpose, one bug at a time, and asserts that the suite
 * *catches* each one — then restores the build and asserts the suite goes green
 * again, because a harness that fails on everything is no more informative than
 * one that fails on nothing.
 *
 * Each mutation is run past **both** checks, and the report says which one
 * caught it. That distinction is the interesting output:
 *
 *   deny-precedence   drop the parentheses around the joined denies, so only the
 *                     first deny binds. rules.py names this as "the single most
 *                     likely way to rebuild the leak". It is silent: the SQL
 *                     stays valid and nothing raises.
 *   fail-open         compile an empty allow set to `1` instead of `0`, so an
 *                     unrecognised principal sees every row.
 *   param-collision   drop the per-rule parameter scoping, so two rules using
 *                     `viewer` overwrite each other's binding.
 *   guardian-clause   delete the guardian-expiry clause from the grant lookup —
 *                     i.e. put policy.ts back the way P1 left it, so a guardian
 *                     keeps an adult member's record for life. Worth reading
 *                     alongside count-in-js: the differential reports ~14.6k
 *                     disagreements, and *every one of them is SQL text or a
 *                     bound parameter*. Not one is a count, a row or a subject
 *                     list, because the randomised corpus has no `people` rows
 *                     and no guardian-derived grants, so the mutation changes no
 *                     answer in it. The differential is checking spelling here,
 *                     which is a real check and is what caught the drift this
 *                     port was behind on — but the tests that say what the
 *                     clause is *for*, in answers, are the guardian block in
 *                     gate.mjs.
 *   count-in-js       compute count() as the length of a fetched array. The
 *                     *number is still correct*, so the differential cannot see
 *                     it — every comparison still agrees. What is wrong is that
 *                     the hidden rows were read into the tab to produce it, and
 *                     only the traced test in gate.mjs notices. This mutation is
 *                     in the list specifically to demonstrate that the
 *                     differential alone is not sufficient for the P1 gate.
 *
 * Usage: node test/mutate.mjs [--verbose]
 */

import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const DIST = join(HERE, '..', 'dist');
const VERBOSE = process.argv.includes('--verbose');

if (!existsSync(join(DIST, 'rules.js'))) {
  console.error('no dist/. Run:  npm run build');
  process.exit(2);
}
if (!existsSync(join(HERE, 'reference.json'))) {
  console.error('no test/reference.json. Run:  python3 test/gen_reference.py');
  process.exit(2);
}

const sha = (s) => createHash('sha256').update(s).digest('hex').slice(0, 12);

const MUTATIONS = [
  {
    name: 'deny-precedence',
    file: 'rules.js',
    from: "predicate = `${predicate} AND NOT (${denies.join(' OR ')})`;",
    to: "predicate = `${predicate} AND NOT ${denies.join(' OR ')}`;",
    why: 'denies negate only the first term instead of the union',
  },
  {
    name: 'fail-open',
    file: 'rules.js',
    from: 'if (allows.length === 0)\n        return { sql: DENY_ALL, params: {} };',
    to: 'if (allows.length === 0)\n        return { sql: ALLOW_ALL, params: {} };',
    why: 'an unrecognised principal sees every row instead of none',
  },
  {
    name: 'param-collision',
    file: 'rules.js',
    from: 'scoped[`r${index}_${key}`] = r.params[key];\n        placeholders[key] = `:r${index}_${key}`;',
    to: 'scoped[`r_${key}`] = r.params[key];\n        placeholders[key] = `:r_${key}`;',
    why: 'two rules using the same parameter name overwrite each other',
  },
  {
    name: 'guardian-clause',
    file: 'policy.js',
    from:
      "'   AND (g.granted_via = {member} OR ' +\n" +
      "                this.stillAMinor('g.subject_id') +\n" +
      "                '))', { viewer: p.personId, sealed: GrantState.SEALED, member: GrantVia.MEMBER }",
    to: "')', { viewer: p.personId, sealed: GrantState.SEALED }",
    why: 'guardian authority never expires — the P1 rule, i.e. the port left behind',
  },
  {
    name: 'count-in-js',
    file: 'store.js',
    from:
      'const row = await this.connection.get(`SELECT COUNT(*) FROM facts WHERE ${predicate}`, params);\n' +
      '        return Number(row ? row[0] : 0);',
    to:
      'const rows = await this.connection.all(`SELECT facts.id, facts.payload FROM facts WHERE ${predicate}`, params);\n' +
      '        return rows.length;',
    why: 'the count is a length over fetched rows, so the rows were fetched',
  },
];

function run(script) {
  const r = spawnSync(process.execPath, [join(HERE, script)], { encoding: 'utf8' });
  const stdout = r.stdout || '';
  const summary =
    stdout.split('\n').find((l) => l.includes('disagreement(s)') || l.includes('gate tests')) ?? '';
  return { status: r.status, summary: summary.trim(), stdout, stderr: r.stderr || '' };
}

function runBoth() {
  const differential = run('differential.mjs');
  const gate = run('gate.mjs');
  return {
    differential,
    gate,
    green: differential.status === 0 && gate.status === 0,
  };
}

// ---------------------------------------------------------------------------

console.log('mutation test: break the port on purpose, confirm the gate notices\n');

const baseline = runBoth();
console.log(`baseline  differential exit ${baseline.differential.status}  ${baseline.differential.summary}`);
console.log(`          gate         exit ${baseline.gate.status}  ${baseline.gate.summary}`);
if (!baseline.green) {
  console.error('\nthe suite is already failing; fix that before mutating.');
  process.exit(2);
}

const results = [];
for (const m of MUTATIONS) {
  const path = join(DIST, m.file);
  const original = readFileSync(path, 'utf8');
  const originalHash = sha(original);

  if (!original.includes(m.from)) {
    console.error(
      `\n[${m.name}] SKIPPED — the text this mutation edits is not in dist/${m.file}.\n` +
        '  The build changed shape and this mutation no longer applies. A skipped\n' +
        '  mutation is a hole in the gate, not a pass; fix the pattern.',
    );
    results.push({ ...m, caughtBy: null });
    continue;
  }

  writeFileSync(path, original.replace(m.from, m.to));
  let outcome;
  try {
    outcome = runBoth();
  } finally {
    writeFileSync(path, original);
    const restoredHash = sha(readFileSync(path, 'utf8'));
    if (restoredHash !== originalHash) {
      console.error(`\nFATAL: dist/${m.file} was not restored (${restoredHash} != ${originalHash})`);
      process.exit(3);
    }
  }

  const by = [];
  if (outcome.differential.status !== 0) by.push('differential');
  if (outcome.gate.status !== 0) by.push('gate');
  results.push({ ...m, caughtBy: by });

  console.log(`\n[${m.name}] ${m.why}`);
  console.log(
    `  differential exit ${outcome.differential.status}  ${outcome.differential.summary}`,
  );
  console.log(`  gate         exit ${outcome.gate.status}  ${outcome.gate.summary}`);
  console.log(`  caught by: ${by.length ? by.join(' + ') : 'NOTHING'}`);
  if (VERBOSE && by.includes('gate')) {
    const lines = outcome.gate.stdout.split('\n').filter((l) => l.startsWith('FAIL'));
    for (const l of lines.slice(0, 4)) console.log('    ' + l);
  }
}

const after = runBoth();
console.log(
  `\nrestored  differential exit ${after.differential.status}  gate exit ${after.gate.status}`,
);

console.log('\n-- summary --');
for (const r of results) {
  const verdict =
    r.caughtBy === null
      ? 'SKIPPED (pattern missing)'
      : r.caughtBy.length
        ? `caught by ${r.caughtBy.join(' + ')}`
        : 'MISSED BY EVERYTHING';
  console.log(`  ${r.name.padEnd(18)} ${verdict}`);
}

const missed = results.filter((r) => r.caughtBy === null || r.caughtBy.length === 0);
if (missed.length || !after.green) {
  console.error(
    `\n${missed.length} mutation(s) not caught; restored build ${after.green ? 'green' : 'RED'}`,
  );
  process.exit(1);
}
console.log('\nevery mutation was caught, and the restored build is green again');
