# marching-arts / browser — the browser half of P1

> **Status: level with the core.** This port implements P1 *and* P2 — migrations
> 002, 003 and 004, and the guardian clause inside the grant-lookup predicate.
> `npm test` regenerates the reference from `../marching_arts/` in the working
> tree on every run and reports **27,534 comparisons, 0 disagreements**. It is
> wired into `.github/workflows/store-ci.yml` as the `browser-resolver` job, and
> that job is in the aggregate `test` job's `needs:`, so branch protection blocks
> on it. See *The drift gate* below for what that gate looked like while it was
> red, which is the more useful half of the story.

The authorization resolver, running in-browser on SQLite-WASM, and a differential
suite that holds it to the Python core in [`../marching_arts/`](../marching_arts).

The rules are *decided* in Python. This is a second implementation of the same
rules, and a second implementation is a liability unless something mechanical
keeps the two identical. That something is [`test/`](test): a generator that runs
the Python resolver over a randomised corpus and dumps everything it produced,
and a comparator that replays the identical corpus through this port.

**27,534 comparisons, 0 disagreements.** Five deliberate bugs, all caught. The
numbers and what they do and do not cover are below.

---

## What is here

| File | What it is |
| --- | --- |
| `src/rules.ts` | The rules→SQL `WHERE` compiler. `compile_rules` reproduced exactly. |
| `src/policy.ts` | Who may see what, including the guardian clause. Every SQL fragment byte-compared against `policy.py`. |
| `src/bands.ts` | L0–L6, `DERIVE_AT`, `NEVER_SERVED`. |
| `src/schema.ts` | Migrations 001–004, DDL byte-identical to `schema.py`. |
| `src/store.ts` | Authorized reads, plus people and guardianships. `count` is a SQL `COUNT(*)`; there is no array to take the length of. |
| `src/connection.ts` | The one seam: an async `Connection` the store is written against. |
| `src/sqlite.ts` | `Connection` over `sqlite3.oo1.DB`. |
| `src/open.ts` | The VFS ladder: `opfs-sahpool`, then memory, with every rung reported. |
| `src/sharedworker.ts` | The owner. One context holds the database; the rest attach ports. |
| `src/owner/` | Election (Web Locks), the wire protocol, the server and client halves. |

### The compiler, and the three things about it that are load-bearing

```
(allow₁ OR allow₂ OR …) AND NOT (deny₁ OR deny₂ OR …)
```

1. **An empty allow set compiles to `0`, never `1`.** A principal the policy does
   not recognise sees nothing, and reaches that state by rule rather than by
   exception. `ALLOW_ALL` exists to be named and is never emitted by the
   compiler.
2. **Parameters are scoped per rule.** `{viewer}` in rule 3 renders as
   `:r3_viewer`, so two rules may both use a parameter called `viewer`. When
   there are no allows the deny parameters are dropped along with the deny terms,
   exactly as `rules.py` drops them by returning a fresh `{}`.
3. **The parentheses around the joined denies.** They are what make this a
   negation of the *union* rather than of the first term. Drop them and only the
   first deny binds; the rest quietly stop applying, the SQL stays valid, and
   nothing raises.

### The guardian clause, and what is deliberately not here

P2's read-path change is one clause, nested *inside* the correlated grant lookup:

```sql
AND (g.granted_via = :r1_member OR EXISTS (SELECT 1 FROM people p
     WHERE p.person_id = g.subject_id
       AND date('now') < date(p.birthdate, '+18 years')))
```

Guardian-derived authority is honoured only while the subject is still a minor.
Nothing is scheduled and nothing has to remember: the day the member turns
eighteen the guardian's grant stops resolving, in a tab that has been open since
before the birthday exactly as in a fresh one, because the predicate re-asks per
row on every read. It is emitted by `Policy.stillAMinor`, which is the same
single definition `policy.py` keeps for the same reason — a guardian-expiry check
phrased two slightly different ways in two places is the shape of bug where
access expires in the resolver but not in the thing that decides who may seal.

