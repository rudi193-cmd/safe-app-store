# The dcisim mark

Three sources on a circle, and the wavefront each one sends to the other two.

The mark is generated, not drawn. `construct.mjs` derives every coordinate from
a spec of eight numbers; `build.mjs` writes the files; `invariants.mjs` says
what has to be true; `construct.test.mjs` holds the shipped files to it. No
coordinate in this directory was typed by a person, and the suite fails if one
ever is.

`explore.mjs` builds other marks from the same construction and runs the same
invariants over them. That is not decoration — it is how four of the invariants
were found to be statements about this logo rather than about the construction.
See *What playing with it broke*, below.

---

## The construction

Start with a circle — centre `O`, radius `R`. It is never drawn. Everything
below is a consequence of it and of the spec.

| | CANON | Where it comes from |
| --- | --- | --- |
| `N` | 3 | order of rotational symmetry, and of the inscribed regular polygon |
| `R` | 24 | the only free length in the mark |
| `span` | 1 | how far round the polygon each wavefront reaches |
| `phase` | −90° | bearing of the first source; −90 puts it at the top |
| `sourceRatio` | 6 | source dot radius, as `R/6` = 4 |
| `strokeRatio` | 1 | stroke weight, as a multiple of the source radius = 4 |
| `gapRatio` | 2 | trim chord, as a multiple of the source radius = 8 |
| `clearRatio` | 1 | clear space outside the ink, as a multiple of it = 4 |

and everything derived from those:

| | Value | How |
| --- | --- | --- |
| sources | (32, 8), (52.7846, 44), (11.2154, 44) | vertices of the inscribed regular `N`-gon |
| `side` | 41.569219… | `2R·sin(π·span/N)` — distance from a source to the peers it reaches |
| `aperture` | 60° | `180(N − 2·span)/N`, the angle those peers subtend at it |
| `trim` | 11.043666° | the `gap` chord as an angle, `2·asin(gap / 2·side)` |
| drawn sweep | 37.912669° | `aperture − 2·trim` |
| `box` | 64 | `2(R + source + clearance)` |
| `precision` | 4 decimals | searched for, not chosen — see below |

**Each arc is a wavefront.** It is centred on one source with radius equal to
the distance to its peers: the wavefront leaving that source at the instant it
arrives at them. All three sources are mutually equidistant, so a listener at
any one of them hears the other two at the same moment, and the mark is a
picture of that fact rather than a decoration alluding to it.

**The three arcs close.** Three circles of radius `side` centred on the
vertices of an equilateral triangle of side `side` meet at those vertices, so
the arcs form a Reuleaux triangle — a curve of constant width. The mark
measures the same across every direction it is measured in.

That generalises exactly one way: for **odd** `N` with `span = (N−1)/2`, each
arc reaches the two opposite vertices and the curve closes into a Reuleaux
polygon. `N 5 span 2` and `N 7 span 3` are real marks. Every other combination
either tangles or is refused, and the invariants now say which.

**The arcs stop short of the sources.** Each is trimmed by `gap` at both ends,
so a wavefront visibly arrives at a source rather than merging into it.

**The grid is derived.** The ink reaches `R + source` from the centre and the
clear space is one further `source`, so `box = 2(R + source + clearance) = 64`,
met exactly at the apex.

**The mark is centred on `O`, not on its bounding box.** The ink spans
x ∈ [7.2154, 56.7846] and y ∈ [4, 51.5692], which is not symmetric top to
bottom — no 3-fold shape is. `O` is the centroid and the axis of rotation.

## Files

| | |
| --- | --- |
| `construct.mjs` | the construction. Everything else is downstream of it |
| `endpoint.mjs` | SVG's endpoint-to-centre arc conversion, shared by the two callers below |
| `invariants.mjs` | what has to be true, as predicates over any geometry |
| `build.mjs` | writes `../icon.svg`, `icon-touch.svg`, and the inline glyph in `../../index.html` |
| `rasterise.mjs` | writes `../icon-192.png`, needs Chromium |
| `png.mjs` | PNG read/write via pngjs, plus the pixel helpers the raster gates use |
| `construct.test.mjs` | the gates, applied to CANON |
| `explore.mjs` | the same gates, applied to everything else, plus a contact sheet |
| `stryker.config.json` | mutation testing config, at the repo root |

```sh
node app/assets/logo/build.mjs        # SVGs and the app-bar glyph
node app/assets/logo/rasterise.mjs    # the touch icon; --chrome <path> if not found
node --test app/assets/logo/construct.test.mjs
node app/assets/logo/explore.mjs --sheet   # variants + a contact sheet in preview/
```

