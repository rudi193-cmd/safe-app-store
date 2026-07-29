/**
 * The owner protocol, over a real MessagePort.
 *
 * This is as much of the SharedWorker story as Node can execute. A
 * `MessageChannel` stands in for the port a tab gets from `SharedWorker.port`:
 * one end is served by `serve()` against a real SQLite-WASM connection, the
 * other is wrapped in `RemoteConnection` and handed to a `Store`. Everything
 * crossing the wire is structure-cloned by Node exactly as a browser would clone
 * it, so a value that would not survive the trip fails here.
 *
 * What this does NOT test, and no headless runner can:
 *
 *   · that a SharedWorker is a single instance per origin
 *   · `navigator.locks` election between two contexts
 *   · `pauseVfs()` / `unpauseVfs()` handing the OPFS SAH pool over
 *
 * Those need a browser. `test/browser.html` drives them manually; the README
 * records them as unverified rather than pretending this file covers them.
 *
 * Usage: node test/owner.mjs [--verbose]
 */

import { MessageChannel } from 'node:worker_threads';

import {
  Band,
  GrantState,
  RemoteConnection,
  Store,
  announce,
  handleRequest,
  openMemory,
  principal,
  serve,
} from '../dist/index.js';

import { quiet } from './quiet.mjs';

const VERBOSE = process.argv.includes('--verbose');
const api = await sqliteApi();
quiet(api);

async function sqliteApi() {
  const { sqlite3 } = await import('../dist/index.js');
  return sqlite3();
}

let passed = 0;
const failures = [];

async function test(name, fn) {
  try {
    await fn();
    passed += 1;
    if (VERBOSE) console.log(`ok    ${name}`);
  } catch (error) {
    failures.push(name);
    console.error(`FAIL  ${name}\n      ${error.message.split('\n').join('\n      ')}`);
  }
}

function eq(got, want, message) {
  const g = JSON.stringify(got);
  const w = JSON.stringify(want);
  if (g !== w) throw new Error(`${message ?? 'not equal'}\n    got  ${g}\n    want ${w}`);
}

function assert(condition, message) {
  if (!condition) throw new Error(message ?? 'assertion failed');
}

/** A served connection plus the client that talks to it. */
async function wired() {
  const conn = await openMemory(api);
  const channel = new MessageChannel();
  let live = conn;
  serve(channel.port2, () => live);
  const remote = new RemoteConnection(channel.port1);
  return {
    conn,
    remote,
    channel,
    detach: () => {
      live = null;
    },
    close: () => {
      channel.port1.close();
      channel.port2.close();
    },
  };
}

/** The gate fixture, built through whichever connection is passed. */
async function seed(store) {
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
}

// ---------------------------------------------------------------------------

await test('migrations run across the port', async () => {
  const w = await wired();
  const store = await Store.open(w.remote);
  const names = (await w.conn.all('SELECT name FROM schema_migrations ORDER BY name')).map(
    (r) => String(r[0]),
  );
  eq(names, ['001_facts_and_grants']);
  assert(store, 'no store');
  w.close();
});

await test('the same store semantics hold over the wire', async () => {
  const w = await wired();
  const store = await Store.open(w.remote);
  await seed(store);

  const leader = principal('leader');
  eq(await store.count(leader), 3, 'count over the port');
  eq(await store.count(principal('stranger')), 0, 'stranger over the port');
  eq(await store.subjects(leader), ['visible-member'], 'subjects over the port');
  eq((await store.visible(leader)).map((r) => r.payload), ['visible 0', 'visible 1', 'visible 2']);
  eq(
    await store.count(leader, {
      where: 'facts.subject_id = :s',
      params: { s: 'hidden-member' },
    }),
    0,
    'hidden subject over the port',
  );
  w.close();
});

await test('a COUNT crosses the port as a number, not as rows', async () => {
  // The whole point of putting the predicate on the calling side: the message
  // that comes back for a count carries one integer. If the owner were fetching
  // and the client counting, the hidden rows would be in this array.
  const w = await wired();
  const store = await Store.open(w.remote);
  await seed(store);

  const seen = [];
  const port = w.channel.port1;
  const original = port.postMessage.bind(port);
  const responses = [];
  const listener = (event) => responses.push(event.data);
  port.addEventListener('message', listener);
  port.postMessage = (m) => {
    seen.push(m);
    return original(m);
  };
  await store.count(principal('leader'));
  await new Promise((r) => setTimeout(r, 20));

  const counts = responses.filter((m) => m && m.ok === true && Array.isArray(m.value));
  assert(counts.length >= 1, 'no response observed');
  const value = counts[counts.length - 1].value;
  eq(value.length, 1, `a count response carried ${value.length} columns`);
  eq(Number(value[0]), 3);
  const sent = seen.filter((m) => m && m.op);
  eq(sent.length, 1, `count sent ${sent.length} messages`);
  assert(/COUNT\(\*\)/i.test(sent[0].sql), `not a COUNT(*): ${sent[0].sql}`);
  w.close();
});