`MAJORITY_AGE` lives in `policy.ts` and is imported by `schema.ts`, mirroring the
Python, so the read path and the write path cannot drift apart on the one number
that decides whose consent counts.

**What is not here: the `subject_consent` core.** That library is Python-only and
stays that way. What is ported is the *schema* its rows land in — `consent_chain`,
`consent_anchor`, and the triggers of migrations 002–004 — so a database a browser
creates is the same database, byte for byte, as one Python creates, and the
guardian rule holds over the chain in either. The resolver reads `grants`; it
never walks a chain, and there is no chain logic in `src/`.

Migration 004 is worth a line on its own. 003's trigger matched
`new.chain = 'consent'` exactly, so partitioning the chain per subject as
`consent/<subject_hash>` silently stopped it firing and a minor could consent for
themselves with nothing raised. 004 replaces it with a match on the partitions
*and* the bare name. `gate.mjs` checks both halves here, because a ported trigger
that does not fire looks exactly like a ported trigger that does.

### The owner

`opfs-sahpool` takes exclusive `FileSystemSyncAccessHandle`s over its pool files.
A second context that tries to install it gets an exception, not a queue. So
single-ownership is not a nicety:

- A **SharedWorker** gives it by construction. One script URL, one instance per
  origin, every tab attaches a port to the same one. Where SharedWorker exists,
  the browser has already elected.
- A **Web Lock** covers where it does not — Chrome on Android and several
  WebViews ship no SharedWorker, so each tab runs a dedicated worker and the lock
  is the whole mechanism. It also covers the window during a worker restart when
  two instances briefly coexist.
- **Handoff** is explicit: the outgoing owner calls `pauseVfs()`, releasing every
  handle, *then* releases the lock; the incoming owner acquires it and calls
  `unpauseVfs()`. The owner detects a challenger by polling `navigator.locks
  .query()` for a pending request, because there is no event for one.

Nothing crossing the port is a question about a principal. The predicate is
compiled on the calling side and travels *with* the statement, so the owner never
knows what a query was about and cannot accidentally answer a wider one.

---

## Running it

```sh
npm install
npm run build          # tsc -> dist/
npm test               # gate + owner protocol + differential
npm run test:mutation  # break it on purpose, confirm the suite notices
```

`npm test` **regenerates** `test/reference.json` on every run, from the working
tree, and fails if it cannot. It does not reuse what is on disk, and that is not
an optimisation left undone — generating only when the file was absent made this
a gate that stopped being one the moment the core moved. It did exactly that
here: a reference written before P2 reported *27,528 comparisons and 0
disagreements* while the port was missing the entire guardian clause. A green run
against yesterday's core is worse than no run, because it is indistinguishable
from a real one. Regeneration is a couple of seconds of stdlib Python. Do not
reintroduce the cache.

`gen_reference.py` is stdlib-only, so any Python that can run the app's own suite
can produce it. The sibling harness in `apps/field-acoustics/kernel` reports its
differential as *skipped* when its reference is absent, which is honest there
because it needs numpy and scipy. A skip here would mean the browser resolver
shipped with nothing holding it to the semantics it is a copy of, so this one
refuses.

### Which Python is "the" Python

`gen_reference.py` reads `marching_arts/` from the **working tree** by default.
That is the gate: when the core changes and the port does not, the suite fails.
It warns on stderr if the working tree is dirty. `--rev REV` pins to a git
revision instead — a deliberate act, and the revision is recorded in the output
file so a reader can always tell what a reference was generated from.

---

## The numbers

Reference generated against `marching_arts/` in the working tree — the default,
and the only mode CI uses.

```
corpus     14 worlds · 130 principal cases · 7,130 store queries
           249 compiler cases over a 24-row scratch table
           8 schema rejections, each confirmed refused by Python first

tier         checks   result
constants        15   ok      band integers, DERIVE_AT, NEVER_SERVED,
                              DENY_ALL, SORTABLE, and all four migrations'
                              DDL byte-for-byte
compiler        996   ok      predicate text, parameters, explain(), and the
                              rows each predicate actually selects
policy          780   ok      every rule fragment as SQL text, per principal
store        25,735   ok      the adversarial battery, per (world, principal)
schema            8   ok      the writes that must be refused

27,534 comparisons, 0 disagreements
```

