# marching-arts-shell

The P4 chassis: shell, storage seam, offline, and the mark. **It contains no
capability, and that is the deliverable.**

[BUILD_PLAN.md][plan] P4 reads *"Shell and the first capability · blocked on the
core job"*, and says what goes inside it "is the one open question". The same
paragraph calls the chassis settled and partly written. So this is the settled
half, built; the open half is left open, and there is a test that fails if
anyone closes it in code instead of with the person who owns the decision.

```sh
make demo app=marching-arts-shell   # from the repo root — the wiring, watched happening
```

```sh
npm install
npm run build        # the mark, the icon SVGs, the app-bar glyph
npm run icons        # the PNG set — needs Chromium
npm test             # 74 gates, no browser
npm run test:raster  # the rasteriser, in a real browser
npm run demo         # the same thing make demo runs
npm run mutate:named # every gate proven able to fail, by name
```

## The wiring demo

`demo.sh` serves this over real HTTP on an ephemeral port — P4's gate says
"from a static host", and explicitly not `file://`, where a null origin kills
fetch, WASM, modules and OPFS alike — then drives a real Chromium through every
seam and prints what each one did. It exits non-zero if a step does not do what
it says, because a demo that cannot fail is a screenshot. It runs in CI for the
same reason.

Its last two steps are the ones no unit test here can reach: **cut the network
and reload**, and count every request that went anywhere other than this host.

**It found a defect on its first run, which is the argument for having it.** The
`opfs-sahpool` rung's `available()` checks `createSyncAccessHandle`, which
Chromium exposes on dedicated workers and *not* on the window — verified both
ways on one origin. `probeStorage()` runs on the main thread, so that rung could
never be seen, and the seam would have reported `indexeddb` on every browser
alive, including ones that fully support the better rung. Every test passed
throughout: they all fed `probeStorage` a synthetic ladder, so the real
predicate had never executed in a browser anywhere. It is now recorded as
`unprobed` rather than `unavailable` — a rung this context cannot see is a
different fact from a rung that is not there — and the status bar says
"better rungs unprobed here" instead of quietly claiming the lesser one.

## What is here

| | |
| --- | --- |
| `web/` | the shell — `index.html`, tokens, styles, service worker, capability seam, storage seam |
| `mark/` | the logo, generated from a spec of eight numbers rather than drawn |
| `test/` | the gates |

**The capability seam is empty.** `web/src/capabilities.js` exports a working
registry with nothing in it, and `test/shell.test.mjs` asserts it stays that way.
That test is meant to be changed — in the commit that adds the first capability,
by someone who has the answer to the core job.

**The storage seam reports; it does not store.** An ordered ladder of backends
with a `notes[]` recording why each rung was skipped, and `durable: false`
carried as a reported fact rather than a silent downgrade. Real storage is
[`@marching-arts/browser`][browser] — SQLite-WASM on OPFS — because a blob store
has nowhere to put a `WHERE` clause and therefore nowhere to put the
authorization predicate, which is the exact failure P1's gate exists to catch.
This module is what the quick-stupids skeleton's storage layer became after
~630 lines of it were judged and discarded; only the shape was kept, and the
module-level memoised promise that would have been fatal for `opfs-sahpool`'s
exclusive handles is gone, with a test that fails if it comes back.

**`network: none` is a mechanism.** The page sets `connect-src 'none'`; the
service worker is cache-only and contains no path to the network at all. A gate
strips comments from `sw.js` and fails on `fetch(` — after its first run failed
on that file's own comment saying no `fetch()` appears in it, which is a fair
demonstration that a check reading prose can be broken by prose.

**The mark is generated.** Three sources on a circle and the wavefront each
sends to the other two; for N = 3 the arcs close into a Reuleaux triangle, so
the mark has the same width measured in every direction. Every coordinate
derives from the spec, and the maskable icon is not a padded copy — Android
masks to a circle of 80% diameter, the mark's ink reaches 87.5% of the half-box,
so `icon-512-maskable.png` is rebuilt at `clearRatio: 2` (77.8%) and passes the
same invariants unchanged. See [`mark/README.md`][mark] for the construction and
for what its gates structurally cannot see.

## What is NOT claimed

- **P4's gate is still not met, but it is closer and the gap is now exact.** It
  reads *"works fully offline after first load, on a Chromebook, from a static
  host"*. The demo serves it from a static host and does reload it with the
  network cut, in CI, on every push — so two thirds of that sentence is now
  mechanised. **No Chromebook has run this**, and that is the whole of what is
  left unproven in it.
- **`favicon.ico` is absent.** The 2026 minimum set is six files and this ships
  five; ICO needs an encoder nothing here has. Modern browsers take the SVG.
- **No capability, so nothing has been demonstrated to anyone.** A chassis with
  nothing in it cannot earn a meeting, which is what P4 says the first screen is
  for.
- **This is `apps/`, which is the contested playground.** Per the store's rules
  nothing here is a standing app and nothing is trusted until promoted, and
  promotion is a separate, witnessed extraction into its own repo.

## Provenance

Re-landed from `rudi193-cmd/quick-stupids`, a cloud-only playground that cannot
be a dependency of anything. Re-landing there means rebuilding against this
repo's conventions rather than copying: manifest, catalog entry, store scope,
its own CI leg. The mark's generator, invariants and mutation harness came
across; the SVG did not, because the generator is the artefact and the SVG is
output.

The named-mutation harness in `mark/mutate.mjs` is itself borrowed back from
this repo — [`apps/marching-arts/browser/test/mutate.mjs`][theirs] had the
restore verification and the green-after-restore control first. It departs in
one way: it never writes to the working tree, because the harness it replaced
used `git checkout -- .` and destroyed uncommitted work doing it.

[plan]: ../marching-arts/docs/BUILD_PLAN.md
[browser]: ../marching-arts/browser/
[theirs]: ../marching-arts/browser/test/mutate.mjs
[mark]: mark/README.md