The mark's colour is not the mark's decision. `icon.svg` carries `--accent`
from `styles/tokens.css` in both themes, because a document referenced by
`<link rel="icon">` has no parent to inherit `currentColor` from and would
otherwise be black on a dark tab strip.

## What playing with it broke

Every invariant in the original suite passed. Running the same invariants over
other specs found four that only ever described this logo, and two things
nobody was checking at all.

**Emission precision was a property of CANON, not of the construction.**
Recovering an arc's centre from rounded endpoints is ill-conditioned in
proportion to how shallow the arc is. At four decimals the recovered centre
lands 7.0e-5 from its source for `N 3 span 1`, 5.9e-4 for `N 7 span 3`, and
5.6e-3 for `N 9 span 4` — past the 1e-3 the invariant allows, for constructions
exactly as correct as CANON. The precision is now searched for and verified by
recovery rather than fixed: CANON still emits at 4 decimals, `N 5 span 2` needs
5, `N 9 span 4` needs 7, and a spec no precision can encode is refused.

*This has a cost, stated because it is easy to miss:* the search makes `every
drawn arc is centred on a source` **enforced** as well as checked. It is no
longer independent confirmation. It still catches a hand-edited file, which the
search cannot, but a reader should not count it twice.

**Nothing checked whether the mark tangles.** `N 4/5/6/7 span 1` are all
correct constructions in which the arcs sweep straight through each other —
4 to 14 crossings apiece, wavefronts passing within 0.000 to 0.053 of one
another against a stroke of 4. Every invariant in the original suite passed on
all of them. Two new gates: `no wavefront crosses another`, computed from exact
circle intersections restricted to the drawn sweeps, and `wavefronts stay a
stroke apart from each other`.

**Nothing checked whether a wavefront still reads as a wavefront.** `N 7 span 3`
and `N 9 span 4` passed all twelve invariants while rendering as rings of dots:
their arcs are shorter than the stroke is thick, so the round caps swallow them.
New gate: `each wavefront is longer than the stroke is thick`. `N 9 span 4` now
fails it at 0.481 against a stroke of 4. `N 7 span 3` passes at 4.98 — marginal,
and on the contact sheet it reads as dashes, so the threshold is a floor and
not a guarantee of elegance.

**The raster mirror gate was a statement about `phase`.** It holds because
CANON puts a source at −90°, on the vertical axis. Spin the same mark to phase 0
and it is still correct and has no vertical mirror at all, so the gate would
have been asserting a fact about one spec. It now asserts its own precondition
first and fails loudly if CANON ever stops satisfying it.

**Grid tightness needs a source on an axis.** `box` assumes the extreme ink
sits on one of the four axes. True at phase −90, 0 and 30 for `N` 3; false at
phase 15, where the same mark floats in a box 0.82 larger than it asked for. Now
split into `the ink stays inside the clear space`, which is universal, and `the
grid is no larger than the mark needs`, which is not.

One correction to record rather than quietly fix: the clear-space check was
dropped when the invariants moved out of the test file into `invariants.mjs`,
and the suite was green without it for several commits. It was noticed by
counting the checks against the old test list, not by anything automated.

## What the gates catch

Thirty-seven tests. Fifteen are invariants applied to CANON, fourteen are
positive controls — specs that must trip a named gate or be refused outright —
and the rest are about the artefact: the committed files, the colours they
carry, the raster, and its size.

There are two mutation harnesses, and neither subsumes the other:

```sh
npm run mutate          # Stryker: ~900 generated mutants, breadth
npm run mutate:named    # mutate.mjs: 13 chosen defects, attribution
```

