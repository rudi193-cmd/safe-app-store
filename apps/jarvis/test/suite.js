// The suite runs inside real Chromium against real IndexedDB.
//
// It could not run in Node: every assertion below goes through an IDB
// transaction and, in the recall cases, an index cursor. A Node run would
// need a stand-in implementation, and the thing it was standing in for would
// then never execute anywhere before a user hit it.
//
// What this suite structurally cannot see, stated plainly so a green run is
// not mistaken for more than it is:
//   * Any call to the Anthropic API. Nothing here sends a request, so the
//     request shape, the tool-call round trip against a live model, and the
//     fallback-rejection retry path are all unverified by this suite.
//   * Speech recognition. Headless Chromium exposes no microphone, so
//     Listener is probed but never driven.
//   * Anything about a closed tab. Reminder delivery after the page is gone
//     is not implemented and not tested; see the durability probe.
//   * Any call to a real willow-mcp server. Discovery, dynamic client
//     registration, the OAuth popup round trip, and token refresh are
//     exercised only by hand against a running instance. What runs here is
//     the pure PKCE/URL/framing logic and the tool-runner's mapping of a
//     willow-mcp result onto {data, text, isError}, against a fake session.

import { Memory, weakestProvenance, normalizeSubject, deleteDatabase } from '../src/memory.js';
import { tokenize, stem, tokensFor } from '../src/text.js';
import { createToolRunner } from '../src/tools.js';
import { buildMemoryContext } from '../src/claude.js';
import { sentences } from '../src/voice.js';
import { probeReminderDurability, probeSpeechInput } from '../src/capability.js';
import { isNative, platformName, hasPlugin, Reminders, KeyStore } from '../src/platform.js';
import { generatePkce, buildAuthorizeUrl, parseSseJsonRpc } from '../src/willow.js';

class Assert extends Error {}

function ok(cond, msg) {
  if (!cond) throw new Assert(msg);
}

function eq(actual, expected, msg) {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a !== e) throw new Assert(`${msg}\n  expected: ${e}\n  actual:   ${a}`);
}

const tests = [];
const test = (name, fn) => tests.push({ name, fn });

/** Each test gets a private database, so ordering between tests cannot matter. */
let dbCounter = 0;
async function fresh() {
  const name = `jarvis-test-${Date.now()}-${dbCounter++}`;
  await deleteDatabase(name);
  const memory = new Memory({ name });
  await memory.open();
  return { memory, name };
}

// --- memory: the basics ------------------------------------------------------

test('cold start has no facts', async () => {
  const { memory } = await fresh();
  const { facts, provenance } = await memory.recall();
  eq(facts.length, 0, 'a new store should be empty');
  eq(provenance, null, 'provenance of an empty set is null, not a default');
  memory.close();
});

test('remember then recall by subject', async () => {
  const { memory } = await fresh();
  await memory.remember({ subject: 'coffee', kind: 'preference', text: 'Oat flat white, no sugar.', provenance: 'stated' });
  await memory.remember({ subject: 'commute', kind: 'fact', text: 'Cycles to work.', provenance: 'stated' });

  const { facts } = await memory.recall({ subject: 'coffee' });
  eq(facts.length, 1, 'subject query must return only that subject');
  eq(facts[0].text, 'Oat flat white, no sugar.', 'wrong fact returned');
  memory.close();
});

test('subject lookup is normalized on both write and read', async () => {
  const { memory } = await fresh();
  await memory.remember({ subject: '  Coffee  ', kind: 'preference', text: 'Oat flat white.', provenance: 'stated' });
  const { facts } = await memory.recall({ subject: 'COFFEE' });
  eq(facts.length, 1, 'normalization must make these the same key');
  eq(normalizeSubject('  Multi   Word  '), 'multi word', 'internal whitespace should collapse');
  memory.close();
});

test('recall returns newest first and respects limit', async () => {
  const { memory } = await fresh();
  for (let i = 0; i < 6; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await memory.remember({ subject: 'log', kind: 'fact', text: `entry ${i}`, provenance: 'stated' });
  }
  const { facts } = await memory.recall({ subject: 'log', limit: 3 });
  eq(facts.length, 3, 'limit must bound the result set');
  eq(facts.map((f) => f.text), ['entry 5', 'entry 4', 'entry 3'], 'results must be newest-first');
  memory.close();
});

test('recall by kind', async () => {
  const { memory } = await fresh();
  await memory.remember({ subject: 'sister', kind: 'person', text: 'Nadia, lives in Leeds.', provenance: 'stated' });
  await memory.remember({ subject: 'coffee', kind: 'preference', text: 'Oat flat white.', provenance: 'stated' });
  const { facts } = await memory.recall({ kind: 'person' });
  eq(facts.length, 1, 'kind query must filter');
  eq(facts[0].subject, 'sister', 'wrong record for kind query');
  memory.close();
});

