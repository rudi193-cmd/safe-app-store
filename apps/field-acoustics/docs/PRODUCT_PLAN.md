# Product plan

## What this is

A design-time acoustic check for marching drill. Not a simulator with a UI on it
— the value is *when* you get the number, not the number. Today a program finds
out its drill doesn't project at a full-ensemble run in July, when the drill is
written and the show is set. This moves that feedback to the moment the set is
written.

## Settled

| Decision | Choice |
| --- | --- |
| Audience | All marching programs — DCI through high school circuits |
| License | Apache-2.0 |
| Compute | In-browser, local-first |
| Core job | **Open** — larger than a single job-to-be-done; awaiting context |

The interaction layer is deliberately unplanned below. Everything else — engine,
data model, import, validation — is invariant across any version of the app, so
it can be built now without guessing.

## The problem nobody expects

**Drill files encode position, not facing.** Coordinate sheets give you
`Side 1: 4.0 steps inside 35, 8.0 steps behind front hash` for every performer at
every set. They do not tell you which way anyone is pointing.

Facing is the entire subject of this tool. A bell is 25 dB down at 8 kHz behind
the player; the difference between two drills at identical coordinates is
everything we are trying to measure. So the single most important data problem is
one the file formats do not solve.

Three ways to get facing, in descending order of fidelity:

1. **Explicit.** The designer annotates it. Accurate, and nobody will do it for
   500 performers across 80 sets.
2. **Inferred from motion.** Direction of travel between consecutive sets. Free,
   correct maybe 70% of the time, and wrong in exactly the interesting cases —
   backwards marching, slides, and anything where the body faces the box while
   the feet go elsewhere. Those are precisely the moments worth analysing.
3. **Assigned per block.** The designer paints facing onto groups of performers
   for a range of sets. A minute of work per phrase, not per performer.

The realistic answer is (2) as a default with (3) as the correction path, and the
UI making it obvious which performers are guessed versus confirmed. **This is
worth prototyping before anything else** — if facing capture is annoying, the
product does not work, no matter how good the physics is.

## Architecture

### One kernel, three targets

Port the propagation core from Python to **Rust**, compiled to:

- **WASM + SIMD** for the browser — the product
- **Native CLI** for batch work and regression testing
- **Python binding (pyo3)** so the existing research code and validation
  notebooks keep working against the same kernel

One implementation, one set of physics tests, three consumers. The alternative —
hand-porting the maths to TypeScript — means two implementations that will drift,
and drift here is silent wrong answers.

### Is it fast enough in a browser?

Per set: ~150 sources x ~2400 audience receivers x 8 bands ≈ 2.9M evaluations,
each a handful of flops plus a table lookup. That is milliseconds in WASM. A
100-set show is ~290M — low single-digit seconds single-threaded, well under a
second with SIMD and workers. Comfortable.

The kernel is a pure parallel reduction with no data dependencies, so a WebGPU
path is available later for whole-show scans. Do not start there: **the baseline
target is a school Chromebook**, and WebGPU coverage on those is not something to
bet the product on. WASM+SIMD everywhere, WebGPU as an opportunistic upgrade.

### Local-first, genuinely

- No accounts, no server, no upload. Static hosting; near-zero running cost,
  which matters for an Apache-2.0 project with no revenue.
- Shows persist in **OPFS**, import/export via the File System Access API where
  available, plain download/upload fallback elsewhere.
- Installable PWA with a service worker. Rehearsal sites have bad wifi and this
  needs to work at one.

Unreleased drill is competitive IP during a season. "Your show never leaves your
laptop" is a trust argument first and a cost argument second — and it is only
credible because the source is open and anyone can verify it.

## What "all marching programs" actually changes

Not a UI reskin. Three substantive extensions:

**Woodwinds.** High school bands are full of flutes, clarinets and saxophones,
and the current model has none. Woodwinds do not radiate from a bell — sound
leaves through open tone holes distributed along the body, so the pattern is
frequency-dependent in a completely different way and is far closer to
omnidirectional at low frequencies while beaming off the bell only for the lowest
written notes. The bell-piston model is simply the wrong shape for them and needs
a separate radiator model, not a re-parameterisation.

**Field and stadium geometry.** NFHS hashes sit 53'4" from the sideline; NCAA and
DCI use 60'. High school stands are shallower, lower, closer, often behind a
track, and frequently have no far-side grandstand at all — which the simulator
has already shown makes the penalty *worse*, since the far stands were quietly
backfilling lost energy. Venue presets have to span "Lucas Oil" to "small-town
bleachers on one side".

**Ensemble scale and step size.** 30 to 300 performers, 8-to-5 and 6-to-5, and
instrumentation that ranges from a full corps hornline to fourteen kids and a
sound system.

## Phasing

**Phase 0 — Facing capture prototype.** Throwaway UI, no physics. Load real
coordinate sheets, infer facing from motion, let someone paint corrections, and
find out how long it takes to get a real show to "facing is right". This is the
existential risk; test it first and cheaply.

**Phase 1 — Kernel port + import.** Rust kernel with the Python physics tests
carried over as the regression suite. Coordinate-notation parser (the
`4.0 steps inside 35` grammar is self-contained and format-independent). CSV and
coordinate-sheet import. Native CLI so it is useful before any UI exists.

**Phase 2 — Validation.** See below. Non-negotiable before promotion.

