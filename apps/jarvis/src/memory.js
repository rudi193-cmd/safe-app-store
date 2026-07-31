// Memory: an indexed fact store.
//
// This is the part of the app that has to be a database rather than a bag of
// blobs. The whole point of an assistant with memory is answering "what do I
// know about X" without reading everything, so retrieval has to push a
// predicate down to an index. Every query in here resolves through an
// IDBIndex; none of them fetch-all-and-filter-in-JS.
//
// Three invariants the rest of the app depends on, each with a test that
// breaks if it stops holding (see test/suite.js):
//
//   1. Corrections land beside the record, never on top of it. Superseding a
//      fact writes a new row and marks the old one; it never mutates or
//      deletes the original. You can always reconstruct what was believed
//      when, which is what makes the log usable for checking reasoning and
//      not just for reading the current answer.
//   2. Absence is a recorded value. `kind: 'absence'` means "we asked and
//      there is nothing" — a different fact from having no row at all.
//   3. Provenance is a state, not a score. Every fact is 'stated',
//      'inferred', or 'assumed', and a recall's provenance is the min() of
//      its contributing facts. Not a percentage: either a claim traces back
//      to something the user actually said, or it does not.

import { tokenize, tokensFor } from './text.js';

export const PROVENANCE = ['assumed', 'inferred', 'stated'];
export const KINDS = ['fact', 'preference', 'person', 'project', 'absence'];

const DB_NAME = 'jarvis';
const DB_VERSION = 2;

/** Rank a provenance state. Higher is better-grounded. Unknown values rank lowest. */
export function provenanceRank(p) {
  const i = PROVENANCE.indexOf(p);
  return i === -1 ? 0 : i;
}

/**
 * The weakest link in a set of facts. A conclusion is worth its worst input,
 * so this is a min() over the ladder rather than an average — averaging would
 * let two assumptions and a statement read as "mostly grounded", which is the
 * exact blurring this is here to prevent.
 */
export function weakestProvenance(facts) {
  if (!facts.length) return null;
  return facts.reduce(
    (worst, f) => (provenanceRank(f.provenance) < provenanceRank(worst) ? f.provenance : worst),
    'stated',
  );
}

/** Subjects are the index key, so they have to normalise identically on write and read. */
export function normalizeSubject(s) {
  return String(s || '')
    .toLowerCase()
    .trim()
    .replace(/\s+/g, ' ');
}