// --- the three invariants ----------------------------------------------------

test('INVARIANT absence is a recorded value, distinct from no record', async () => {
  const { memory } = await fresh();
  const before = await memory.recall({ subject: 'dietary' });
  eq(before.facts.length, 0, 'precondition: nothing recorded yet');

  await memory.remember({
    subject: 'dietary',
    kind: 'absence',
    text: 'No dietary restrictions — asked and confirmed.',
    provenance: 'stated',
  });

  const after = await memory.recall({ subject: 'dietary' });
  eq(after.facts.length, 1, 'a recorded absence must be retrievable as a row');
  eq(after.facts[0].kind, 'absence', 'the absence must keep its kind');
  ok(
    before.facts.length !== after.facts.length,
    'having-no-record and having-an-absence-record must be distinguishable',
  );
  memory.close();
});

test('INVARIANT corrections land beside the record, never on top of it', async () => {
  const { memory } = await fresh();
  const first = await memory.remember({
    subject: 'coffee',
    kind: 'preference',
    text: 'Drinks espresso.',
    provenance: 'inferred',
  });

  const second = await memory.remember({
    subject: 'coffee',
    kind: 'preference',
    text: 'Actually drinks oat flat whites.',
    provenance: 'stated',
    supersedes: first.id,
  });

  const { facts } = await memory.recall({ subject: 'coffee' });
  eq(facts.length, 1, 'only the current fact should be live');
  eq(facts[0].id, second.id, 'the live fact should be the correction');

  const original = await memory.getFact(first.id);
  ok(original, 'the superseded record must still exist — a correction is not a delete');
  eq(original.text, 'Drinks espresso.', 'the superseded record must keep its original text');
  eq(original.provenance, 'inferred', 'the superseded record must keep its original provenance');
  eq(original.createdAt, first.createdAt, 'the superseded record must keep its original timestamp');
  eq(original.live, 0, 'the superseded record must be marked not-live');

  const trail = await memory.history('coffee');
  eq(trail.length, 2, 'history must show both what was believed and what replaced it');
  eq(trail[1].supersedes, first.id, 'the correction must point at what it replaced');
  memory.close();
});

test('INVARIANT provenance is the weakest link, not an average', async () => {
  eq(weakestProvenance([{ provenance: 'stated' }, { provenance: 'stated' }]), 'stated', 'all-stated stays stated');
  eq(
    weakestProvenance([{ provenance: 'stated' }, { provenance: 'stated' }, { provenance: 'assumed' }]),
    'assumed',
    'one assumption drags the whole set down — averaging would hide it',
  );
  eq(weakestProvenance([{ provenance: 'stated' }, { provenance: 'inferred' }]), 'inferred', 'min over the ladder');
  eq(weakestProvenance([]), null, 'no facts means no provenance, not a default');

  const { memory } = await fresh();
  await memory.remember({ subject: 'plan', kind: 'fact', text: 'Flies Tuesday.', provenance: 'stated' });
  await memory.remember({ subject: 'plan', kind: 'fact', text: 'Probably needs a hotel.', provenance: 'assumed' });
  const { provenance } = await memory.recall({ subject: 'plan' });
  eq(provenance, 'assumed', 'a recall is worth its weakest contributing fact');
  memory.close();
});

test('forget retires a fact without destroying the record', async () => {
  const { memory } = await fresh();
  const fact = await memory.remember({ subject: 'gym', kind: 'fact', text: 'Goes Tuesdays.', provenance: 'stated' });
  await memory.forget(fact.id);

  const { facts } = await memory.recall({ subject: 'gym' });
  eq(facts.length, 0, 'a forgotten fact must not appear in recalls');
  const row = await memory.getFact(fact.id);
  ok(row, 'the record itself must survive being forgotten');
  eq(row.text, 'Goes Tuesdays.', 'the forgotten record must keep its contents');
  memory.close();
});

test('remember rejects unknown kinds and provenances', async () => {
  const { memory } = await fresh();
  let threw = 0;
  try {
    await memory.remember({ subject: 'x', kind: 'vibes', text: 'y', provenance: 'stated' });
  } catch {
    threw += 1;
  }
  try {
    await memory.remember({ subject: 'x', kind: 'fact', text: 'y', provenance: 'pretty sure' });
  } catch {
    threw += 1;
  }
  eq(threw, 2, 'both an unknown kind and an unknown provenance must be rejected at the boundary');
  memory.close();
});

// --- reminders ---------------------------------------------------------------

test('reminders separate due from pending, and firing is one-way', async () => {
  const { memory } = await fresh();
  const past = await memory.addReminder({ at: Date.now() - 60_000, text: 'call back' });
  await memory.addReminder({ at: Date.now() + 3_600_000, text: 'stand up' });

  const due = await memory.dueReminders();
  eq(due.length, 1, 'only the overdue reminder is due');
  eq(due[0].text, 'call back', 'wrong reminder came back due');
  eq((await memory.pendingReminders()).length, 2, 'both are still pending until fired');

  await memory.markFired(past.id);
  eq((await memory.dueReminders()).length, 0, 'a fired reminder must not come back due');
  eq((await memory.pendingReminders()).length, 1, 'a fired reminder leaves the pending set');
  memory.close();
});

