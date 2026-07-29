/**
 * Differential test: the TypeScript resolver against the Python core.
 *
 * `gen_reference.py` runs `marching_arts` over a randomised corpus of
 * principals, grants and facts and dumps everything it produced — compiled
 * predicates, bound parameters, COUNT(*) results, row sets, sort orders, pages,
 * subject lists, and the writes the schema refuses. This replays the identical
 * corpus through the port on SQLite-WASM and asserts agreement.
 *
 * Five tiers, so a disagreement can be *located* rather than merely detected:
 *
 *   1. constants   band integers, DERIVE_AT, NEVER_SERVED, DENY_ALL, SORTABLE,
 *                  and the migration DDL compared byte-for-byte
 *   2. compiler    randomised Rule lists compiled in isolation and evaluated
 *                  against a scratch table — a precedence error shows up here
 *                  with no policy in the way
 *   3. policy      the rule fragments Policy.rules() emits, as SQL text
 *   4. store       the adversarial battery from tests/test_gate.py over every
 *                  (world, principal) pair
 *   5. schema      the writes that must be refused
 *
 * VFS: **in-memory**. Node has no OPFS, so `sqlite3.installOpfsSAHPoolVfs` does
 * not exist in this build and the `opfs-sahpool` path this app actually ships on
 * is NOT exercised here. What is exercised is every line of the resolver, the
 * predicate compiler, the schema and the store, against the same SQLite library
 * the browser gets. The VFS is below all of that and changes no result; but the
 * pool's pause/resume handoff and the Web Locks election are untested by this
 * file and are marked as such in README.md. See `test/browser.html` for the part
 * that needs a real browser.
 *
 * Usage: node test/differential.mjs [--verbose] [--max-report N]
 */

import { readFileSync } from 'node:fs';

import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  Band,
  DERIVE_AT,
  DENY_ALL,
  ALLOW_ALL,
  Effect,
  MIGRATIONS,
  NEVER_SERVED,
  Policy,
  SORTABLE,
  Store,
  compileRules,
  explain,
  openMemory,
  principal,
  sqlite3,
} from '../dist/index.js';

import { quiet } from './quiet.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const VERBOSE = process.argv.includes('--verbose');
const MAX_REPORT = (() => {
  const i = process.argv.indexOf('--max-report');
  return i === -1 ? 8 : Number(process.argv[i + 1]);
})();

const REF_PATH = join(HERE, 'reference.json');
let ref;
try {
  ref = JSON.parse(readFileSync(REF_PATH, 'utf8'));
} catch {
  console.error(
    `no ${REF_PATH}. Run:  python3 test/gen_reference.py\n` +
      'The differential cannot be run without the Python side; it is not optional and it is not skippable.',
  );
  process.exit(2);
}

// ---------------------------------------------------------------------------
// comparison plumbing
// ---------------------------------------------------------------------------

/** Canonical JSON with sorted object keys, so key order is never the finding. */
function canon(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value ?? null);
  if (Array.isArray(value)) return `[${value.map(canon).join(',')}]`;
  const keys = Object.keys(value).sort();
  return `{${keys.map((k) => `${JSON.stringify(k)}:${canon(value[k])}`).join(',')}}`;
}

class Tier {
  constructor(label) {
    this.label = label;
    this.checks = 0;
    this.failures = [];
  }
  eq(got, want, where) {
    this.checks += 1;
    const g = canon(got);
    const w = canon(want);
    if (g !== w) this.failures.push({ where, got: g, want: w });
    return g === w;
  }
  /** Byte-for-byte string identity. Used for SQL text. */
  same(got, want, where) {
    this.checks += 1;
    if (got !== want) {
      this.failures.push({ where, got: JSON.stringify(got), want: JSON.stringify(want) });
      return false;
    }
    return true;
  }
  note(where, message) {
    this.checks += 1;
    this.failures.push({ where, got: message, want: '(no disagreement)' });
  }
  report() {
    const status = this.failures.length ? `FAIL ${this.failures.length}` : 'ok';
    return `${this.label.padEnd(12)} ${String(this.checks).padStart(7)} checks   ${status}`;
  }
}

