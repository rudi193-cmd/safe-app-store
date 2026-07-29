/**
 * P1's gate, in the browser: hidden rows must not leak through a COUNT, a
 * filter, a sort order or an empty state.
 *
 * Every test here is one of `apps/marching-arts/tests/test_gate.py` or
 * `test_rules.py`, re-expressed against the port. They are duplicated rather
 * than replaced by the differential on purpose: the differential proves the two
 * implementations *agree*, and two implementations can agree while both being
 * wrong. These say what correct is, independently.
 *
 * Two of them are things the differential structurally cannot check:
 *
 *   `count is a COUNT(*)`   traced, not asserted. Every statement the store
 *                           issues is recorded, and count() must issue exactly
 *                           one that touches `facts`, and that one must be a
 *                           COUNT(*) carrying the authorization predicate. A
 *                           count computed over fetched rows returns the same
 *                           *number*, so no numeric comparison can see it — but
 *                           the hidden rows were read into the tab to get there.
 *   `no row escapes`        no statement the store issues may select payload
 *                           without a WHERE. Checked over the whole battery.
 *
 * Needs no Python. Usage: node test/gate.mjs [--verbose]
 */

import {
  Band,
  Effect,
  DENY_ALL,
  GrantState,
  Policy,
  Store,
  compileRules,
  explain,
  openMemory,
  principal,
  rule,
  sqlite3,
} from '../dist/index.js';

import { quiet } from './quiet.mjs';

const VERBOSE = process.argv.includes('--verbose');
const api = await sqlite3();
// Constraint violations are provoked on purpose below; see quiet.mjs.
quiet(api);

let passed = 0;
const failures = [];
const pending = [];

function test(name, fn) {
  pending.push([name, fn]);
}

function assert(condition, message) {
  if (!condition) throw new Error(message ?? 'assertion failed');
}

function eq(got, want, message) {
  const g = JSON.stringify(got);
  const w = JSON.stringify(want);
  if (g !== w) throw new Error(`${message ?? 'not equal'}\n    got  ${g}\n    want ${w}`);
}

async function rejects(fn, message) {
  try {
    await fn();
  } catch {
    return;
  }
  throw new Error(message ?? 'expected a rejection, got none');
}

/** A Connection that records every statement, so `count` can be traced. */
class TracingConnection {
  constructor(inner) {
    this.inner = inner;
    this.statements = [];
    this.recording = false;
  }
  record(sql) {
    if (this.recording) this.statements.push(sql);
  }
  async all(sql, params) {
    this.record(sql);
    return this.inner.all(sql, params);
  }
  async get(sql, params) {
    this.record(sql);
    return this.inner.get(sql, params);
  }
  async run(sql, params) {
    this.record(sql);
    return this.inner.run(sql, params);
  }
  exec(sql) {
    this.record(sql);
    return this.inner.exec(sql);
  }
  begin() {
    return this.inner.begin();
  }
  commit() {
    return this.inner.commit();
  }
  rollback() {
    return this.inner.rollback();
  }
  close() {
    return this.inner.close();
  }
}

const LEADER = principal('leader');
const STRANGER = principal('stranger');

/** Two members. The leader holds a sealed craft-band grant on one of them. */
async function fixture() {
  const conn = new TracingConnection(await openMemory(api));
  const store = await Store.open(conn);
  for (let i = 0; i < 3; i++) {
    await store.recordFact('visible-member', Band.CRAFT, 'rehearsal log', {
      payload: `visible ${i}`,
    });
  }
  for (let i = 0; i < 7; i++) {
    await store.recordFact('hidden-member', Band.CRAFT, 'rehearsal log', {
      payload: `hidden ${i}`,
    });
  }
  await store.recordGrant('visible-member', 'leader', Band.CRAFT, GrantState.SEALED, 'consent form', {
    sealedBy: 'guardian',
  });
  return { conn, store };
}

/** Compile a predicate and evaluate it against a scratch table of integers. */
async function scratchRows(sql, params) {
  const conn = await openMemory(api);
  await conn.exec('CREATE TABLE t(n INTEGER)');
  for (let i = 0; i < 10; i++) await conn.run('INSERT INTO t VALUES (:n)', { n: i });
  const rows = (await conn.all(`SELECT n FROM t WHERE ${sql} ORDER BY n`, params)).map((r) =>
    Number(r[0]),
  );
  await conn.close();
  return rows;
}

// ── count ───────────────────────────────────────────────────────────────────

test('count excludes hidden rows', async () => {
  const { store } = await fixture();
  eq(await store.count(LEADER), 3, 'leader');
  eq(await store.count(STRANGER), 0, 'stranger');
});