// --- tool dispatch -----------------------------------------------------------

test('tool runner round-trips remember into recall', async () => {
  const { memory } = await fresh();
  const run = createToolRunner({ memory, session: 'test' });

  const stored = await run('remember', {
    subject: 'coffee',
    kind: 'preference',
    text: 'Oat flat white, no sugar.',
    provenance: 'stated',
  });
  ok(!stored.isError, `remember should succeed: ${stored.text}`);

  const recalled = await run('recall', { subject: 'coffee' });
  ok(!recalled.isError, 'recall should succeed');
  ok(recalled.text.includes('Oat flat white'), 'the stored fact should come back through the tool surface');
  ok(recalled.text.includes('stated'), 'the tool result must carry provenance to the model');
  memory.close();
});

test('an empty recall tells the model it means no record, not no truth', async () => {
  const { memory } = await fresh();
  const run = createToolRunner({ memory, session: 'test' });
  const out = await run('recall', { subject: 'nothing-here' });
  ok(!out.isError, 'an empty recall is not an error');
  ok(
    /not evidence|nothing has been recorded/i.test(out.text),
    'an empty result must say it is an absence of record, or the model will read it as a denial',
  );
  memory.close();
});

test('tool failures come back as results, not exceptions', async () => {
  const { memory } = await fresh();
  const run = createToolRunner({ memory, session: 'test' });

  const unknown = await run('teleport', {});
  ok(unknown.isError, 'an unknown tool must be reported as an error result');

  const bad = await run('forget', { id: 999999 });
  ok(bad.isError, 'forgetting a nonexistent id must be an error result');

  const broken = await run('set_reminder', { text: 'no time given' });
  ok(broken.isError, 'a reminder with no time must be an error result the model can read');
  memory.close();
});

test('set_reminder schedules and list_reminders sees it', async () => {
  const { memory } = await fresh();
  let notified = 0;
  const run = createToolRunner({ memory, session: 'test', onReminderScheduled: () => { notified += 1; } });

  const set = await run('set_reminder', { in_minutes: 30, text: 'take the bins out' });
  ok(!set.isError, `set_reminder should succeed: ${set.text}`);
  eq(notified, 1, 'scheduling must notify the app so the tick loop is armed');
  ok(/only while this page is open/i.test(set.text), 'the model must be told reminders do not survive a closed tab');

  const list = await run('list_reminders', {});
  ok(list.text.includes('take the bins out'), 'the scheduled reminder should be listed');
  memory.close();
});

test('get_context reports the clock and names what it cannot read', async () => {
  const { memory } = await fresh();
  const run = createToolRunner({ memory, session: 'test' });
  const out = await run('get_context', {});
  const ctx = JSON.parse(out.text);
  ok(typeof ctx.iso === 'string' && ctx.iso.includes('T'), 'context must carry a real timestamp');
  ok(typeof ctx.timezone === 'string' && ctx.timezone.length > 0, 'context must carry a timezone');
  ok('battery' in ctx, 'battery must be reported — as a reading or as a named reason it is missing');
  memory.close();
});

// --- retrieval ---------------------------------------------------------------

test('tokenizing drops stopwords and stems plurals', async () => {
  eq(tokenize('what do you know about my morning meetings'), ['morn', 'meet'], 'stopwords out, content stemmed');
  eq(stem('meetings'), 'meet', 'plural then verb ending');
  eq(stem('getting'), 'get', 'doubled consonants collapse after -ing');
  eq(stem('stories'), 'story', '-ies becomes -y');
  eq(stem('glasses'), 'glass', '-sses keeps the stem intact');
  eq(stem('bus'), 'bus', 'a word ending in -us is not a plural');
  eq(stem('analysis'), 'analysis', 'a word ending in -is is not a plural');
});

test('the stemmer refuses to collapse unrelated words', async () => {
  // Over-stemming is the dangerous direction. A miss is silence; a false
  // match is the assistant answering confidently about the wrong subject.
  eq(stem('string'), 'string', 'stripping -ing here would leave "str" and collide with everything');
  eq(stem('spring'), 'spring', 'same — too little left to be a word');
  ok(stem('university') !== stem('universal'), 'unrelated words must not merge');
  ok(stem('passport') !== stem('passing'), 'unrelated words must not merge');
});