Plus 43 gate tests and 10 owner-protocol tests, which say what *correct* is
independently — two implementations can agree while both being wrong.

### The drift gate, demonstrated

This is kept because it is the useful half. While P1 was being built,
`marching_arts/` was being extended in the working tree by another pair of hands:
P2 consent — a `people` table, guardianships, a hash-chained consent log,
migration 002, and a `granted_via` clause inside the grant subquery. That is what
the generator's default mode is for. Pointed at the working tree, the P1-era port
reported:

```
constants     15 checks   FAIL 7       migration count 4, port has 1;
                                       002/003/004 missing
compiler     996 checks   ok           compile_rules is unchanged — correctly unaffected
policy       780 checks   FAIL 520     the grant fragment gained a guardian clause
store     25,735 checks   FAIL 14,260
```

14,787 disagreements, located in seconds, and the tiering did its job: the
compiler tier stayed green because the compiler did not change, so the finding
pointed at the policy rather than at everything at once.

That is now closed. `schema.ts` carries migrations 001–004 with the DDL byte-for-
byte — including the double spaces and comment art that are artefacts of Python's
implicit string concatenation, reproduced deliberately; the only edits are the
interpolations standing where `.format()` fields stood and the escaped backticks
a template literal requires, neither of which changes a byte of the result.
`policy.ts` carries the guardian clause, `MAJORITY_AGE` and `GrantVia`, and
`store.ts` carries `granted_via`/`requested_by` on the grant write plus
`recordPerson`, `recordGuardianship`, `isMinor` and `guardiansOf`. `bands.ts` and
`rules.ts` needed nothing — checked rather than assumed; `compile_rules` was
untouched by P2, which is why the compiler tier stayed green throughout.

The store battery per principal covers, from `tests/test_gate.py`: hidden rows
under `COUNT`, a caller filter that tries to widen (`1 = 1 OR 1 = 1`), a filter
targeting a hidden subject, payload probing (present vs absent answer
identically), every sortable column ascending and descending, five paginated
windows, `LIMIT 0`, every band including the never-served one, and
refused-versus-nonexistent for every subject in the world plus two that do not
exist.

### Where the comparison is deliberately weaker, and why

`id` is unique, so its ordering is total and is compared exactly. `subject_id`,
`band` and `created_at` tie, and SQLite orders ties arbitrarily — two engines
running the same statement may legitimately return tied rows in a different
sequence. For those the comparison is the **multiset of rows plus the sequence of
sort keys**, which is everything the ordering actually promises. Pagination cases
all sort by `id`, where the window is unambiguous, and are additionally checked
for denseness against `COUNT(*)`.

---

## The mutation test — a gate that cannot fail is not a gate

`npm run test:mutation` edits `dist/`, re-runs the suite, restores the file and
verifies the restoration by hash. Actual output:

| Mutation | What breaks | Caught by |
| --- | --- | --- |
| `deny-precedence` | denies negate only the first term | differential (7,473 disagreements) + gate |
| `fail-open` | empty allow set compiles to `1` | differential (124) + gate |
| `param-collision` | per-rule scoping dropped | differential (14,997) + gate |
| `guardian-clause` | guardian authority never expires | differential (14,650, **all text**) + gate |
| `count-in-js` | `count()` becomes `rows.length` | **gate only** |

The last two rows are the interesting ones and both are in the list on purpose.