test('count is computed in SQL, not in JavaScript', async () => {
  // The gate's exact wording: if the count is computed over fetched rows, the
  // phase is not done. Traced rather than asserted — a COUNT(*) that reaches
  // SQLite carrying the predicate cannot have fetched the hidden rows to get
  // there.
  const { conn, store } = await fixture();
  conn.statements = [];
  conn.recording = true;
  await store.count(LEADER);
  conn.recording = false;

  const touching = conn.statements.filter((s) => s.includes('facts'));
  eq(touching.length, 1, `count issued ${touching.length} statements: ${touching.join(' | ')}`);
  const sql = touching[0];
  assert(/COUNT\(\*\)/i.test(sql), `not a COUNT(*): ${sql}`);
  // The predicate travelled with it — the database did the filtering.
  assert(sql.includes('grants') && sql.includes('subject_id'), `no predicate in: ${sql}`);
  // And it selected no payload: nothing was fetched to be counted.
  assert(!/facts\.payload/.test(sql), `count fetched payloads: ${sql}`);
});

test('count agrees with the length of visible()', async () => {
  const { store } = await fixture();
  for (const p of [LEADER, STRANGER, principal('visible-member')]) {
    eq(await store.count(p), (await store.visible(p)).length, `for ${p.personId}`);
  }
});

// ── filter ──────────────────────────────────────────────────────────────────

test('a caller filter cannot widen the result', async () => {
  const { store } = await fixture();
  const rows = await store.visible(LEADER, { where: '1 = 1 OR 1 = 1' });
  eq(rows.length, 3);
  eq([...new Set(rows.map((r) => r.subjectId))], ['visible-member']);
});

test('a caller filter targeting a hidden subject returns nothing', async () => {
  const { store } = await fixture();
  const rows = await store.visible(LEADER, {
    where: 'facts.subject_id = :who',
    params: { who: 'hidden-member' },
  });
  eq(rows, []);
  eq(
    await store.count(LEADER, {
      where: 'facts.subject_id = :who',
      params: { who: 'hidden-member' },
    }),
    0,
  );
});

test('a filter cannot confirm a hidden row by probing', async () => {
  const { store } = await fixture();
  const present = await store.count(LEADER, {
    where: 'facts.payload = :p',
    params: { p: 'hidden 0' },
  });
  const absent = await store.count(LEADER, {
    where: 'facts.payload = :p',
    params: { p: 'no such row' },
  });
  eq([present, absent], [0, 0], 'probing a hidden payload answered differently');
});

// ── sort order ──────────────────────────────────────────────────────────────

test('the sort column is allowlisted', async () => {
  const { store } = await fixture();
  await rejects(
    () => store.visible(LEADER, { orderBy: '(SELECT payload FROM facts LIMIT 1)' }),
    'a subquery was accepted as a sort column',
  );
});

test('pagination does not reveal gaps', async () => {
  // LIMIT/OFFSET apply after the predicate, so pages are dense. If hidden rows
  // participated in ordering, the second page would be short or empty and the
  // caller could infer how many rows they were not shown.
  const { store } = await fixture();
  const pages = [];
  for (const offset of [0, 2, 4]) pages.push(await store.visible(LEADER, { limit: 2, offset }));
  eq(pages.map((p) => p.length), [2, 1, 0]);
  const ids = pages.flatMap((p) => p.map((r) => r.id));
  eq(ids, [...ids].sort((a, b) => a - b), 'pages are not in id order');
  eq(ids.length, await store.count(LEADER), 'paged rows do not sum to COUNT(*)');
});

test('a descending sort reveals no more than an ascending one', async () => {
  const { store } = await fixture();
  const up = (await store.visible(LEADER, { orderBy: 'id' })).map((r) => r.id);
  const down = (await store.visible(LEADER, { orderBy: 'id', descending: true })).map((r) => r.id);
  eq(up, [...down].reverse());
});

// ── empty state ─────────────────────────────────────────────────────────────

test('refused and nonexistent are indistinguishable', async () => {
  // The one people forget. A member who declined to share must look exactly like
  // a member who is not in the system. If they look different, declining becomes
  // the signal, and every member who exercises the choice is marked by it.
  const { store } = await fixture();
  const refused = await store.visible(LEADER, {
    where: 'facts.subject_id = :s',
    params: { s: 'hidden-member' },
  });
  const absent = await store.visible(LEADER, {
    where: 'facts.subject_id = :s',
    params: { s: 'no-such-person' },
  });
  eq([refused, absent], [[], []]);
  const cRefused = await store.count(LEADER, {
    where: 'facts.subject_id = :s',
    params: { s: 'hidden-member' },
  });
  const cAbsent = await store.count(LEADER, {
    where: 'facts.subject_id = :s',
    params: { s: 'no-such-person' },
  });
  eq([cRefused, cAbsent], [0, 0]);
});