test('the write path and the read path agree on tokens', async () => {
  // If these diverge, the index is written in one vocabulary and queried in
  // another. Both halves look correct in isolation and nothing is ever found.
  // Asserting equality on the same input is the sharp form of that: it does
  // not depend on which words happen to be stopwords today.
  const phrase = 'Cycles to the office every morning, about 25 minutes.';
  eq(
    tokensFor({ subject: '', aliases: [], text: phrase }).all.sort(),
    tokenize(phrase).sort(),
    'the write path must index exactly the tokens the read path will look for',
  );

  // And the alias genuinely reaches across phrasings.
  const { all } = tokensFor({ subject: 'commute', aliases: ['office travel'], text: 'Cycles in.' });
  ok(tokenize('how long to the office').some((t) => all.includes(t)), 'an alias must bridge the query to the fact');
});

test('SEMANTIC search finds a fact through an alias the subject never mentions', async () => {
  const { memory } = await fresh();
  await memory.remember({
    subject: 'commute',
    kind: 'fact',
    text: 'Cycles in, about 25 minutes.',
    provenance: 'stated',
    aliases: ['office', 'work', 'getting to work', 'travel'],
  });
  await memory.remember({ subject: 'coffee', kind: 'preference', text: 'Oat flat white.', provenance: 'stated' });

  // The phrasing shares no word with the subject or the body text.
  const { facts } = await memory.search('how long does getting to the office take');
  ok(facts.length > 0, 'an alias must make the fact reachable from different wording');
  eq(facts[0].subject, 'commute', 'the aliased fact should rank first');
  ok(facts[0].matched.includes('offic') || facts[0].matched.includes('office'), 'the match reason must be reported');
  memory.close();
});

test('SEMANTIC ranking prefers a subject hit over a passing mention', async () => {
  const { memory } = await fresh();
  // The fact filed under the word is written FIRST, so recency actively
  // favours the wrong answer. An earlier version of this test wrote them the
  // other way round and passed even with the weighting removed — the tie was
  // broken by createdAt, and the test was reporting on recency while claiming
  // to be about relevance. It also flaked, because two writes inside the same
  // millisecond tie on that too.
  await memory.remember({ subject: 'dentist', kind: 'person', text: 'Dr Achebe, Mill Road.', provenance: 'stated' });
  await memory.remember({
    subject: 'standup',
    kind: 'fact',
    text: 'Mentioned in passing that the dentist is nearby.',
    provenance: 'stated',
  });

  const { facts } = await memory.search('dentist');
  const filed = facts.find((f) => f.subject === 'dentist');
  const mentioned = facts.find((f) => f.subject === 'standup');
  ok(filed && mentioned, 'both facts should match the query');
  // Asserted on score rather than position: an ordering assertion can be
  // satisfied by a tiebreak, a score comparison cannot.
  ok(
    filed.score > mentioned.score,
    `a fact filed under the word must score above one that merely mentions it (${filed.score} vs ${mentioned.score})`,
  );
  eq(facts[0].subject, 'dentist', 'and must therefore rank first, despite being older');
  memory.close();
});

test('SEMANTIC a short precise fact outranks a bloated one', async () => {
  const { memory } = await fresh();
  // The defect this catches was found by measuring the ranker against a real
  // corpus, not by reading it: adding aliases made ranking WORSE, because the
  // score was a raw sum and a fact with many aliases collects more matched
  // tokens than a short fact that is actually about the query.
  //
  // `grab-bag` matches all three query tokens; `dentist` matches two. On a raw
  // sum the grab-bag wins, and it wins by the *rarest* token — `reminder`,
  // which only it has — so the failure is decisive rather than a tie broken by
  // recency. It must lose anyway: two of its own three tokens matching says far
  // more than three of a dozen.
  //
  // Written so the wrong answer is stored LAST, so the recency tiebreak favours
  // the wrong answer too. A test that can pass on the tiebreak while claiming to
  // be about relevance has been shipped in this file before.
  await memory.remember({
    subject: 'dentist',
    kind: 'fact',
    text: 'Appointment on Tuesday.',
    provenance: 'stated',
  });
  await memory.remember({
    subject: 'calendar',
    kind: 'fact',
    aliases: ['dentist', 'appointment', 'reminder', 'standup', 'review',
      'flight', 'haircut', 'plumber', 'vet', 'school run', 'payday',
      'invoice', 'renewal', 'birthday', 'delivery', 'inspection'],
    text: 'Everything lives here.',
    provenance: 'stated',
  });

  const { facts } = await memory.search('dentist appointment reminder');
  eq(facts[0].subject, 'dentist', 'a grab-bag must not win by being large');
  memory.close();
});