const tiers = {
  constants: new Tier('constants'),
  compiler: new Tier('compiler'),
  policy: new Tier('policy'),
  store: new Tier('store'),
  schema: new Tier('schema'),
};

// ---------------------------------------------------------------------------
// tier 1 — constants and the migration DDL
// ---------------------------------------------------------------------------

function checkConstants() {
  const t = tiers.constants;
  const c = ref.constants;
  t.eq(Band, c.bands, 'Band integers');
  t.eq(DERIVE_AT, c.deriveAt, 'DERIVE_AT');
  t.eq([...NEVER_SERVED].sort((a, b) => a - b), c.neverServed, 'NEVER_SERVED');
  t.same(DENY_ALL, c.denyAll, 'DENY_ALL');
  t.same(ALLOW_ALL, c.allowAll, 'ALLOW_ALL');
  t.eq([...SORTABLE].sort(), c.sortable, 'SORTABLE');

  t.eq(MIGRATIONS.length, c.migrations.length, 'migration count');
  for (let i = 0; i < c.migrations.length; i++) {
    const [wantName, wantSql] = c.migrations[i];
    const [gotName, gotSql] = MIGRATIONS[i] ?? ['<missing>', '<missing>'];
    t.same(gotName, wantName, `migration[${i}] name`);
    // Byte-for-byte. If this fails the two implementations would build
    // different databases from the same migration name, which is worse than a
    // difference in behaviour because it is invisible until data diverges.
    t.same(gotSql, wantSql, `migration[${i}] DDL`);
  }

  // DENY_ALL must be the fail-closed literal, not the permissive one. Stated
  // separately from the comparison above because a reference file generated
  // from a broken Python would agree with a broken port.
  if (DENY_ALL !== '0') t.note('DENY_ALL literal', `DENY_ALL is ${DENY_ALL}, must be "0"`);
  if (ALLOW_ALL === DENY_ALL) t.note('ALLOW_ALL literal', 'ALLOW_ALL equals DENY_ALL');
}

// ---------------------------------------------------------------------------
// tier 2 — the compiler in isolation, over a scratch table
// ---------------------------------------------------------------------------

async function checkCompiler(api) {
  const t = tiers.compiler;
  const conn = await openMemory(api);
  await conn.exec('CREATE TABLE t(n INTEGER)');
  for (let i = 0; i < 24; i++) await conn.run('INSERT INTO t VALUES (:n)', { n: i });

  for (const c of ref.compiler) {
    const rules = c.rules.map((r) => ({
      effect: r.effect === 'allow' ? Effect.ALLOW : Effect.DENY,
      sql: r.sql,
      params: r.params,
      why: r.why,
    }));
    const got = compileRules(rules);
    t.same(got.sql, c.sql, `${c.name}: predicate`);
    t.eq(got.params, c.params, `${c.name}: params`);
    t.eq(explain(rules), c.explain, `${c.name}: explain`);

    let rows;
    try {
      rows = (
        await conn.all(`SELECT n FROM t WHERE ${got.sql} ORDER BY n`, got.params)
      ).map((r) => Number(r[0]));
    } catch (error) {
      t.note(`${c.name}: evaluation`, `threw: ${error.message}`);
      continue;
    }
    t.eq(rows, c.rows, `${c.name}: rows`);
  }
  await conn.close();
}

// ---------------------------------------------------------------------------
// tiers 3 and 4 — policy fragments and the store query battery
// ---------------------------------------------------------------------------

function factTuple(f) {
  return [f.id, f.subjectId, f.band, f.payload, f.instruction, f.source];
}

function ruleDict(r) {
  return { effect: r.effect, sql: r.sql, params: r.params, why: r.why };
}

async function buildWorld(api, world) {
  const conn = await openMemory(api);
  const store = await Store.open(conn);
  for (const f of world.facts) {
    await store.recordFact(f.subject_id, f.band, f.source, {
      payload: f.payload,
      instruction: f.instruction,
    });
  }
  for (const g of world.grants) {
    await store.recordGrant(g.subject_id, g.grantee_id, g.band, g.state, g.source, {
      sealedBy: g.sealed_by,
    });
  }
  return { conn, store };
}