test('the subject list omits rather than blanks', async () => {
  const { store } = await fixture();
  eq(await store.subjects(LEADER), ['visible-member']);
  eq(await store.subjects(STRANGER), []);
});

test('a draft grant is indistinguishable from no grant', async () => {
  // Only a human seals. A grant the system inferred is recorded and inert.
  const { store } = await fixture();
  await store.recordGrant('hidden-member', 'leader', Band.CRAFT, GrantState.DRAFT, 'inferred from roster');
  eq(await store.subjects(LEADER), ['visible-member']);
  eq(await store.count(LEADER), 3);
});

test('a pending grant is indistinguishable from no grant', async () => {
  const { store } = await fixture();
  await store.recordGrant('hidden-member', 'leader', Band.FAMILY, GrantState.PENDING, 'awaiting signature');
  eq(await store.subjects(LEADER), ['visible-member']);
  eq(await store.count(LEADER), 3);
});

test('revocation is silent and immediate', async () => {
  const { conn, store } = await fixture();
  eq(await store.count(LEADER), 3);
  await store.revoke('visible-member', 'leader');
  eq(await store.count(LEADER), 0);
  eq(await store.subjects(LEADER), []);
  // No residue: the former grant is not readable as a former grant.
  const row = await conn.get("SELECT COUNT(*) FROM grants WHERE grantee_id = 'leader'");
  eq(Number(row[0]), 0);
});

// ── fail closed ─────────────────────────────────────────────────────────────

test('an unknown principal sees nothing', async () => {
  const { store } = await fixture();
  eq(await store.visible(principal('')), []);
  eq(await store.count(principal('nobody')), 0);
});

test('a grant cannot open a never-served band', async () => {
  // The deny applies to the union of allows, so no grant can win against it.
  const { store } = await fixture();
  await store.recordFact('visible-member', Band.SAFEGUARDING, 'routed elsewhere', {
    payload: 'must never be served',
  });
  await store.recordGrant('visible-member', 'leader', Band.FAMILY, GrantState.SEALED, 'consent form', {
    sealedBy: 'guardian',
  });
  const rows = await store.visible(LEADER);
  assert(
    rows.every((r) => r.band !== Band.SAFEGUARDING),
    'a safeguarding row was served',
  );
  eq(
    await store.count(LEADER, { where: 'facts.band = :b', params: { b: Band.SAFEGUARDING } }),
    0,
  );
  // And the subject cannot see their own either — NEVER_SERVED is above the
  // self rule, because the deny negates the union of allows.
  eq(
    await store.count(principal('visible-member'), {
      where: 'facts.band = :b',
      params: { b: Band.SAFEGUARDING },
    }),
    0,
  );
});

// ── the projection ──────────────────────────────────────────────────────────

test('at and above DERIVE_AT another person’s payload is NULL, the row is not', async () => {
  const { store } = await fixture();
  await store.recordFact('visible-member', Band.HEALTH, 'clinic note', {
    payload: 'the diagnosis',
    instruction: 'rotate out every twenty minutes',
  });
  await store.recordGrant('visible-member', 'leader', Band.HEALTH, GrantState.SEALED, 'consent form', {
    sealedBy: 'guardian',
  });
  const asLeader = (await store.visible(LEADER)).find((r) => r.band === Band.HEALTH);
  assert(asLeader, 'the health row was hidden entirely; it should be visible with a NULL payload');
  eq(asLeader.payload, null, 'the payload was forwarded');
  eq(asLeader.instruction, 'rotate out every twenty minutes', 'the instruction was withheld');

  const asSelf = (await store.visible(principal('visible-member'))).find(
    (r) => r.band === Band.HEALTH,
  );
  eq(asSelf.payload, 'the diagnosis', 'a person cannot see their own record');
});

// ── the schema refuses ──────────────────────────────────────────────────────

test('a fact with no source is refused by the schema', async () => {
  const { store } = await fixture();
  await rejects(() => store.recordFact('p', Band.ROSTER, ''), 'blank source accepted');
  await rejects(() => store.recordFact('p', Band.ROSTER, '   '), 'whitespace source accepted');
});

test('a band outside the range is refused by the schema', async () => {
  const { store } = await fixture();
  await rejects(() => store.recordFact('p', 7, 'source'), 'band 7 accepted');
  await rejects(() => store.recordFact('p', -1, 'source'), 'band -1 accepted');
});

test('a sealed grant with no signer is refused by the schema', async () => {
  const { store } = await fixture();
  await rejects(
    () => store.recordGrant('p', 'q', Band.CRAFT, GrantState.SEALED, 'form'),
    'unsigned seal accepted',
  );
  await rejects(
    () => store.recordGrant('p', 'q', Band.CRAFT, GrantState.SEALED, 'form', { sealedBy: '  ' }),
    'blank signer accepted',
  );
});