**Phase 3 — The app.** Interaction layer, once the core job is settled.

**Phase 4 — Woodwinds and venue library.** The work that makes it genuinely
usable outside drum corps.

**Later — Auralization.** Dry stems filtered through the model, A/B in
headphones. This is what actually convinces staff, and it is a much bigger lift
than it looks: it needs source material, per-source FIR convolution, and careful
handling so the demo is honest rather than flattering.

## Measured directivity, and a licence that decides it for us

The model's single most load-bearing input is the rear-hemisphere front-to-back
ratio, because turning a form inward puts most of the hornline behind 90 degrees.
It is currently asserted. Replacing it with measurement is the highest-value
improvement available, and it is available now — the data exists and is open.

But the two comprehensive databases have incompatible terms, and this decides
the architecture rather than merely informing it:

| Source | Licence | Usable here |
| --- | --- | --- |
| [BYU Spatial Audio Library](https://scholarsarchive.byu.edu/directivity/) | CC BY 4.0 | **Yes.** Attribution only, commercial use permitted, compatible with Apache-2.0. Covers trumpet, tuba, euphonium, flute. |
| [TU Berlin](https://arxiv.org/abs/2307.02110) | CC BY-NC-SA | **No.** The non-commercial clause propagates to every downstream user, including programs that pay for things. 41 instruments, and none of them reachable. |

So the tool **ships a loader and no data**. The AES69 (SOFA) reader is in the
repo, Apache-2.0, tested against a synthesised file whose response can be
written down rather than against an opaque fixture. Users point it at whatever
they hold. This keeps the licence clean and, usefully, means the same code path
serves a program that has commissioned its own measurements.

The BYU flute data also opens the woodwind problem earlier than planned — that
was Phase 4 on the assumption of building a new radiator model from scratch.
Measured data for one woodwind is worth more than a model for all of them.

## Provenance as the credibility architecture

The risk this plan named first was: one number a caption head disagrees with and
the tool is dead permanently. The mitigation was field validation, which is
still right and still slow. There is a cheaper half that ships immediately.

Every input carries a state — measured, fitted, or assumed — and every result is
worth its weakest input. `--provenance` prints it. Right now the honest verdict
on the headline number is ASSUMED, limited by four inputs, and the tool says so
rather than presenting three significant figures and hoping.

This is deliberately a trichotomy and not a confidence score. A number is not
70% verified. It traces to something a person can look up, or it does not.

Two reasons this matters more than it looks:

1. **It converts the credibility risk into a work list.** "Limited by: battery
   carry angles, grandstand absorption, instrument sound powers, rear
   front-to-back ratios" is a roadmap, and each item that moves from assumed to
   measured is visible progress a customer can audit.
2. **It survives contact with a sceptic.** A caption head who disagrees with a
   number can be shown exactly which input is carrying it. That is a much better
   conversation than defending a black box, and it is the difference between
   "your model is wrong" and "your snare angle is wrong, here is the right one."

The audits are why this exists rather than being a nicety. Two independent
reimplementations verified the propagation core to 1e-14 dB, and the published
results were still wrong — every defect was an unverified input, not a bug.
A test suite cannot catch that class of error. Provenance can at least refuse to
hide it.

## Validation, which is the whole ballgame

The model is currently calibrated against published directivity indices and
plausible sound power levels. That is enough for a research tool and **not enough
to tell a caption head their drill is wrong.** One number a staff disagrees with
and the tool is dead permanently.

So, before promoting it anywhere:

- **Field measurement.** Partner with two or three programs. Calibrated SPL
  meters at known seats, per-octave-band capture during a full run, compared
  against prediction for the same set. Publish everything, including where the
  model missed.
- **Single-instrument directivity.** Measure a few real marching instruments on a
  turntable outdoors. Replaces the fitted aperture correction with measured data
  for the instruments that matter most.
- **Open data.** Measurements and comparison notebooks in the repo. With
  Apache-2.0, "check the physics yourself" is a real invitation, and it is the
  main thing that will earn trust with technically-minded staff.

The honest framing throughout: this predicts *differences between design options*
far better than it predicts absolute levels, because most calibration error is
common to both options and cancels. Lead with that. It is both true and the more
useful claim.

## Risks

| Risk | Mitigation |
| --- | --- |
| Facing capture is too tedious to be used | Phase 0, before anything else is built |
| One wrong number destroys credibility | Field validation before promotion; publish misses |
| Tool moralises about drill written for visual reasons | Report, never prescribe. Acoustics is one input among many and the designer outranks it |
| Apache-2.0 lets anyone commercialise it | Accepted and intended — adoption over capture |
| Seasonal usage, dead half the year | No servers, so idle costs nothing |
| Chromebook performance | WASM+SIMD baseline, WebGPU only as an upgrade |

## Open questions

1. **The core job.** Awaiting your context — it determines the entire interaction
   layer and nothing above it.
2. **Who writes the drill in your target programs?** Staff, freelance designer,
   or purchased pre-written show? Changes who the user is and whether import is
   from their own file or a PDF someone sent them.
3. **Governance.** DCO sign-off or a CLA, and whether this lives under your name,
   a neutral org, or eventually a foundation.
4. **Does it need the score at all?** Everything so far assumes a uniform
   fortissimo. Real dynamics and orchestration would improve realism a lot and
   pull in MusicXML — a big scope increase, possibly a large payoff.