test('SEMANTIC length normalization does not punish a richly-aliased fact', async () => {
  const { memory } = await fresh();
  // The dual of the test above, and the reason the divisor is a square root
  // rather than the length itself. Dividing by length outright would replace
  // one bias with its mirror image: a fact would be penalised for carrying the
  // aliases that make it findable at all, which is the feature, not a defect.
  //
  // Here the long fact is the RIGHT answer — the query is about it in five
  // different words — and the short fact clips one token in passing. Square
  // root keeps the long fact ahead; dividing by length hands it to the short
  // one. Without any normalization the long fact also wins, so this test says
  // nothing about the previous one and cannot substitute for it.
  await memory.remember({
    subject: 'passport renewal',
    kind: 'fact',
    aliases: ['embassy', 'visa', 'photos', 'courier', 'biometrics',
      'fee', 'expedited', 'checklist', 'consulate', 'notary'],
    text: 'Ten year renewal, submitted online in March.',
    provenance: 'stated',
  });
  await memory.remember({
    subject: 'appointment',
    kind: 'fact',
    text: 'Tuesday.',
    provenance: 'stated',
  });

  const { facts } = await memory.search('passport renewal embassy visa photos appointment');
  eq(facts[0].subject, 'passport renewal', 'a fact must not be punished for its aliases');
  memory.close();
});

test('SEMANTIC a rare word outranks two common ones', async () => {
  const { memory } = await fresh();
  // Six facts share two common words; one fact has a word nobody else uses.
  // The common-word facts match *twice*, so without inverse-document-freq
  // weighting they win on raw count. They must lose anyway — two words you
  // use constantly say less about which fact you meant than one you almost
  // never use. Every match here is on a subject, so subject weighting is held
  // constant and rarity is the only variable left.
  for (let i = 0; i < 6; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await memory.remember({
      subject: `work team ${i}`,
      kind: 'fact',
      text: `Standing item ${i}.`,
      provenance: 'stated',
    });
  }
  await memory.remember({ subject: 'passport', kind: 'fact', text: 'Expires in March.', provenance: 'stated' });

  const { facts } = await memory.search('work team passport');
  eq(facts[0].subject, 'passport', 'one rare token must beat two common ones');
  ok(facts[0].score > 0, 'a ranked result must carry its score');
  memory.close();
});

test('SEMANTIC search matches across singular and plural', async () => {
  const { memory } = await fresh();
  await memory.remember({
    subject: 'standup',
    kind: 'fact',
    text: 'Nine fifteen, Mondays.',
    provenance: 'stated',
    aliases: ['meetings'],
  });
  // The stored alias is plural and the query is singular. Only stemming
  // bridges them, and it has to run on both sides to do it.
  const { facts } = await memory.search('when is that meeting');
  eq(facts.length, 1, 'stemming must bridge plural storage and singular query');
  eq(facts[0].subject, 'standup', 'the right fact must be found');
  memory.close();
});

test('search excludes retired facts and survives correction', async () => {
  const { memory } = await fresh();
  const first = await memory.remember({
    subject: 'commute',
    kind: 'fact',
    text: 'Drives in.',
    provenance: 'stated',
    aliases: ['office'],
  });
  eq((await memory.search('office')).facts.length, 1, 'precondition: findable before correction');

  await memory.remember({
    subject: 'commute',
    kind: 'fact',
    text: 'Cycles in now.',
    provenance: 'stated',
    aliases: ['office'],
    supersedes: first.id,
  });

  const { facts } = await memory.search('office');
  eq(facts.length, 1, 'a superseded fact must leave the search index');
  eq(facts[0].text, 'Cycles in now.', 'the correction must be what is found');

  const retired = await memory.getFact(first.id);
  eq(retired.text, 'Drives in.', 'the retired record keeps its text');
  ok(retired.tokens.length > 0, 'the retired record keeps its tokens for history');
  eq(retired.liveTokens, [], 'only the index projection is emptied');
  memory.close();
});

test('search on an all-stopword query returns nothing rather than everything', async () => {
  const { memory } = await fresh();
  await memory.remember({ subject: 'coffee', kind: 'preference', text: 'Oat flat white.', provenance: 'stated' });
  const { facts, tokens } = await memory.search('what about the');
  eq(tokens.length, 0, 'a query of pure stopwords has no usable tokens');
  eq(facts.length, 0, 'and must return nothing, not the whole store');
  memory.close();
});