test('a grant in an invented state is refused by the schema', async () => {
  const { store } = await fixture();
  await rejects(
    () => store.recordGrant('p', 'q', Band.CRAFT, 'approved', 'form', { sealedBy: 'x' }),
    "state 'approved' accepted",
  );
});

// ── the compiler, independently of the policy ───────────────────────────────

test('no allows denies everything', async () => {
  const { sql, params } = compileRules([]);
  eq(sql, DENY_ALL);
  eq(await scratchRows(sql, params), []);
});

test('denies alone still deny everything', async () => {
  const { sql, params } = compileRules([rule(Effect.DENY, 'n = 3')]);
  eq(sql, DENY_ALL);
  eq(await scratchRows(sql, params), []);
});

test('allows are unioned', async () => {
  const { sql, params } = compileRules([
    rule(Effect.ALLOW, 'n < 2'),
    rule(Effect.ALLOW, 'n > 7'),
  ]);
  eq(await scratchRows(sql, params), [0, 1, 8, 9]);
});

test('a deny negates the union, not the first term', async () => {
  // The regression test for the missing-parentheses bug. With correct
  // precedence n=1 is denied even though the *first* allow permitted it, and
  // n=8 is denied even though the second did.
  const { sql, params } = compileRules([
    rule(Effect.ALLOW, 'n < 2'),
    rule(Effect.ALLOW, 'n > 7'),
    rule(Effect.DENY, 'n = 1'),
    rule(Effect.DENY, 'n = 8'),
  ]);
  eq(await scratchRows(sql, params), [0, 9]);
});

test('a later allow cannot reopen a denied row', async () => {
  const { sql, params } = compileRules([
    rule(Effect.DENY, 'n = 5'),
    rule(Effect.ALLOW, 'n >= 0'),
    rule(Effect.ALLOW, 'n = 5'),
  ]);
  assert(!(await scratchRows(sql, params)).includes(5), 'n=5 was reopened');
});

test('parameters are scoped per rule', async () => {
  const { sql, params } = compileRules([
    rule(Effect.ALLOW, 'n = {v}', { v: 3 }),
    rule(Effect.ALLOW, 'n = {v}', { v: 6 }),
  ]);
  eq(Object.values(params).sort(), [3, 6]);
  eq(await scratchRows(sql, params), [3, 6]);
});

test('a single allow needs no extra grouping', () => {
  eq(compileRules([rule(Effect.ALLOW, 'n = 1')]).sql, '(n = 1)');
});

test('explain reports reasons in order', () => {
  eq(
    explain([
      rule(Effect.ALLOW, 'n < 2', {}, 'own record'),
      rule(Effect.DENY, 'n = 1', {}, 'routed elsewhere'),
      rule(Effect.ALLOW, 'n = 9'),
    ]),
    ['allow: own record', 'deny: routed elsewhere'],
  );
});

test('an unknown placeholder in a rule fragment throws', () => {
  let threw = false;
  try {
    compileRules([rule(Effect.ALLOW, 'n = {missing}', { v: 1 })]);
  } catch {
    threw = true;
  }
  assert(threw, 'an undefined placeholder rendered silently');
});

// ── every statement the store issues is predicated ──────────────────────────

test('no read the store issues selects rows without a predicate', async () => {
  const { conn, store } = await fixture();
  conn.statements = [];
  conn.recording = true;
  await store.count(LEADER);
  await store.visible(LEADER);
  await store.subjects(LEADER);
  await store.visible(LEADER, { where: 'facts.band = :b', params: { b: Band.CRAFT } });
  await store.visible(LEADER, { orderBy: 'band', descending: true, limit: 2, offset: 1 });
  conn.recording = false;

  for (const sql of conn.statements.filter((s) => s.includes('FROM facts'))) {
    assert(/ WHERE /.test(sql), `an unpredicated read reached SQLite: ${sql}`);
    assert(
      sql.includes(':r0_viewer') || sql.includes(' 0'),
      `a read carried no compiled predicate: ${sql}`,
    );
  }
  eq(conn.statements.filter((s) => s.includes('FROM facts')).length, 5);
});

// ---------------------------------------------------------------------------

for (const [name, fn] of pending) {
  try {
    await fn();
    passed += 1;
    if (VERBOSE) console.log(`ok    ${name}`);
  } catch (error) {
    failures.push([name, error]);
    console.error(`FAIL  ${name}\n      ${error.message.split('\n').join('\n      ')}`);
  }
}

console.log(`\n${passed}/${pending.length} gate tests passed`);
if (failures.length) {
  console.error(`${failures.length} failed`);
  process.exit(1);
}