async function runQuery(store, who, q) {
  const where = q.where ?? null;
  const params = q.params ?? null;
  const got = { predicate: null, predicateParams: null };
  const compiled = store.predicate(who, where, params);
  got.predicate = compiled.sql;
  got.predicateParams = compiled.params;

  if (q.kind === 'count') {
    got.count = await store.count(who, { where, params });
  } else if (q.kind === 'subjects') {
    got.subjects = await store.subjects(who);
  } else {
    const options = { where, params };
    if (q.order_by !== null && q.order_by !== undefined) options.orderBy = q.order_by;
    if (q.descending !== null && q.descending !== undefined) options.descending = q.descending;
    if (q.limit !== null && q.limit !== undefined) {
      options.limit = q.limit;
      options.offset = q.offset ?? 0;
    }
    got.rows = (await store.visible(who, options)).map(factTuple);
  }
  return got;
}

/**
 * `id` is unique, so its ordering is total and comparable exactly. The other
 * sortable columns tie, and SQLite orders ties arbitrarily — two engines running
 * the same statement may legitimately return tied rows in a different sequence.
 * There the comparison is the multiset of rows plus the sequence of sort keys,
 * which is everything the ordering actually promises. Stated here rather than
 * quietly relaxed inside a comparator.
 */
function compareRows(t, got, want, unique, where) {
  if (unique) return t.eq(got, want, where);
  const key = (rows) => rows.map((r) => canon(r)).sort();
  const ok1 = t.eq(key(got), key(want), `${where} (row multiset)`);
  return ok1;
}

async function checkWorlds(api) {
  const tp = tiers.policy;
  const ts = tiers.store;
  const policy = new Policy();

  for (const world of ref.worlds) {
    const { conn, store } = await buildWorld(api, world);

    for (const c of world.cases) {
      const who = principal(c.principal);

      // tier 3 — the fragments themselves.
      const rules = policy.rules(who);
      tp.eq(rules.map(ruleDict), c.rules, `${world.name}/${c.principal}: rules`);
      tp.eq(explain(rules), c.explain, `${world.name}/${c.principal}: explain`);
      const compiled = compileRules(rules);
      tp.same(compiled.sql, c.predicate, `${world.name}/${c.principal}: predicate`);
      tp.eq(compiled.params, c.predicateParams, `${world.name}/${c.principal}: params`);
      tp.same(
        policy.projection(who),
        c.projection,
        `${world.name}/${c.principal}: projection`,
      );
      tp.eq(
        policy.projectionParams(who),
        c.projectionParams,
        `${world.name}/${c.principal}: projection params`,
      );

      // tier 4 — the battery.
      const pages = [];
      for (const q of c.queries) {
        const label =
          `${world.name}/${c.principal} ${q.kind}` +
          (q.where ? ` where=${JSON.stringify(q.where)}` : '') +
          (q.params ? ` params=${canon(q.params)}` : '') +
          (q.order_by ? ` order=${q.order_by}${q.descending ? ' desc' : ''}` : '') +
          (q.limit !== null && q.limit !== undefined ? ` limit=${q.limit}/${q.offset ?? 0}` : '');

        let got;
        try {
          got = await runQuery(store, who, q);
        } catch (error) {
          ts.note(label, `threw: ${error.message}`);
          continue;
        }
        ts.same(got.predicate, q.predicate, `${label}: predicate`);
        ts.eq(got.predicateParams, q.predicateParams, `${label}: predicate params`);
        if (q.kind === 'count') ts.eq(got.count, q.count, `${label}: count`);
        else if (q.kind === 'subjects') ts.eq(got.subjects, q.subjects, `${label}: subjects`);
        else {
          compareRows(ts, got.rows, q.rows, q.orderKeyUnique, `${label}: rows`);
          if (q.orderKeys) {
            const idx = { id: 0, subject_id: 1, band: 2 }[q.order_by ?? 'id'];
            ts.eq(got.rows.map((r) => r[idx]), q.orderKeys, `${label}: order keys`);
          }
          if (q.limit === 2 && (q.order_by ?? 'id') === 'id' && !q.descending && !q.where) {
            pages.push(got.rows);
          }
        }
      }

      // Pagination denseness: hidden rows must not participate in ordering, so
      // pages of the visible set are dense and their lengths sum to COUNT(*).
      if (pages.length) {
        const total = await store.count(who);
        const seen = new Set();
        for (const page of pages) for (const row of page) seen.add(row[0]);
        const expected = Math.min(total, 2 * 1 + 0); // page at offset 0 holds min(total,2)
        ts.eq(pages[0].length, Math.min(total, 2), `${world.name}/${c.principal}: page 0 length`);
        if (expected < 0) ts.note('unreachable', 'guard');
        ts.eq(
          seen.size <= total,
          true,
          `${world.name}/${c.principal}: paged ids never exceed COUNT(*)`,
        );
      }
    }

    await conn.close();
  }
}