[Stryker](https://github.com/stryker-mutator/stryker-js) (Apache-2.0) generates
mutants nobody thought to write, which is how the gutted-`withinSweep` hole was
found at all. It cannot say *which* gate caught what: `node --test` is only
drivable through its TAP runner, which reports one test per file, so every
mutant returns `killedBy: ["0"]`.

`mutate.mjs` is thirteen defects that matter, each naming the gate that must
catch it, and it fails if the **wrong** gate catches one. Its design is taken
from `apps/marching-arts/browser/test/mutate.mjs` in `safe-app-store`, which had
all of this first — including verifying the restore and re-running the suite
afterwards to prove the harness is not simply failing on everything. One
departure: that harness mutates in place and hashes to prove the restore took;
this one copies into a sandbox and never writes to the working tree, because the
throwaway harness it replaces used `git checkout -- .` and destroyed uncommitted
work doing it.

Wrong-gate attribution has now paid for itself twice. It found that `the
wavefront radius is the distance to the peers it reaches` compared peer spacing
to `side` and **never looked at an arc's radius** — half of what its title
claimed was unchecked, and no amount of Stryker breadth would have said so,
because the mutants it generates are killed by *something*. It also found that
inflating a wavefront radius 1% is not caught by a gate at all: the precision
search cannot recover any centre, so the generator refuses first, which is a
stronger outcome and a different one.

**Adopting it immediately found something two rounds of hand-authored defects
had missed.** 659 mutants over `construct.mjs`, `invariants.mjs` and
`endpoint.mjs`; 235 survived. The sharpest: emptying the body of
`withinSweep()` in `invariants.mjs` survives. Every test passes with it gutted,
and `no wavefront crosses another` then reports zero crossings for `N 4 span 1`
— the mark that visibly tangles, and the reason that gate was added in the first
place. It had never been shown to fire from inside the suite, because the suite
only ever fed it CANON, which does not tangle either way.

The same held for every refusal branch in `derive()`, and for the precision
search: `if (worst <= RECOVERY_TARGET) return decimals` mutated to `true`
survived, because CANON needs exactly the floor precision and nothing else was
ever constructed.

`explore.mjs` had been catching all of this the whole time — as a script someone
runs and reads, which is not a gate. Fourteen of its variants are now tests.
That took the score from **59.5% to 72.2%**, and killed 92 more mutants.

| | Before positive controls | After |
| --- | --- | --- |
| killed | 344 | 436 |
| survived | 235 | 168 |
| no coverage | 47 | 22 |

**Then the other three modules were mutated too, and the score turned out to be
the wrong number to read.** Stryker's percentage is computed over mutants that
were *executed*. Report `killed/total` instead and the picture inverts:

| file | killed / total | Stryker's score | never executed |
| --- | --- | --- | --- |
| `endpoint.mjs` | 58/66 | 90.6% | 3% |
| `construct.mjs` | 184/239 | 83.3% | 3% |
| `build.mjs` | 44/73 | 71.0% | 15% |
| `invariants.mjs` | 195/354 | 60.9% | 4% |
| `png.mjs` | 22/68 | **95.7%** | **66%** |
| `rasterise.mjs` | 2/83 | 20.0% | **88%** |

`png.mjs` has the best score in the repo and is the second-worst covered: two
thirds of it never runs, because `encodePng` and `crop` are only reached from
`rasterise.mjs`, which no test calls. This is the repo's own rule about coverage
being a claim about the harness, landing on the harness itself.

One survivor from that run is now closed. The `ENCODE` settings object in
`png.mjs` could be emptied with nothing noticing — and that object is the only
thing keeping the icon at 4,178 bytes rather than 6,182. The byte-budget gate
checked the committed *file*, not the encoder that wrote it. There is now a
round-trip gate: decode the committed PNG, re-encode its own pixels, require
byte-identity. It never re-renders, so it is stable across Chromium versions,
and it fails if either the encoder settings or the committed file drift.
Deliberately setting `deflateStrategy: 3` makes exactly that one test fail.

**The tolerance survivors are now dead, and what replaced them is instructive.**
Those gates had no reachable failure: a spec cannot put a source off the basis
circle, because the construction derives it there, so `ConditionalExpression →
true` survived on every one of them — nothing constructible distinguishes a
working check from one that always passes. Perturbing a *geometry object*
reaches what a spec cannot. Eight gates now get a corruption just over their
tolerance, which must fail, and one just under, which must pass; that makes the
tolerance itself the subject, since loosening it stops the over case failing and
tightening it starts the under case failing.

Measured: `invariants.mjs` went from 195/354 killed to 241/397, and every
`→ true` mutant on those eight gates is now killed. What survives on those lines
is `<` mutated to `<=`, which differs only when a measured error is *exactly*
the tolerance — unreachable in floating point, so equivalent rather than
untested — and `detail` strings mutated to empty, which no test should assert
on. Those could be suppressed with `// Stryker disable`, which would make the
remaining count mean something; that is a deliberate call and has not been made.

Two magnitudes had to be measured rather than assumed, and both taught
something. `sources lie on the basis circle` needed its perturbation in `y`:
at the apex an `x` displacement is tangential, and a radial-distance check is
right to report zero error for it. And `the mark maps onto itself under
rotation` needed 1e-4, not 1e-12, because it compares coordinates rounded to
four decimals — its real tolerance is four orders looser than it looks in the
source, which nothing had ever stated.

**Survivors are not all bad tests, and the score should not be chased.**
Twenty-five are mutations of `detail` strings — diagnostic text no test should
ever assert on. Fifty-six sit on a tolerance or a number-formatting call, where
loosening `< 1e-12` to something larger changes nothing detectable because the
measured error is around 1e-15 for every spec we construct. Killing those needs
adversarial near-miss inputs: specs whose error lands *between* the old
tolerance and the new one. That is a real remaining gap and a real technique,
and it is the thing the old hand-rolled harness was accidentally doing when it
nudged a coordinate by 0.4.

Stryker cannot tell an equivalent mutant from a missing test. Neither can a
percentage. The number above is a prompt to go and look, not a target.

## What this was checked against

- **Rendered, at size, in a browser.** 200, 64, 48, 32, 24 and 16 px, light and
  dark, in Chromium. Stroke weight was chosen there: at `R/8` the mark is more
  elegant large and loses the source-to-line contrast by 24 px; `R/6` holds it.
  Below 24 px the trim gaps close and the silhouette survives but the reading
  does not. Use the wordmark.
- **Every variant in `explore.mjs`**, drawn on one contact sheet and looked at,
  which is how the dotted-ring failure was spotted before it was measurable.
- **Byte size of the shipped raster.** Swapping the hand-written PNG encoder for
  pngjs inflated `icon-192.png` by 48%, from 4,178 to 6,182 bytes, and all 22
  gates then passed without noticing. pngjs defaults to adaptive row filtering
  with the Z_RLE deflate strategy, which is right for photographs and wrong for
  flat two-colour art; pinning `colorType 2, filterType 0, deflateStrategy 0`
  reproduces the old output exactly. There is now a byte-budget gate.

## What the harness structurally cannot see

- ~~There is no CI in this repo~~ — there is now, in
  `.github/workflows/logo.yml`, and it is the reason any number here means
  anything. Two jobs, split the way `safe-app-store` splits `browser-resolver`
  from `browser-mechanisms`: `gates` runs the suite, the named mutations and an
  idempotent-build check without a browser; `raster` installs Chromium and runs
  `raster.test.mjs`. **What is still unverified is whether the workflow passes
  on a runner** — it has only been simulated locally, step by step, and a
  workflow that has never had a green run is a plan, not a gate.
- **`rasterise.mjs` was 2 of 83 mutants killed, 88% never executed** — no test
  called it, they read the committed PNG instead. `raster.test.mjs` now
  rasterises fresh in a real Chromium and compares every one of the 36,864
  pixels against the committed icon, then asserts the comparisons happened
  rather than trusting exit 0. It **does not skip**: no browser is a failure,
  because a skipped test exiting 0 is precisely how `safe-app-store` ended up
  with a differential leg reporting green having compared nothing.
  The corner-white guard is extracted as `assertCropCaughtTheIcon` and gated in
  the browserless suite against synthetic images, because the condition it
  guards cannot be induced on demand — asking Chromium for a 4096px icon just
  yields a 4096px icon. Whether a real viewport ever trips it remains
  unverified; that is a smaller unknown than the whole guard being unexercised.
- **No test renders the SVG.** The raster gates read `icon-192.png`, produced
  from `icon-touch.svg` — a different file from `icon.svg`, sharing only the
  generated body. A defect reaching `icon.svg` alone would be caught by
  byte-comparison but never seen drawn.
- **The legibility gates are floors, not judgements.** `longer than the stroke
  is thick` separates a wavefront from a dot. It has nothing to say about
  whether the result is any good, and `N 7 span 3` passes it while looking like
  a dashed circle.
- **`the gap leaves the source visible` is a design rule wearing an
  invariant's clothes.** `N 5 span 2, gap 0.5` fails three gates and is, on the
  sheet, a perfectly reasonable pentagon logo. The gates encode this mark's
  intent, not a fact about geometry.
- **The ink fraction is a band, not a number.** 0.1185 measured at 192 px under
  Chromium 1194; the test accepts 0.04–0.20 because antialiasing and colour
  management differ between renderers.
- **The PNG's bytes are not reproducible** across Chromium versions, so nothing
  byte-compares it.
- **Mutation attribution does not work here.** Stryker reports `killedBy` per
  mutant, which is why it was chosen — but that needs a runner that reports
  individual tests, and the only path for `node --test` is the TAP runner, which
  reports one test per *file*. Every mutant comes back `killedBy: ["0"]`. So we
  know how many gates can fail, and not which one caught what. The throwaway
  harness this replaced did report failing test names; on that one axis it was
  better, and the trade was made knowingly.
- **Nobody has looked at this on a phone**, as a favicon in a real tab strip, or
  masked into an Android adaptive icon. `index.html` also still references a
  `manifest.webmanifest` that does not exist.

## The mark this replaces

The previous glyph was a source dot with two arcs, and it stated three
different centres for one concentric figure:

| Element | Centre it actually resolves to |
| --- | --- |
| `<circle cx="9" cy="16" r="3" />` | 9 |
| `<path d="M15 8.5a10 10 0 0 1 0 15" />` | 8.3856 |
| `<path d="M19.5 5.5a15.5 15.5 0 0 1 0 21" />` | 8.0982 |

Errors of 0.61 and 0.90 on a 32-unit grid, from endpoints and radii each
plausible on their own. It was drawn by eye, it looked fine, and nothing asked
it a question it could fail — including `r="15.5"` on an arc whose endpoints
put its radius at 14.85.

## Status

Contested tier, like everything here. Read against the destination
(`rudi193-cmd/safe-app-store`, read-only clone at `/workspace/safe-app-store`)
rather than against assumptions about it, this is **not ready to re-land**, for
four reasons the store states itself.

**There is nowhere to put it.** The mark decorates a browser shell — an app bar,
an icon set, `index.html`. The store's `apps/marching-arts/browser/` is a
library: `src/` is `sqlite.ts`, `policy.ts`, `store.ts`, `owner/election.ts`,
and its `package.json` ships `dist`, `src`, `README.md`. No HTML, no shell. The
consumer of this mark does not exist over there, and `tools/catalog_lint.py
--strict` requires `catalog.json` and `apps/` to agree, so an asset cannot land
on its own.

**The suite would not run.** `app-tests` in `.github/workflows/store-ci.yml` is
a hand-maintained matrix literal — eight app names — running
`python -m pytest tests/ -q`. Putting files under `apps/` earns nothing. Node
suites need a dedicated job, and the store has two: `browser-resolver` and
`browser-mechanisms`. This is the same failure already on this project's record,
where two re-landed apps passed locally and neither was in the matrix.

**The store has already been burned by the hole still open here.** The comment
on its `bureau-differential` job: the Python leg "reports green having compared
nothing", because the tests are guarded with `skipUnless(node)` and a skipped
test still exits 0; the dedicated job "asserts they happened rather than
trusting the exit code". `rasterise.mjs` is 2/83 killed and ungated because it
needs a browser. A skip-if-no-Chromium guard would reproduce that failure
exactly. The remedy is already written down: `browser-mechanisms` installs
Chromium via Playwright in its own job, kept separate so the non-browser suite
stays runnable without one.

**What re-landing would actually require**, now that it is known rather than
assumed: a `safe-app-manifest.json`; a catalog entry in
`.willow/store/catalog.json` with `id, name, description, status, version,
path, tier, majors[], tags[]` (`marching-arts` is `status: gated`, `tier:
playground`); Apache-2.0 throughout, which matches; a `package.json` with
`"type": "module"` and `engines.node >= 22`; and a hand-added workflow leg —
two, if the rasteriser is to be gated at all.

`construct.mjs`, `invariants.mjs` and `explore.mjs` remain the artefacts worth
moving. The SVG is output.

### One finding that flows the other way

The store's browser port already has `test/mutate.mjs` and
`test/mutate-browser.mjs` — 472 lines of hand-rolled mutation testing, opening
with "A gate that cannot fail is not a gate." It is **better designed than the
harness this repo replaced**: it verifies the restore by hashing the file before
and after and aborts if the hash differs, it re-runs the suite after restoring
to prove the harness is not simply failing on everything, and it reports which
of two checks caught each mutation — which its own comment calls "the
interesting output".

That last part matters for the recommendation in
[PRIOR_ART.md](../../../PRIOR_ART.md). Stryker was chosen for `killedBy`
attribution and does not deliver it here: the TAP runner is the only path for
`node --test` and reports one test per file, so every mutant returns
`killedBy: ["0"]`. Against the store's harness, adopting Stryker would **lose**
the attribution the store deliberately built. What Stryker still wins on is
breadth — 883 generated mutants against a dozen hand-written ones, which is how
the gutted-`withinSweep` hole was found at all — and safety, since it sandboxes
a copy rather than writing to the tree. The honest recommendation is both: keep
a small hand-written set for attribution on the mutations that matter, and run
Stryker for coverage of the ones nobody thought to write.
