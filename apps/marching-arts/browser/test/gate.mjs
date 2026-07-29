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
  GrantVia,
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

/** A birthdate `yearsAgo` years before today, in the form the CHECK demands. */
function birthdate(yearsAgo) {
  const d = new Date();
  d.setUTCFullYear(d.getUTCFullYear() - yearsAgo);
  return d.toISOString().slice(0, 10);
}

/**
 * A fifteen-year-old with a registered guardian, and an adult member.
 *
 * Mirrors the `roster` fixture in `../tests/test_consent.py`, minus the consent
 * library itself — that core is Python-only. What is reproduced here is the part
 * the resolver owns: rows, people, guardianships and grants.
 */
async function guardianFixture() {
  const conn = new TracingConnection(await openMemory(api));
  const store = await Store.open(conn);
  for (let i = 0; i < 3; i++) {
    await store.recordFact('minor-member', Band.CRAFT, 'rehearsal log', { payload: `minor ${i}` });
    await store.recordFact('adult-member', Band.CRAFT, 'rehearsal log', { payload: `adult ${i}` });
  }
  await store.recordPerson('minor-member', birthdate(15), 'registration form');
  await store.recordPerson('adult-member', birthdate(30), 'registration form');
  await store.recordGuardianship('parent', 'minor-member', 'child', 'registration form');
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

// ── guardian authority, and the fact that it expires ────────────────────────
//
// These exist because the differential structurally cannot check them. The
// randomised corpus in gen_reference.py contains no `people` rows and no
// guardian-derived grants, so deleting the guardian clause from policy.ts
// changes *no answer* anywhere in it — all 14,650 disagreements that mutation
// produces are SQL text and bound parameters, not a single count or row. Text
// agreement is a real check and it caught the drift that started this work, but
// it is agreement about spelling. The tests below say what the clause is *for*,
// in answers, the way `../tests/test_consent.py` does on the Python side.

test('a guardian sees their minor’s rows while the minor is a minor', async () => {
  const { store } = await guardianFixture();
  await store.recordGrant('minor-member', 'parent', Band.CRAFT, GrantState.SEALED, 'consent form', {
    sealedBy: 'parent',
    grantedVia: GrantVia.GUARDIAN,
  });
  eq(await store.count(principal('parent')), 3, 'the guardian sees nothing');
  eq(await store.subjects(principal('parent')), ['minor-member']);
});

test('guardian access stops at majority with nothing scheduled', async () => {
  // The birthday is the mechanism. No job runs, and no job can fail to run: the
  // grant row is untouched and the access is gone anyway, because the predicate
  // re-asks on every read.
  const { conn, store } = await guardianFixture();
  await store.recordGrant('minor-member', 'parent', Band.CRAFT, GrantState.SEALED, 'consent form', {
    sealedBy: 'parent',
    grantedVia: GrantVia.GUARDIAN,
  });
  eq(await store.count(principal('parent')), 3);

  await store.recordPerson('minor-member', birthdate(18), 'corrected registration');

  eq(await store.count(principal('parent')), 0, 'a guardian kept an adult’s record');
  eq(await store.subjects(principal('parent')), []);
  eq(
    await store.visible(principal('parent'), {
      where: 'facts.subject_id = :s',
      params: { s: 'minor-member' },
    }),
    [],
  );
  // Untouched in the table. Nothing ran; the access is gone regardless.
  const row = await conn.get("SELECT state, granted_via FROM grants WHERE grantee_id = 'parent'");
  eq([String(row[0]), String(row[1])], [GrantState.SEALED, GrantVia.GUARDIAN]);
});

test('a member-granted grant is unaffected by the subject’s age', async () => {
  // The control. Without this, "deny everything" would pass the test above.
  const { store } = await guardianFixture();
  await store.recordGrant('adult-member', 'leader', Band.CRAFT, GrantState.SEALED, 'consent form', {
    sealedBy: 'adult-member',
    grantedVia: GrantVia.MEMBER,
  });
  eq(await store.count(LEADER), 3, 'a member’s own consent stopped resolving');
  await store.recordPerson('adult-member', birthdate(80), 'corrected registration');
  eq(await store.count(LEADER), 3, 'the member grant depended on the birthdate');
});

test('a subject still sees their own record after majority', async () => {
  // Guardian expiry withdraws the guardian, not the member. The self rule needs
  // no grant, so nothing about a birthday touches it.
  const { store } = await guardianFixture();
  await store.recordPerson('minor-member', birthdate(18), 'corrected registration');
  eq(await store.count(principal('minor-member')), 3);
});

// ── the schema refuses, on the guardian path ────────────────────────────────
//
// Migration 002's triggers. They hold against a writer who never heard of them,
// including one written in JavaScript, because they live in the database rather
// than in either implementation.

test('a minor’s sealed grant must be guardian-derived', async () => {
  const { store } = await guardianFixture();
  await rejects(
    () =>
      store.recordGrant('minor-member', 'leader', Band.CRAFT, GrantState.SEALED, 'consent form', {
        sealedBy: 'parent',
      }),
    'a minor consented for themselves',
  );
});

test('only a registered guardian may seal for a minor', async () => {
  const { store } = await guardianFixture();
  await rejects(
    () =>
      store.recordGrant('minor-member', 'leader', Band.CRAFT, GrantState.SEALED, 'consent form', {
        sealedBy: 'some-adult',
        grantedVia: GrantVia.GUARDIAN,
      }),
    'an unregistered adult sealed for a minor',
  );
});

test('guardian authority cannot be written for an adult', async () => {
  // Not merely un-honoured at read time — unwritable, so the row cannot sit
  // there looking valid.
  const { store } = await guardianFixture();
  await store.recordGuardianship('parent', 'adult-member', 'other', 'registration form');
  await rejects(
    () =>
      store.recordGrant('adult-member', 'leader', Band.CRAFT, GrantState.SEALED, 'consent form', {
        sealedBy: 'parent',
        grantedVia: GrantVia.GUARDIAN,
      }),
    'guardian authority was written over an adult',
  );
});

test('consent may not be signed or requested by the beneficiary', async () => {
  const { store } = await guardianFixture();
  await rejects(
    () =>
      store.recordGrant('adult-member', 'leader', Band.CRAFT, GrantState.SEALED, 'consent form', {
        sealedBy: 'leader',
      }),
    'the beneficiary signed their own access',
  );
  await rejects(
    () =>
      store.recordGrant('adult-member', 'leader', Band.CRAFT, GrantState.DRAFT, 'consent form', {
        requestedBy: 'leader',
      }),
    'the beneficiary requested their own access',
  );
  // The carve-out: a registered guardian of the subject, whose access to their
  // own minor's record is the relationship rather than an abuse of one.
  await store.recordGrant('minor-member', 'parent', Band.CRAFT, GrantState.SEALED, 'consent form', {
    sealedBy: 'parent',
    grantedVia: GrantVia.GUARDIAN,
  });
  eq(await store.count(principal('parent')), 3);
});

test('a guardianship must be over somebody else who exists', async () => {
  const { store } = await guardianFixture();
  await rejects(
    () => store.recordGuardianship('minor-member', 'minor-member', 'other', 'form'),
    'somebody was made their own guardian',
  );
  await rejects(
    () => store.recordGuardianship('parent', 'no-such-member', 'child', 'form'),
    'a guardianship over nobody was accepted',
  );
});

test('a malformed birthdate is refused rather than read as NULL', async () => {
  // A CHECK that evaluates to NULL passes. Without the IS NOT NULL half, a
  // fourteen-year-old with a typo'd birthdate quietly becomes an adult.
  const { store } = await guardianFixture();
  await rejects(() => store.recordPerson('p', 'not-a-date', 'form'), 'a non-date was accepted');
  await rejects(() => store.recordPerson('p', '2011-6-1', 'form'), 'an unnormalised date was accepted');
});

// ── migration 004: the guardian rule survives per-subject partitioning ───────
//
// The resolver does not write the consent chain — `subject_consent` is
// Python-only and stays that way. The *schema* is ported, though, and 003's
// trigger matched `new.chain = 'consent'` exactly, so partitioning the chain as
// `consent/<subject_hash>` silently stopped it firing. This is the check that
// 004's replacement landed on this side too.

async function chainInsert(conn, chain, seq, row) {
  await conn.run('INSERT INTO consent_chain(chain, seq, row) VALUES (:c, :s, :r)', {
    c: chain,
    s: seq,
    r: JSON.stringify(row),
  });
}

test('a minor’s use-consent is refused in a per-subject chain partition', async () => {
  const { conn } = await guardianFixture();
  const granted = { subject_id: 'minor-member', status: 'granted', granted_by: 'minor-member' };
  await rejects(
    () => chainInsert(conn, 'consent/9f86d081884c7d65', 1, granted),
    'a minor consented for themselves in a partitioned chain',
  );
  // The bare name is kept on purpose: a writer reaching past the module straight
  // to SQL must not be able to dodge the rule by using the old chain name.
  await rejects(
    () => chainInsert(conn, 'consent', 1, granted),
    'a minor consented for themselves under the bare chain name',
  );
});

test('a guardian’s use-consent lands, and unrelated chains are untouched', async () => {
  const { conn } = await guardianFixture();
  await chainInsert(conn, 'consent/9f86d081884c7d65', 1, {
    subject_id: 'minor-member',
    status: 'granted',
    granted_by: 'parent',
  });
  // An adult grants their own; and a chain that is not a consent chain is not
  // this trigger's business.
  await chainInsert(conn, 'consent/ab12', 1, {
    subject_id: 'adult-member',
    status: 'granted',
    granted_by: 'adult-member',
  });
  await chainInsert(conn, 'disclosure/9f86', 1, {
    subject_id: 'minor-member',
    status: 'granted',
    granted_by: 'minor-member',
  });
  const row = await conn.get('SELECT COUNT(*) FROM consent_chain');
  eq(Number(row[0]), 3);
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