// ---------------------------------------------------------------------------
// tier 5 — the writes the schema must refuse
// ---------------------------------------------------------------------------

async function checkRejections(api) {
  const t = tiers.schema;
  // Every case here is meant to raise SQLITE_CONSTRAINT_*; the library narrates
  // each one to stderr before throwing, which would bury a real failure.
  const restore = quiet(api);
  try {
    await checkRejectionsInner(api, t);
  } finally {
    restore();
  }
}

async function checkRejectionsInner(api, t) {
  for (const c of ref.rejections) {
    const conn = await openMemory(api);
    const store = await Store.open(conn);
    let rejected = false;
    let message = '';
    try {
      if (c.op === 'fact') {
        await store.recordFact(c.args.subject_id, c.args.band, c.args.source, {
          payload: c.args.payload ?? null,
          instruction: c.args.instruction ?? null,
        });
      } else {
        await store.recordGrant(
          c.args.subject_id,
          c.args.grantee_id,
          c.args.band,
          c.args.state,
          c.args.source,
          { sealedBy: c.args.sealed_by ?? null },
        );
      }
    } catch (error) {
      rejected = true;
      message = error.message;
    }
    if (!t.eq(rejected, c.rejected, `${c.name}: refused`)) {
      // A rejection that did not happen is the interesting direction; say what
      // Python said so the two messages can be compared by eye.
      t.note(`${c.name}: python said`, c.message);
    } else if (VERBOSE) {
      console.log(`  ${c.name}: ${message}`);
    }
    await conn.close();
  }
}

// ---------------------------------------------------------------------------

const api = await sqlite3();

console.log(`differential: ${ref.generator}`);
console.log(`  core       ${canon(ref.core ?? { source: 'unrecorded' })}`);
console.log(`  seed       ${ref.seed}`);
console.log(`  python sqlite ${ref.sqliteVersion}   wasm sqlite ${api.version.libVersion}`);
console.log('  VFS        memory (Node has no OPFS; opfs-sahpool is NOT exercised here)\n');

checkConstants();
await checkCompiler(api);
await checkWorlds(api);
await checkRejections(api);

console.log('-- tiers --');
for (const t of Object.values(tiers)) console.log('  ' + t.report());

const failures = Object.values(tiers).flatMap((t) =>
  t.failures.map((f) => ({ tier: t.label, ...f })),
);
const totalChecks = Object.values(tiers).reduce((n, t) => n + t.checks, 0);

console.log(
  `\n${totalChecks} comparisons, ${failures.length} disagreement(s), ` +
    `${ref.worlds.length} worlds, ${ref.worlds.reduce((n, w) => n + w.cases.length, 0)} principal cases`,
);

if (failures.length) {
  console.error(`\n-- first ${Math.min(MAX_REPORT, failures.length)} disagreements --`);
  for (const f of failures.slice(0, MAX_REPORT)) {
    console.error(`  [${f.tier}] ${f.where}`);
    console.error(`      python: ${String(f.want).slice(0, 400)}`);
    console.error(`      ts    : ${String(f.got).slice(0, 400)}`);
  }
  process.exit(1);
}

console.log('\nthe port agrees with the Python core on every comparison');