**`count-in-js`.** Computing the count over fetched rows returns *the same
number*, so the differential agrees on all 27,534 comparisons and reports a clean
pass. What is wrong is that the hidden rows were read into the tab to produce it —
which is exactly what the build plan forbids ("if the count is computed in
JavaScript over fetched rows, the phase is not done"). Only the traced test in
`test/gate.mjs` sees it: it records every statement the store issues and requires
`count()` to issue exactly one touching `facts`, that it be a `COUNT(*)`, that it
carry the predicate, and that it select no payload.

**`guardian-clause`.** Deleting the guardian clause — putting `policy.ts` back the
way P1 left it — produces 14,650 differential disagreements, which looks like an
emphatic catch. Classified, they are 130 policy `rules`, 130 policy `predicate`,
130 policy `params`, 7,130 store `predicate` and 7,130 store `predicate params`.
**Zero counts, zero row sets, zero subject lists.** The randomised corpus has no
`people` rows and no guardian-derived grants, so removing the clause changes no
answer anywhere in it; the differential is comparing spelling. That is a real
check — it is what caught this port being behind in the first place — but it
would not survive the port spelling an equivalent predicate differently, and it
says nothing about what the clause is *for*. The guardian block in `gate.mjs`
does: a guardian sees their fifteen-year-old's rows, the same grant row untouched
authorizes nothing once the birthdate says eighteen, and a member-granted grant is
unaffected by any birthdate (the control, without which "deny everything" would
pass). Plus migration 002's triggers on the write path, and 004's per-partition
chain rule.

**The differential alone is not sufficient for the P1 gate.** That is a finding,
not a caveat, and P2 did not change it.

---

## What is NOT verified here

Stated plainly rather than buried.

- **The differential runs on the in-memory VFS, not `opfs-sahpool`.** Node has no
  OPFS, so `sqlite3.installOpfsSAHPoolVfs` does not exist in the Node build and
  the VFS this app ships on is not exercised by `npm test`. What *is* exercised
  is every line of the resolver, compiler, schema and store, against the same
  SQLite library the browser gets. The VFS sits below all of that and changes no
  query result — but "changes no query result" is an argument, not a test.
- **The Web Locks election is untested.** `src/owner/election.ts` is never
  executed by any automated check. Node has no `navigator.locks`.
- **`pauseVfs()`/`unpauseVfs()` handoff is untested.** Same reason.
- **SharedWorker uniqueness is untested.** `test/owner.mjs` drives the protocol
  over a real `MessageChannel` with real structured cloning, which is the whole
  wire; it cannot test that the browser gives every tab the same worker.

[`test/browser.html`](test/browser.html) drives those four manually: serve the
directory over http (not `file://` — a null origin has no OPFS), open it in two
tabs, and press the buttons. It is a manual check and it is not a gate. Wiring it
to Playwright would make it one; that work is not done.

**Wiring the differential into CI did not change any of the above.** The
`browser-resolver` job runs the same Node suite on the same in-memory VFS, so the
four browser-only mechanisms are exactly as unverified by automation as they were
before — and are now unverified *in CI*, which is easier to misread. A green
required check named `test` is easy to take as "the browser half is covered". What
is covered is the resolver, the compiler, the schema and the store.

Also not automated here: the `subject_consent` core, which is Python-only by
design and is tested by `../tests/test_consent.py`. This port carries the schema
its rows land in and nothing else, so the triggers hold for the tables a browser
creates — `gate.mjs` checks that they fire — but nothing confirms the two hosts
agree about the *chain*, because only one of them has one.

---

## CI wiring — applied

A test that does not run in CI is not a test. `.github/workflows/store-ci.yml`
now carries a `browser-resolver` job, and that job is in the aggregate `test`
job's `needs:`:

```yaml
  browser-resolver:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v7
      - name: Set up Python
        uses: actions/setup-python@v7
        with:
          python-version: "3.12"
      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: "22"          # >=22: @sqlite.org/sqlite-wasm requires it
          cache: npm
          cache-dependency-path: apps/marching-arts/browser/package-lock.json
      - name: Install
        working-directory: apps/marching-arts/browser
        run: npm ci
      - name: Build
        working-directory: apps/marching-arts/browser
        run: npm run build
      - name: Differential against the Python core
        working-directory: apps/marching-arts/browser
        run: npm test                 # regenerates reference.json, then all stages
      - name: Mutation test
        working-directory: apps/marching-arts/browser
        run: npm run test:mutation

  test:
    needs: [gates, app-tests, browser-resolver]
```

The `needs:` line is the load-bearing one. Branch protection requires a single
check named `test`; without it the job runs, nothing depends on it, and that is
the same as not running.

It is a separate job rather than an addition to the `app-tests` matrix because
that matrix is Python-only, and folding Node into it would put a `setup-node`
step in every other app's leg for the benefit of none of them.

**Sequencing.** This was deliberately not wired before, because CI checks out a
clean tree and the generator's default mode compares against whatever
`marching_arts/` is at that commit — with the port behind by P2, wiring it would
have turned the whole store's `test` job red. It is wired now because the port is
genuinely level: 27,534 comparisons, 0 disagreements, reference regenerated from
the working tree. What was never an option is pinning the generator to a fixed
`--rev` in CI to keep it green; that converts the gate into a decoration. If this
job goes red, the core moved and the port did not, and that is the finding.

Two properties of this repo's CI that the wiring respects:

- `gates` runs `python -m compileall -q apps ...` over everything. `test/
  gen_reference.py` byte-compiles; keep it stdlib-only so no dependency install
  is needed for that step — and note the job above installs no Python packages
  for the same reason.
- `app-tests` for `marching-arts` runs `pytest tests/` from the app directory.
  `browser/` contains no `test_*.py`, so it is not collected there and the two
  suites stay independent.

`test/reference.json` is gitignored on purpose. A committed reference is a
snapshot of what the core *used to* do, and a differential against a stale
snapshot passes forever.

---

## Verdict on `quick-stupids/app/src/storage/`

Judged, as asked. About 630 lines of storage plus ~790 of shell/CSS.

**Reused — the shape, not the code.**

- The **named-backend seam with an ordered ladder** (`selectBackend()`: OPFS →
  IndexedDB → memory, each rung recording *why* it was skipped into a `notes[]`
  the UI can render). That is the right shape and `src/open.ts` reproduces it for
  a different ladder — `opfs-sahpool` → memory — including `durable: false` being
  a reported fact rather than a silent degradation. A shell that hides
  `durable === false` is lying to a user about whether their data survives the
  tab, and that idea came from there.
- The **honesty of `notes`**. Worth keeping in any storage layer.

**Discarded — everything else, and not because it is bad.**

- `store.js`, `files.js`, the three backends: this is a **named-blob store**, one
  file per item per namespace, with `save`/`load`/`list`/`remove` and
  import/export to disk. It is a competent piece of work. It is also the wrong
  data model for P1 by an entire category: there is no place in it to put a
  `WHERE` clause, so there is no place to put the predicate. Every guarantee P1
  owes — count under a predicate, a filter that can only narrow, a sort that
  cannot smuggle a subquery, refused indistinguishable from nonexistent —
  requires a relational engine. Adapting it would have meant fetching rows and
  filtering in JavaScript, which is precisely the failure the P1 gate is written
  to catch.
- `names.js` (197 lines of filename validation: NFC normalisation, control
  characters, path separators, Windows reserved names). Careful, and irrelevant
  here — the SAH pool addresses its own files and no user-supplied string
  becomes a filename anywhere in this port. Carrying it would have been dead code
  wearing a safety costume.
- The OPFS backend's `createWritable()` path. `opfs-sahpool` uses sync access
  handles from a worker instead, which is a different API for a different reason.
- `app/index.html` and `app/styles/`. Shell, not resolver. P4's problem, and the
  build plan says the chassis is settled and partly written; nothing in P1 needs
  it.

**One thing in there is a live hazard.** `openStorage()` memoises a single module
-level `opening` promise, so a session gets one backend forever and there is no
handoff, no re-election and no way to release a handle. That is fine for a blob
store on OPFS's async API and fatal for `opfs-sahpool`, whose handles are
exclusive. If anyone re-lands that module as-is next to this one, two owners will
race for the pool and the loser gets an exception at open time — which is the
*good* outcome; the bad one is a tab that silently falls back to memory and
reports itself as durable. The single-promise memo is the pattern to leave
behind.

Net: one idea kept, ~630 lines not carried across. The repo's own CLAUDE.md is
right that re-landing is where the mistakes get caught — the mistake caught here
was the data model.