test('MIGRATION facts written before search shipped stay findable', async () => {
  // The upgrade path is the one place where a mistake destroys data already
  // on a user's device — every fact would still be there and none of it would
  // ever surface again. Build a v1 store by hand, then open it at the current
  // version and search it.
  const name = `jarvis-migration-${Date.now()}`;
  await deleteDatabase(name);

  await new Promise((resolve, reject) => {
    const open = indexedDB.open(name, 1);
    open.onupgradeneeded = () => {
      const facts = open.result.createObjectStore('facts', { keyPath: 'id', autoIncrement: true });
      facts.createIndex('subject_live_created', ['subject', 'live', 'createdAt']);
      facts.createIndex('kind_live_created', ['kind', 'live', 'createdAt']);
      facts.createIndex('live_created', ['live', 'createdAt']);
      facts.createIndex('supersedes', 'supersedes');
      const reminders = open.result.createObjectStore('reminders', { keyPath: 'id', autoIncrement: true });
      reminders.createIndex('pending_at', ['pending', 'at']);
    };
    open.onsuccess = () => {
      const db = open.result;
      const tx = db.transaction(['facts'], 'readwrite');
      // Exactly the shape v1 wrote: no aliases, no token fields.
      tx.objectStore('facts').add({
        subject: 'passport',
        kind: 'fact',
        text: 'Expires in March.',
        provenance: 'stated',
        supersedes: null,
        live: 1,
        createdAt: Date.now(),
        session: 'old',
      });
      tx.oncomplete = () => {
        db.close();
        resolve();
      };
      tx.onerror = () => reject(tx.error);
    };
    open.onerror = () => reject(open.error);
  });

  const memory = new Memory({ name });
  await memory.open();
  const { facts } = await memory.search('passport');
  eq(facts.length, 1, 'a fact written before the index existed must be backfilled, not orphaned');
  eq(facts[0].text, 'Expires in March.', 'and must keep its contents through the upgrade');
  eq((await memory.recall({ subject: 'passport' })).facts.length, 1, 'the pre-existing indices must still work');
  memory.close();
});

test('memory context ranks matches and labels unmatched background', async () => {
  const { memory } = await fresh();
  eq(await buildMemoryContext(memory, 'anything at all'), null, 'no facts means no injected block');

  await memory.remember({
    subject: 'commute',
    kind: 'fact',
    text: 'Cycles in.',
    provenance: 'stated',
    aliases: ['office', 'work'],
  });
  await memory.remember({ subject: 'coffee', kind: 'preference', text: 'Oat flat white.', provenance: 'stated' });

  const ctx = await buildMemoryContext(memory, 'how long to the office');

  // Assert against the fact lines, not the whole block. The instruction prose
  // mentions "(recent)" too, so a naive regex over `ctx` passes whether or not
  // any fact is actually labelled — it tests the wording, not the mechanism.
  const factLines = ctx.split('\n').filter((l) => l.startsWith('#'));
  eq(factLines.length, 2, 'both the match and the background fact should be listed');

  const matched = factLines.find((l) => l.includes('Cycles in.'));
  const background = factLines.find((l) => l.includes('Oat flat white.'));
  ok(matched, 'the aliased fact must be injected');
  ok(/matched: /.test(matched), 'a ranked fact must say on its own line why it surfaced');
  ok(background.includes('(recent)'), 'an unmatched fact must be labelled background on its own line');
  ok(!/matched: /.test(background), 'an unmatched fact must not be presented as a match');

  ok(/background only|do not\s+treat/i.test(ctx), 'the model must be told not to answer from background facts');
  ok(/call recall/i.test(ctx), 'the block must admit matching can still miss');
  memory.close();
});

// --- voice + capability ------------------------------------------------------

test('streamed text splits into speakable sentences and keeps the tail', async () => {
  const first = sentences('Sure. I have set that up');
  eq(first.spoken, ['Sure.'], 'a complete sentence should be emitted');
  eq(first.rest, 'I have set that up', 'the incomplete tail should be carried forward');

  const second = sentences(`${first.rest} for tomorrow. Anything else?`);
  eq(second.spoken, ['I have set that up for tomorrow.'], 'the tail should join the next chunk');
  eq(second.rest, 'Anything else?', 'a trailing fragment with no boundary stays buffered');
});

test('an unavailable capability records why, rather than going quiet', async () => {
  const speech = probeSpeechInput();
  if (!speech.available) {
    ok(speech.notes.length > 0, 'an unavailable capability must record why each rung was skipped');
  } else {
    ok(speech.rung, 'an available capability must name the rung that answered');
  }

  const durability = probeReminderDurability();
  eq(durability.durable, false, 'reminder durability must be reported as false, not omitted');
  ok(durability.notes.length >= 2, 'the skipped durable option must be named, not silently dropped');
});

// --- the native bridge -------------------------------------------------------
//
// Read the scope of these carefully. They cover the bridge's *own* branching:
// what it decides, and what it reports, given a platform signal. Not one of
// them calls a Capacitor plugin, because no plugin exists in a browser. The
// native rungs remain unexecuted — a test that stubbed `globalThis.Capacitor`
// and then asserted "reminders are durable" would be asserting about the stub.
// Where a stub is used below it is to drive a guard, and the test name says so.

test('BRIDGE a browser is correctly not a native shell', async () => {
  eq(isNative(), false, 'a plain browser tab must never look native');
  eq(platformName(), 'web', 'and must report itself as web');
});

test('BRIDGE reminders report themselves undurable on the web rung, with a reason', async () => {
  const reminders = await new Reminders().init();
  eq(reminders.durable, false, 'a browser cannot fire a reminder with the tab closed');
  eq(reminders.rung, 'in-page timer', 'and must name the rung that actually answered');
  ok(reminders.notes.length > 0, 'the skipped native rung must record why it was skipped');
  eq(await reminders.schedule({ id: 1, at: Date.now(), text: 'x' }), false, 'scheduling must report that it did not hand off');
});