await test('a constraint violation crosses the port as a rejection', async () => {
  const w = await wired();
  const store = await Store.open(w.remote);
  let error = null;
  try {
    await store.recordFact('p', Band.ROSTER, '   ');
  } catch (e) {
    error = e;
  }
  assert(error, 'a blank source was accepted over the port');
  assert(/CHECK|constraint/i.test(error.message), `unexpected message: ${error.message}`);
  assert(typeof error.resultCode === 'number', 'the SQLite result code did not survive the trip');
  w.close();
});

await test('an unavailable owner refuses rather than hangs', async () => {
  const w = await wired();
  const store = await Store.open(w.remote);
  w.detach();
  let error = null;
  try {
    await store.count(principal('leader'));
  } catch (e) {
    error = e;
  }
  assert(error, 'a request against a detached owner resolved');
  eq(error.name, 'OwnerUnavailable');
  w.close();
});

await test('responses are matched to requests by id', async () => {
  // Two overlapping calls with different answers. If ids were ignored, or the
  // owner interleaved them, one of these gets the other's rows.
  const w = await wired();
  const store = await Store.open(w.remote);
  await seed(store);
  const [a, b, c] = await Promise.all([
    store.count(principal('leader')),
    store.count(principal('stranger')),
    store.count(principal('hidden-member')),
  ]);
  eq([a, b, c], [3, 0, 7]);
  w.close();
});

await test('requests are served in the order they were issued', async () => {
  // oo1 is synchronous inside the owner, and two overlapping explicit
  // transactions from two tabs would be a correctness bug rather than a
  // throughput opportunity. So the owner chains requests; a BEGIN issued before
  // an INSERT must reach SQLite before it, even though both were posted in the
  // same tick.
  const w = await wired();
  await Store.open(w.remote);
  const order = [];
  await Promise.all([
    w.remote.begin().then(() => order.push('begin')),
    w.remote
      .run('INSERT INTO facts(subject_id, band, source) VALUES (:s, :b, :src)', {
        s: 'x',
        b: Band.ROSTER,
        src: 'source',
      })
      .then(() => order.push('insert')),
    w.remote.commit().then(() => order.push('commit')),
    w.remote.get('SELECT COUNT(*) FROM facts').then((r) => order.push(`count=${r[0]}`)),
  ]);
  eq(order, ['begin', 'insert', 'commit', 'count=1'], 'the owner reordered the queue');
  // And the insert really did land inside the transaction that was open at the
  // time: rolling back afterwards must not undo it.
  await w.remote.rollback();
  eq(Number((await w.conn.get('SELECT COUNT(*) FROM facts'))[0]), 1);
  w.close();
});

await test('notices reach the client and are not mistaken for responses', async () => {
  const w = await wired();
  const received = [];
  w.remote.onNotice = (n) => received.push(n);
  announce([w.channel.port2], { notice: 'ready', vfs: 'memory', durable: false, notes: ['x'] });
  await new Promise((r) => setTimeout(r, 20));
  eq(received.length, 1);
  eq(received[0].notice, 'ready');
  eq(received[0].durable, false);
  eq(w.remote.status.vfs, 'memory');
  w.close();
});

await test('handleRequest reports an unknown op instead of guessing', async () => {
  const conn = await openMemory(api);
  const res = await handleRequest(conn, { v: 1, id: 7, op: 'drop-everything' });
  eq(res.ok, false);
  eq(res.id, 7);
  assert(/unknown op/.test(res.error.message), res.error.message);
  await conn.close();
});

await test('a malformed message is ignored rather than dispatched', async () => {
  const w = await wired();
  const store = await Store.open(w.remote);
  await seed(store);
  w.channel.port1.postMessage({ nonsense: true });
  w.channel.port1.postMessage(null);
  await new Promise((r) => setTimeout(r, 20));
  eq(await store.count(principal('leader')), 3, 'the owner was disturbed by junk');
  w.close();
});

// ---------------------------------------------------------------------------

console.log(`\n${passed}/${passed + failures.length} owner protocol tests passed`);
if (failures.length) {
  console.error(`${failures.length} failed: ${failures.join(', ')}`);
  process.exit(1);
}
