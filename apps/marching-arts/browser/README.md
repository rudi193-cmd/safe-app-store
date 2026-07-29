# marching-arts / browser — the browser half of P1

> **Status: behind the core, and `npm test` fails saying so.** This port
> implements P1 as merged at `1ee4ee6`. P2 — consent, guardianships, migrations
> 002/003 — landed in `../marching_arts/` afterwards and is not ported yet, so
> the differential reports disagreements in the constants and policy tiers. That
> is the harness doing its job, not a broken build. **Do not wire this into CI
> until the port is brought forward**; it would turn the store's aggregate
> `test` job red. See *The drift gate* below.

The authorization resolver, running in-browser on SQLite-WASM, and a differential
suite that holds it to the Python core in [`../marching_arts/`](../marching_arts).

The rules are *decided* in Python. This is a second implementation of the same
rules, and a second implementation is a liability unless something mechanical
keeps the two identical. That something is [`test/`](test): a generator that runs
the Python resolver over a randomised corpus and dumps everything it produced,
and a comparator that replays the identical corpus through this port.

**27,528 comparisons, 0 disagreements.** Four deliberate bugs, all caught. The
numbers and what they do and do not cover are below.

---

## What is here

| File | What it is |
| --- | --- |
| `src/rules.ts` | The rules→SQL `WHERE` compiler. `compile_rules` reproduced exactly. |
| `src/policy.ts` | Who may see what. Every SQL fragment byte-compared against `policy.py`. |
| `src/bands.ts` | L0–L6, `DERIVE_AT`, `NEVER_SERVED`. |
| `src/schema.ts` | Migration 001, DDL byte-identical to `schema.py`. |
| `src/store.ts` | Authorized reads. `count` is a SQL `COUNT(*)`; there is no array to take the length of. |
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

`npm test` generates `test/reference.json` if it is missing and **fails** if it
cannot. `gen_reference.py` is stdlib-only, so any Python that can run the app's
own suite can produce it. The sibling harness in `apps/field-acoustics/kernel`
reports its differential as *skipped* when its reference is absent, which is
honest there because it needs numpy and scipy. A skip here would mean the browser
resolver shipped with nothing holding it to the semantics it is a copy of, so
this one refuses.

### Which Python is "the" Python

`gen_reference.py` reads `marching_arts/` from the **working tree** by default.
That is the gate: when the core changes and the port does not, the suite fails.
It warns on stderr if the working tree is dirty. `--rev REV` pins to a git
revision instead — a deliberate act, and the revision is recorded in the output
file so a reader can always tell what a reference was generated from.

---

## The numbers

Reference generated against `marching_arts/` at `1ee4ee6` (P1 as merged;
`--rev HEAD`, because the working tree was mid-P2 under another pair of hands).

```
corpus     14 worlds · 130 principal cases · 7,130 store queries
           249 compiler cases over a 24-row scratch table
           8 schema rejections, each confirmed refused by Python first

tier         checks   result
constants         9   ok      band integers, DERIVE_AT, NEVER_SERVED,
                              DENY_ALL, SORTABLE, migration DDL byte-for-byte
compiler        996   ok      predicate text, parameters, explain(), and the
                              rows each predicate actually selects
policy          780   ok      every rule fragment as SQL text, per principal
store        25,735   ok      the adversarial battery, per (world, principal)
schema            8   ok      the writes that must be refused

27,528 comparisons, 0 disagreements
```

Plus 31 gate tests and 10 owner-protocol tests, which say what *correct* is
independently — two implementations can agree while both being wrong.

### The drift gate, demonstrated

While this was being built, `marching_arts/` was being extended in the working
tree by another pair of hands: P2 consent — a `people` table, guardianships, a
hash-chained consent log, migration 002, and a `granted_via` clause inside the
grant subquery. That is what the generator's default mode is for. Pointed at the
working tree instead of `HEAD`:

```
constants     13 checks   FAIL 5       migration count 3, port has 1;
                                       002_people_guardianship_and_consent_chain missing
compiler     996 checks   ok           compile_rules is unchanged — correctly unaffected
policy       780 checks   FAIL 520     the grant fragment gained a guardian clause
store     25,735 checks   FAIL 14,260
```

14,785 disagreements, located in seconds, and the tiering did its job: the
compiler tier stayed green because the compiler did not change, so the finding
points at the policy rather than at everything at once.

**This port therefore implements P1 as merged at `1ee4ee6`, and is already behind
the core.** Bringing it forward is a follow-up: port migration 002, the guardian
clause in `Policy.rules`, and the consent chain, then regenerate with the default
(working-tree) mode and drive the count back to zero. Nothing in the harness needs
to change to do that — which is the point of building the harness first.

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
| `count-in-js` | `count()` becomes `rows.length` | **gate only** |

The last row is the interesting one and it is in the list on purpose. Computing
the count over fetched rows returns *the same number*, so the differential agrees
on all 27,528 comparisons and reports a clean pass. What is wrong is that the
hidden rows were read into the tab to produce it — which is exactly what the
build plan forbids ("if the count is computed in JavaScript over fetched rows,
the phase is not done"). Only the traced test in `test/gate.mjs` sees it: it
records every statement the store issues and requires `count()` to issue exactly
one touching `facts`, that it be a `COUNT(*)`, that it carry the predicate, and
that it select no payload.

**The differential alone is not sufficient for the P1 gate.** That is a finding,
not a caveat.

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

---

## CI wiring this needs

**None of this runs in CI yet, and a test that does not run in CI is not a test.**
The wiring below is described rather than added, because `.github/workflows/
store-ci.yml` is outside this task's write scope.

The store-wide workflow has two jobs: `gates` (Python-only, whole-store) and
`app-tests` (a matrix leg per app, running `python -m pytest tests/ -q`). Neither
runs Node. What is needed is a third job, or an addition to the `marching-arts`
matrix leg:

```yaml
  browser-resolver:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with: { python-version: "3.12" }
      - uses: actions/setup-node@v4
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
        run: npm test                 # generates reference.json, then all stages
      - name: Mutation test
        working-directory: apps/marching-arts/browser
        run: npm run test:mutation
```

Then add `browser-resolver` to the `needs:` list of the aggregate `test` job, so
branch protection actually blocks on it. Without that last line the job runs and
nothing depends on it, which is the same as not running.

**Sequencing matters here.** CI checks out a clean tree, so the generator's
default mode compares against whatever `marching_arts/` is at that commit. The
port is currently behind the core by the P2 consent work (see *The drift gate,
demonstrated* above), so wiring this job today makes `test` red on the next merge
of P2. Two honest options, in preference order: bring the port forward first and
then wire the job, or wire it now with `continue-on-error: true` and an issue
tracking its removal. What is not acceptable is pinning the generator to a fixed
`--rev` in CI to keep it green — that converts the gate into a decoration.

Two properties of this repo's CI that the wiring has to respect:

- `gates` runs `python -m compileall -q apps ...` over everything. `test/
  gen_reference.py` byte-compiles; keep it stdlib-only so no dependency install
  is needed for that step.
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