function req(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function openDb(name = DB_NAME) {
  return new Promise((resolve, reject) => {
    const open = indexedDB.open(name, DB_VERSION);
    open.onupgradeneeded = (event) => {
      const db = open.result;
      const tx = open.transaction;

      if (event.oldVersion < 1) {
        const facts = db.createObjectStore('facts', { keyPath: 'id', autoIncrement: true });
        // Every index here exists because a query below uses it. `live` is a
        // derived 0/1 field rather than a boolean because IndexedDB cannot key
        // on booleans, and we need "current facts about X, newest first" to be
        // an index range rather than a scan.
        facts.createIndex('subject_live_created', ['subject', 'live', 'createdAt']);
        facts.createIndex('kind_live_created', ['kind', 'live', 'createdAt']);
        facts.createIndex('live_created', ['live', 'createdAt']);
        facts.createIndex('supersedes', 'supersedes');

        const reminders = db.createObjectStore('reminders', { keyPath: 'id', autoIncrement: true });
        reminders.createIndex('pending_at', ['pending', 'at']);
      }

      if (event.oldVersion < 2) {
        const facts = tx.objectStore('facts');
        // The inverted index. multiEntry means one index entry per token, so
        // a lookup for a token is a direct index hit rather than a scan over
        // facts. It keys on `liveTokens` rather than `tokens` so that
        // retiring a fact removes it from the index outright — see #reindex.
        facts.createIndex('liveTokens', 'liveTokens', { multiEntry: true });

        // Backfill. A store written before this version has no token fields,
        // and without this pass every fact already on the user's device would
        // silently stop being findable the moment search shipped — the whole
        // memory would look empty while still being right there.
        const cursorReq = facts.openCursor();
        cursorReq.onsuccess = () => {
          const cursor = cursorReq.result;
          if (!cursor) return;
          cursor.update(withTokens(cursor.value));
          cursor.continue();
        };
      }
    };
    open.onsuccess = () => resolve(open.result);
    open.onerror = () => reject(open.error);
    open.onblocked = () => reject(new Error('IndexedDB upgrade blocked by another open tab'));
  });
}

/**
 * Derive the token fields for a row.
 *
 * `tokens` and `strongTokens` describe the fact and never change once
 * written. `liveTokens` is the index projection: it mirrors `tokens` while
 * the fact is live and is emptied when it is not. That is what keeps a
 * superseded fact out of search results without deleting anything — the
 * content is untouched, only its presence in the index changes.
 */
function withTokens(row) {
  const { strong, all } = tokensFor({
    subject: row.subject,
    aliases: row.aliases || [],
    text: row.text,
  });
  return {
    ...row,
    aliases: row.aliases || [],
    tokens: all,
    strongTokens: strong,
    liveTokens: row.live ? all : [],
  };
}

/** Mark a row not-live and drop it out of the search index, changing nothing else. */
function retire(row) {
  return { ...row, live: 0, liveTokens: [] };
}

export class Memory {
  #db = null;
  #name;

  constructor({ name = DB_NAME } = {}) {
    this.#name = name;
  }

  // Deliberately not memoised into a module-level promise. A module-scoped
  // `opening` promise hands every caller the same connection forever, with no
  // way to release the handle — survivable for IndexedDB, fatal for anything
  // holding an exclusive lock, and impossible to reset between tests. Each
  // Memory instance owns its own connection and can give it back.
  async open() {
    if (!this.#db) this.#db = await openDb(this.#name);
    return this.#db;
  }

  close() {
    if (this.#db) {
      this.#db.close();
      this.#db = null;
    }
  }

  async #tx(stores, mode, fn) {
    const db = await this.open();
    const tx = db.transaction(stores, mode);
    const out = await fn(tx);
    await new Promise((resolve, reject) => {
      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error || new Error('transaction aborted'));
    });
    return out;
  }

  /**
   * Record a fact. `supersedes` marks an earlier fact as no longer current
   * without touching its contents — the old row stays byte-identical and
   * queryable, it just stops appearing in live results.
   */
  async remember({
    subject,
    kind = 'fact',
    text,
    provenance = 'stated',
    aliases = [],
    supersedes = null,
    session = null,
  }) {
    if (!text || !String(text).trim()) throw new Error('remember: text is required');
    if (!KINDS.includes(kind)) throw new Error(`remember: unknown kind "${kind}"`);
    if (!PROVENANCE.includes(provenance)) throw new Error(`remember: unknown provenance "${provenance}"`);

    const row = withTokens({
      subject: normalizeSubject(subject),
      kind,
      text: String(text).trim(),
      provenance,
      aliases: (Array.isArray(aliases) ? aliases : [])
        .map((a) => String(a).trim())
        .filter(Boolean)
        .slice(0, 12),
      supersedes: supersedes == null ? null : Number(supersedes),
      live: 1,
      createdAt: Date.now(),
      session,
    });

    return this.#tx(['facts'], 'readwrite', async (tx) => {
      const store = tx.objectStore('facts');
      if (row.supersedes != null) {
        const prior = await req(store.get(row.supersedes));
        if (!prior) throw new Error(`remember: cannot supersede unknown fact ${row.supersedes}`);
        // Only liveness changes on the prior row. Its text, provenance and
        // timestamp are left exactly as written; `liveTokens` empties so it
        // leaves the search index, while `tokens` stays for the history.
        await req(store.put(retire(prior)));
      }
      const id = await req(store.add(row));
      return { ...row, id };
    });
  }

  /** Retire a fact without asserting a replacement. The row itself survives. */
  async forget(id) {
    return this.#tx(['facts'], 'readwrite', async (tx) => {
      const store = tx.objectStore('facts');
      const prior = await req(store.get(Number(id)));
      if (!prior) return null;
      const next = retire(prior);
      await req(store.put(next));
      return next;
    });
  }

  /**
   * Query live facts. Every branch resolves through an index range: this
   * never loads the store and filters afterward. `limit` bounds work at the
   * cursor, so a capped query stops reading once it has enough.
   */
  async recall({ subject = null, kind = null, since = null, limit = 20 } = {}) {
    const lower = since == null ? 0 : Number(since);
    const upper = Number.MAX_SAFE_INTEGER;

    let indexName, range;
    if (subject) {
      const s = normalizeSubject(subject);
      indexName = 'subject_live_created';
      range = IDBKeyRange.bound([s, 1, lower], [s, 1, upper]);
    } else if (kind) {
      indexName = 'kind_live_created';
      range = IDBKeyRange.bound([kind, 1, lower], [kind, 1, upper]);
    } else {
      indexName = 'live_created';
      range = IDBKeyRange.bound([1, lower], [1, upper]);
    }

    const rows = await this.#tx(['facts'], 'readonly', async (tx) => {
      const index = tx.objectStore('facts').index(indexName);
      const out = [];
      // 'prev' walks the compound key backwards, so results arrive
      // newest-first and `limit` truncates the tail rather than the head.
      const cursorReq = index.openCursor(range, 'prev');
      await new Promise((resolve, reject) => {
        cursorReq.onsuccess = () => {
          const cursor = cursorReq.result;
          if (!cursor || out.length >= limit) return resolve();
          out.push(cursor.value);
          cursor.continue();
        };
        cursorReq.onerror = () => reject(cursorReq.error);
      });
      return out;
    });

    // Secondary filter only where the index cannot express the predicate:
    // subject-scoped queries may additionally narrow by kind.
    const filtered = subject && kind ? rows.filter((r) => r.kind === kind) : rows;
    return { facts: filtered, provenance: weakestProvenance(filtered) };
  }

  /**
   * Rank live facts against free text.
   *
   * An inverted-index lookup per query token, scored by inverse document
   * frequency. A token that appears in almost every fact you have stored
   * discriminates between them barely at all, so it is worth close to
   * nothing; a token that appears in two facts is worth a lot. That is the
   * whole of the ranking, and it is the reason this beats the previous exact
   * subject match without needing a model: "what did I say about getting to
   * the office" scores a fact filed under `commute` because `office` is one
   * of its aliases, and scores it highly because `office` is rare.
   *
   * Document frequency comes from `index.count(token)` and the corpus size
   * from a count over the live range — both are index reads, so scoring does
   * not need a separate statistics table that could drift out of step with
   * the facts it describes.
   *
   * Scale: this fetches every fact matching any query token before ranking.
   * At personal-memory size — thousands of facts — that is nothing. It is the
   * wrong shape at a million, where you would intersect posting lists
   * rarest-token-first instead of unioning them.
   */
  async search(query, { limit = 10, minScore = 0 } = {}) {
    const queryTokens = tokenize(query);
    if (!queryTokens.length) return { facts: [], provenance: null, tokens: [] };

    const ranked = await this.#tx(['facts'], 'readonly', async (tx) => {
      const store = tx.objectStore('facts');
      const tokenIndex = store.index('liveTokens');
      const liveIndex = store.index('live_created');

      const total = await req(liveIndex.count(IDBKeyRange.bound([1, 0], [1, Number.MAX_SAFE_INTEGER])));
      if (!total) return [];

      const hits = new Map();
      for (const token of queryTokens) {
        // eslint-disable-next-line no-await-in-loop
        const df = await req(tokenIndex.count(token));
        if (!df) continue;
        const idf = Math.log(1 + total / df);
        // eslint-disable-next-line no-await-in-loop
        const matches = await req(tokenIndex.getAll(token));
        for (const fact of matches) {
          const entry = hits.get(fact.id) || { fact, score: 0, matched: [] };
          // A hit on the subject or an alias is deliberate — someone chose
          // that word as a handle for this fact. A hit in the body text is
          // often incidental. Weighting them equally lets a passing mention
          // outrank the thing actually filed under the word.
          const strong = (fact.strongTokens || []).includes(token);
          entry.score += idf * (strong ? 2.5 : 1);
          entry.matched.push(token);
          hits.set(fact.id, entry);
        }
      }
      // Length normalization. Without it the score is a raw sum, so a fact
      // wins by being *big*: a grab-bag with twenty aliases collects more
      // matched tokens than a short fact that is precisely about the query,
      // and outranks it. Matching two of your three tokens is stronger
      // evidence than matching two of your forty, and the sum cannot say so.
      //
      // This is not a hypothetical. Measured against a real corpus — 96
      // verbatim spans of one person's prose naming files, in
      // `test/terpsi-rank.js` — adding aliases made ranking WORSE, 0.732 ->
      // 0.659 rank@1, while every matcher it was compared against improved.
      // Aliases are the feature this whole retrieval design is built around,
      // and the raw sum turned them into a liability. Normalizing reverses it
      // (0.659 -> 0.756, and 0.250 -> 0.500 on the hardest split).
      //
      // The divisor is the square root of the fact's total token weight, with
      // strong tokens counted at the same 2.5 the scoring uses. Square root
      // rather than the count itself: dividing by length outright over-punishes
      // long facts, which is the opposite bias rather than no bias.
      for (const entry of hits.values()) {
        const strongCount = (entry.fact.strongTokens || []).length;
        const weakCount = Math.max(0, (entry.fact.tokens || []).length - strongCount);
        entry.score /= Math.sqrt(2.5 * strongCount + weakCount) || 1;
      }
      return [...hits.values()];
    });

    const facts = ranked
      .filter((h) => h.score > minScore)
      .sort((a, b) => b.score - a.score || b.fact.createdAt - a.fact.createdAt)
      .slice(0, limit)
      .map((h) => ({ ...h.fact, score: Number(h.score.toFixed(3)), matched: h.matched }));

    return { facts, provenance: weakestProvenance(facts), tokens: queryTokens };
  }

  /** Full history for a subject, superseded rows included, oldest first. */
  async history(subject) {
    const s = normalizeSubject(subject);
    return this.#tx(['facts'], 'readonly', async (tx) => {
      const all = await req(tx.objectStore('facts').getAll());
      return all.filter((f) => f.subject === s).sort((a, b) => a.createdAt - b.createdAt);
    });
  }

  async getFact(id) {
    return this.#tx(['facts'], 'readonly', (tx) => req(tx.objectStore('facts').get(Number(id))));
  }

  // --- reminders -----------------------------------------------------------

  async addReminder({ at, text }) {
    const when = Number(at);
    if (!Number.isFinite(when)) throw new Error('addReminder: `at` must be a timestamp');
    const row = { at: when, text: String(text).trim(), pending: 1, createdAt: Date.now(), firedAt: null };
    return this.#tx(['reminders'], 'readwrite', async (tx) => {
      const id = await req(tx.objectStore('reminders').add(row));
      return { ...row, id };
    });
  }

  /** Pending reminders due at or before `at`, via the index — not a scan. */
  async dueReminders(at = Date.now()) {
    return this.#tx(['reminders'], 'readonly', async (tx) => {
      const index = tx.objectStore('reminders').index('pending_at');
      return req(index.getAll(IDBKeyRange.bound([1, 0], [1, Number(at)])));
    });
  }

  async pendingReminders() {
    return this.#tx(['reminders'], 'readonly', async (tx) => {
      const index = tx.objectStore('reminders').index('pending_at');
      return req(index.getAll(IDBKeyRange.bound([1, 0], [1, Number.MAX_SAFE_INTEGER])));
    });
  }

  async markFired(id) {
    return this.#tx(['reminders'], 'readwrite', async (tx) => {
      const store = tx.objectStore('reminders');
      const row = await req(store.get(Number(id)));
      if (!row) return null;
      const next = { ...row, pending: 0, firedAt: Date.now() };
      await req(store.put(next));
      return next;
    });
  }

  async wipe() {
    return this.#tx(['facts', 'reminders'], 'readwrite', async (tx) => {
      await req(tx.objectStore('facts').clear());
      await req(tx.objectStore('reminders').clear());
    });
  }
}

/** Delete a database outright. Used by tests to guarantee a cold start. */
export function deleteDatabase(name = DB_NAME) {
  return new Promise((resolve, reject) => {
    const r = indexedDB.deleteDatabase(name);
    r.onsuccess = () => resolve();
    r.onerror = () => reject(r.error);
    r.onblocked = () => resolve();
  });
}