test('BRIDGE key storage falls back to localStorage and says the key is exposed', async () => {
  const store = new Map();
  const fake = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, v),
    removeItem: (k) => store.delete(k),
  };
  const keys = await new KeyStore({ fallback: fake }).init();
  eq(keys.appPrivate, false, 'a browser tab cannot offer app-private storage');
  ok(
    keys.notes.some((n) => /any script on this page/i.test(n)),
    'the web rung must state the actual exposure rather than implying the key is protected',
  );

  await keys.set('k', 'v');
  eq(await keys.get('k'), 'v', 'the fallback must still round-trip');
  await keys.remove('k');
  eq(await keys.get('k'), null, 'and must actually remove');
});

test('BRIDGE GUARD ONLY: a plugin the shell lacks is refused even when the platform is native', async () => {
  // This drives the guard with a stubbed global. It proves the bridge asks
  // whether the plugin's native half exists rather than assuming it does
  // because the JS package installed — which is exactly how you ship a build
  // that reports reminders as durable and silently drops them. It proves
  // nothing whatsoever about the plugin itself.
  const original = globalThis.Capacitor;
  try {
    globalThis.Capacitor = {
      isNativePlatform: () => true,
      getPlatform: () => 'android',
      isPluginAvailable: () => false,
      // Deliberately a liar: if the bridge ignores `isPluginAvailable` and
      // reaches for this anyway, it gets a plugin that cheerfully reports
      // everything is fine and the session ends up claiming durability it
      // does not have. That is the actual bug, so the stub is built to let it
      // happen rather than to throw and mask it.
      registerPlugin: () => ({
        checkPermissions: async () => ({ display: 'granted' }),
        requestPermissions: async () => ({ display: 'granted' }),
        checkExactNotificationSetting: async () => ({ exact_alarm: 'granted' }),
      }),
    };
    eq(isNative(), true, 'precondition: the stub reports native');
    eq(hasPlugin('LocalNotifications'), false, 'precondition: the stub reports the plugin missing');

    const reminders = await new Reminders().init();
    eq(reminders.durable, false, 'a missing native half must not be reported as durable');
    ok(
      reminders.notes.some((n) => /not present in this build/i.test(n)),
      'and must say the plugin is missing rather than blaming the browser',
    );
  } finally {
    if (original === undefined) delete globalThis.Capacitor;
    else globalThis.Capacitor = original;
  }
});

test('BRIDGE the reminder confirmation tracks the rung that will actually deliver it', async () => {
  const { memory } = await fresh();

  const web = createToolRunner({ memory, session: 'test', remindersDurable: false });
  const webResult = await web('set_reminder', { in_minutes: 5, text: 'bins' });
  ok(/only while this page is open/i.test(webResult.text), 'the web rung must warn the reminder dies with the tab');

  const native = createToolRunner({ memory, session: 'test', remindersDurable: true });
  const nativeResult = await native('set_reminder', { in_minutes: 5, text: 'bins' });
  ok(
    /operating system|even if the app is closed/i.test(nativeResult.text),
    'the durable rung must say so instead of repeating a caveat that is no longer true',
  );
  ok(
    !/only while this page is open/i.test(nativeResult.text),
    'and must not carry the web caveat, which would understate what it can do',
  );
  memory.close();
});

// --- willow: PKCE, URL building, and SSE framing (pure logic, no network) ---

test('WILLOW PKCE challenge is the S256 hash of the verifier, base64url with no padding', async () => {
  const { verifier, challenge, method } = await generatePkce();
  eq(method, 'S256', 'method must be S256');
  ok(/^[A-Za-z0-9_-]+$/.test(verifier), 'verifier must be base64url with no +, / or = padding');
  ok(/^[A-Za-z0-9_-]+$/.test(challenge), 'challenge must be base64url with no +, / or = padding');

  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
  const expected = btoa(String.fromCharCode(...new Uint8Array(digest)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
  eq(challenge, expected, 'challenge must be the base64url SHA-256 digest of the verifier, independently recomputed');
});

test('WILLOW PKCE never reuses a verifier across calls', async () => {
  const a = await generatePkce();
  const b = await generatePkce();
  ok(a.verifier !== b.verifier, 'two calls must not produce the same verifier');
});

test('WILLOW buildAuthorizeUrl carries every parameter the server needs, and nothing it was not given', () => {
  const url = new URL(
    buildAuthorizeUrl({
      authorizationEndpoint: 'http://127.0.0.1:8765/authorize',
      clientId: 'client-123',
      redirectUri: 'http://localhost:8080/index.html',
      challenge: 'chal-value',
      state: 'state-value',
    }),
  );
  eq(url.origin + url.pathname, 'http://127.0.0.1:8765/authorize', 'must redirect to the discovered authorization endpoint');
  eq(url.searchParams.get('response_type'), 'code', 'must request the authorization_code flow, not implicit');
  eq(url.searchParams.get('client_id'), 'client-123');
  eq(url.searchParams.get('redirect_uri'), 'http://localhost:8080/index.html');
  eq(url.searchParams.get('code_challenge'), 'chal-value');
  eq(url.searchParams.get('code_challenge_method'), 'S256');
  eq(url.searchParams.get('state'), 'state-value');
});

test('WILLOW parseSseJsonRpc takes the last complete JSON-RPC message in the stream', () => {
  const text = [
    'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"stale":true}}',
    'data: {"jsonrpc":"2.0","id":1,"result":{"stale":false}}',
  ].join('\n\n');
  const msg = parseSseJsonRpc(text);
  eq(msg.result, { stale: false }, 'must take the final data: block, not the first');
});

test('WILLOW parseSseJsonRpc refuses a stream with no JSON-RPC message rather than returning nothing', () => {
  let threw = false;
  try {
    parseSseJsonRpc('event: ping\n\n');
  } catch {
    threw = true;
  }
  ok(threw, 'a stream with no data: JSON must be an error, not a silent null result the caller mistakes for an empty answer');
});

// --- willow: the tool-runner mapping onto a fake session --------------------
//
// These stand in a plain object with `connected` and `callTool`, not a real
// WillowSession — the thing worth testing here is tools.js's own mapping from
// a willow-mcp result onto {data, text, isError}, which is real logic in this
// repo. Whether a real WillowSession ever reaches that state is a live-network
// question this suite cannot answer; see the file-level note above.

test('WILLOW willow_whoami reports disconnected honestly before any sign-in', async () => {
  const { memory } = await fresh();
  const run = createToolRunner({ memory, session: 'test', willow: null });
  const result = await run('willow_whoami', {});
  eq(result.isError, false, 'having no willow-mcp connection is a known state, not a tool failure');
  ok(/not connected/i.test(result.text), 'must say it is not connected rather than throwing or staying silent');
  memory.close();
});

test('WILLOW a write tool refuses locally when disconnected, the same way a read tool does', async () => {
  const { memory } = await fresh();
  const run = createToolRunner({ memory, session: 'test', willow: null });
  const result = await run('willow_dispatch_send', { to_app: 'hanuman', assignment_md: 'do the thing' });
  ok(/not connected/i.test(result.text), 'willow_dispatch_send must not attempt a call with nothing to call');
  memory.close();
});

test('WILLOW a willow-mcp denial surfaces as an error to the model, verbatim, not swallowed', async () => {
  const { memory } = await fresh();
  const fakeWillow = {
    connected: true,
    async callTool(name) {
      eq(name, 'agent_clear', 'must call the underlying willow-mcp tool name, not the local jarvis-side wrapper name');
      return { text: '{"error":"signed in but not yet bound"}', data: { error: 'signed in but not yet bound' }, isError: false };
    },
  };
  const run = createToolRunner({ memory, session: 'test', willow: fakeWillow });
  const result = await run('willow_agent_clear', { target_app: 'hanuman', dispatch_id: 'd-1' });
  eq(result.isError, true, 'a {error: ...} result from willow-mcp is a denial and must be reported as one');
  ok(result.text.includes('signed in but not yet bound'), "the server's own denial reason must reach the model unparaphrased");
  memory.close();
});

test('WILLOW a successful willow-mcp read passes its filters through and surfaces the data', async () => {
  const { memory } = await fresh();
  const fakeWillow = {
    connected: true,
    async callTool(name, args) {
      eq(name, 'dispatch_list', 'wrong underlying tool called');
      eq(args.status, 'pending', 'a filter given to willow_dispatch_list must reach the underlying call');
      return { text: '{"dispatches":[],"total":0}', data: { dispatches: [], total: 0 }, isError: false };
    },
  };
  const run = createToolRunner({ memory, session: 'test', willow: fakeWillow });
  const result = await run('willow_dispatch_list', { status: 'pending' });
  eq(result.isError, false, 'a clean read must not be reported as an error');
  eq(result.data.total, 0, 'the underlying result data must reach the caller, not just its text');
  memory.close();
});

// --- runner ------------------------------------------------------------------

export async function runAll() {
  const results = [];
  for (const { name, fn } of tests) {
    const started = performance.now();
    try {
      // eslint-disable-next-line no-await-in-loop
      await fn();
      results.push({ name, pass: true, ms: Math.round(performance.now() - started) });
    } catch (err) {
      results.push({
        name,
        pass: false,
        ms: Math.round(performance.now() - started),
        error: err instanceof Assert ? err.message : `${err.name}: ${err.message}`,
      });
    }
  }
  return results;
}

export const testNames = tests.map((t) => t.name);
