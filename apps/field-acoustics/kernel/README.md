# `kernel/` — the acoustic propagation kernel, in TypeScript

A dependency-free TypeScript port of the propagation core in `dcisim/`
(`engine.py`, `atmosphere.py`, `directivity.py`, plus the geometry and
instrument definitions it needs), restructured for the browser, with a Web
Worker wrapper so a whole show can be computed off the main thread.

Nothing in `app/` or `dcisim/` was modified. The repository's root `.gitignore`
picked up two lines (`kernel/dist/`, `kernel/node_modules/`); that is the only
change outside this directory.

---

## Why this exists, and why it is TypeScript

The browser-stack spike (`spike-browser-stack.md`) measured four implementations
of this kernel. Three of its findings drove every decision here:

1. **The workload is transcendentals, not flops.** Per (source, receiver, band)
   the model evaluates `log10` and `10^x`, plus an `acos` per (source, receiver).
   Replacing those with cheap stand-ins gave a 4.07x ceiling — roughly
   three-quarters of the runtime.
2. **Most of that ceiling is reachable by algebra, without changing the
   physics.** See below.
3. **WASM was not worth it.** A literal Rust→wasm port was *slower* than plain
   JavaScript in-browser (64.0 ms vs 62.9 ms), and `simd128` measured zero
   benefit three separate ways. So: TypeScript, no wasm, no Rust, no bundler.

The spike also established that `SharedArrayBuffer` is unavailable without
COOP/COEP, that COOP/COEP is not available on a plain static host, and that this
kernel does not need it — it is an embarrassingly parallel reduction, so workers
can own private buffers and transfer them back.

## The restructuring

```
10^((Lw + D(theta,f) - 20*log10(r) - 11 - alpha(f)*r) / 10)
  ==  P_lin * G_lin(cos theta) * 10^-1.1 * r^-2 * exp(-alpha*r*ln10/10)
```

* `log10` cancels against `10^x` outright, leaving `r^-2`.
* `D(theta) = 20*log10(amp) + DI`, so `10^(D/10) = amp^2 * 10^(DI/10)`. The
  directivity table is therefore stored **pre-squared**, and `DI` is folded into
  a per-source constant. No logarithm survives.
* The directivity table is indexed by **`cos(theta)`**, not `theta`, which
  deletes the `acos`.
* `exp(-alpha*r*ln10/10)` becomes a per-band lookup table in `r`.

Both tables are **band-interleaved** (`table[j * 8 + b]`), so one lookup touches
two cache lines rather than sixteen. That layout is worth ~30% on its own and is
what makes a 16 384-point directivity table cost about what a 4 096-point
band-major one did.

Uniform-in-`cos` is a *better*-conditioned grid than uniform-in-`theta` near the
poles, not a worse one: the main lobe goes as `1 - (ka)^2*theta^2/8`, which is
linear in `cos(theta)` to leading order, and the rear taper is C1-flat at 180
degrees. The residual disagreement concentrates at the slope discontinuities of
the Python table (where `max(piston, floor)` engages), where it falls linearly
with the grid step.

## Measured results

Machine: this container, Node v22.22.2 (V8), x86_64,
`navigator.hardwareConcurrency` = 4. numpy 2.4.6 / scipy 1.17.1 / Python 3.11.15.

### Speed — 77 sources, 1640 receivers, 8 bands

That is `arcForm()`'s default corps (50 brass + 19 battery + 8 front ensemble)
and the default grandstand (41 seats across x 40 rows). Five bass drums radiate
from two heads apiece, so the kernel walks **82 lobes**; with the far-side
reflection on that is **2.15 M band evaluations per set**. Median of 25 runs,
each configuration **in its own process** (see below).

| configuration | reflection on | reflection off |
| --- | --- | --- |
| **shipping default** — cos 16384, abs 8192, f64 | **25.8 ms/set** | **15.1 ms/set** |
| cos 4096, abs 8192, f64 | 23.8 | 13.2 |
| cos 16384, abs 8192, f32 | 25.1 | — |
| cos 16384, `Math.exp` instead of the absorption table | 44.1 | — |
| cos 65536, abs 8192, f64 | 34.7 | — |
| naive baseline — same layout, `acos` + `log10` + `exp` | 152.9 | 99.1 |
| **speedup, default vs naive** | **5.9x** | 6.6x |

A 100-set show is **2.6 s** single-threaded in Node, before any worker pool.
Across the pool (24 sets, batch of 3, same grid):

| workers | ms/set wall |
| --- | --- |
| 1 | 33.5 |
| 2 | 18.9 |
| 4 | 17.0 |
| 8 | 15.9 |

Sublinear, and the spike said to expect exactly this shape (it measured 35.8 /
16.8 / 19.0 / 15.0 ms for 1 / 2 / 4 / 8 workers). This box reports 4 logical
cores, the reduction is memory-bound, and `postMessage` overhead is significant
against a ~26 ms task even batched. **2 workers is where most of the win is.**
Reproduce with `npm run bench:pool`.

The first job in a fresh worker also pays ~70 ms to build the directivity and
cos tables for all eight instruments. That is once per worker, not once per set,
and `pool_bench.mjs` warms each worker before timing so it is not charged to the
first set — but it is real, and a UI that spawns a pool on demand will feel it.

**Benchmark methodology note, which turned out to matter more than expected.**
Timing every configuration in one process understated the default by ~30%
(31 ms rather than 26 ms). `Float64Array` and `Float32Array` tables both flowing
through `accumulatePath` make the inner loop polymorphic, and V8 does not
recover the monomorphic code once it has seen both. `test/bench.mjs` therefore
runs each case in its own process. **This is a deployment hazard, not just a
benchmarking one**: pick one `tablePrecision` per process and stay with it.

Three notes on the baseline, because the ratio is only meaningful with them:

* `test/naive_kernel.mjs` is structurally identical to the shipping kernel —
  same flat typed arrays, same interleaved table, same loop nest, same outputs —
  and differs *only* in evaluating the equation as written. It agrees with the
  shipping kernel to 2.6e-5 dB, so the ratio compares two implementations of the
  same computation.
* It uses `Math.exp(lp * ln10/10)` rather than `Math.pow(10, lp/10)`. V8's
  `Math.pow(10, x)` is 4.7x slower than `Math.exp` (79 ns vs 17 ns, measured), so
  a baseline that used `pow` — which is what the Python literally says — would
  have inflated this speedup to about 10x. The baseline gets the benefit of the
  doubt.
* `test/reference_kernel.mjs` runs at 719 ms/set. It is the *correctness*
  reference, written for legibility, and allocates per evaluation. It is not a
  performance baseline and is not quoted as one.

### Correctness — differential against the Python implementation

`test/gen_reference.py` runs `dcisim` over 41 cases: 24 randomised ensembles
(3–45 performers, instruments drawn from the whole catalog, **unnormalised**
facing vectors with magnitudes from 3e-6 to 250, all four facing modes, battery
pinned front or not, randomised stadium geometry and absorption, temperature
−5…42 °C, humidity 2…98 %, pressure 80…106 kPa, reflection on and off), plus
deterministic edge cases (single source inverse-square, two-lobe bass drums,
pit-only, empty ensemble, block and arc forms in both facings, an unreachable
far side, a perfectly absorptive far side) and two ground-effect cases.
Receivers are a deliberately nasty mix: grandstand seats, on-field points among
the players, points behind the far-side plane, points inside `MIN_RANGE_M` of a
bell, and points 200 m out. 49 536 receiver-band values in total.

| implementation | max level error | rms | max arrival error |
| --- | --- | --- | --- |
| `literal` — unrestructured transcription | **5.0e-13 dB** | 6.2e-15 dB | 1.8e-12 ms |
| `fine` — cos 131072, abs 131072 | 1.2e-4 dB | 6.0e-7 dB | 3.9e-5 ms |
| **`f64` — shipping default** (cos 16384, abs 8192) | **1.4e-4 dB** | 2.4e-6 dB | 7.6e-5 ms |
| `f32` — same tables in Float32 | 1.4e-4 dB | 2.4e-6 dB | 7.6e-5 ms |
| `coarse` — cos 4096, abs 8192 | 1.3e-3 dB | 1.2e-5 dB | 2.0e-4 ms |

Read that table top-down, because the two rows answer different questions.

**The `literal` row is the correctness result.** `test/reference_kernel.mjs` is
an independent, deliberately slow transcription of `dcisim/engine.py:path()`
that evaluates the same `acos`/`log10`/`10^x`. It agrees with numpy to
**5.0e-13 dB**, which is summation order and nothing else. That establishes that
the *port* is faithful; every row below it measures what the *restructuring*
costs on top of a correct port.

**The shipping default costs 1.4e-4 dB**, better than the 2.4e-4 dB the spike
budgeted. It is also within a factor of 1.2 of the `fine` row, which is the floor:
that residual is the Python model's own 721-point theta grid, whose piecewise
linear interpolation this kernel does not reproduce exactly under the `cos`
reparameterisation. Going finer than 16384 does not help.

Isolated probes, checked separately so a disagreement can be located:

| probe | agreement |
| --- | --- |
| `besselJ1` vs `scipy.special.j1`, x ∈ [0, 25] | 4.5e-12 absolute |
| `speedOfSound` | exact |
| `absorptionCoefficients` | 2.0e-16 relative |
| directivity index, 8 instruments x 2 temperatures | 9.8e-15 dB |
| directivity amplitude table, 7808 samples | 8.9e-16 relative |

### Float64 vs Float32 — measured, and the answer is f64

`tablePrecision: 'f32'` halves the tables' footprint and changes the differential
result in the fifth significant figure (1.371e-4 dB either way, i.e. the
resampling error swamps it completely). Measured in isolation it is **25.1 vs
25.8 ms/set — inside the run-to-run noise.** Every read of a `Float32Array`
costs a widening conversion in V8, which cancels the better cache residency at
these table sizes.

So f32 buys nothing here, exactly as `simd128` bought nothing in the spike. f64
is the default; f32 stays available for memory-constrained callers and is
documented as measured-no-benefit rather than quietly dropped. Do not mix the
two in one process — see the polymorphism note above.

The one table-size knob that *does* matter is `cosTableSize`. 16384 costs 8%
over 4096 and buys an order of magnitude of accuracy (1.4e-4 vs 1.3e-3 dB), which
is why it is the default; 65536 costs another 35% and buys nothing, because the
Python reference's own grid is the floor by then.

## Layout

```
src/
  numeric.ts       linspace / geomspace / trapezoid / interp, reproducing the
                   exact numpy routines the Python model depends on
  bessel.ts        J1: power series below 15, optimally-truncated Hankel
                   asymptotic above
  atmosphere.ts    ISO 9613-1 absorption, speed of sound, bands, A-weighting
  directivity.ts   piston + sidelobe floor + rear taper; the theta-indexed table
                   and its cos-indexed, pre-squared, band-interleaved kernel form
  instruments.ts   the catalog, with per-instrument directivity memoisation
  field.ts         stadium geometry, seat grid, far-side plane
  drill.ts         Performer, applyFacing, blockForm, arcForm
  engine.ts        simulate() — the hot loop
  protocol.ts      the job/result wire types
  workerCore.ts    the worker's message handler, testable without a thread
  worker.ts        worker entry point (browser Worker or node:worker_threads)
  pool.ts          WorkerPool
test/
  gen_reference.py  runs dcisim, writes reference.json
  differential.mjs  replays it through five kernel configurations
  reference_kernel.mjs  the literal transcription (correctness reference)
  naive_kernel.mjs      the unrestructured kernel (performance baseline)
  invariants.mjs    the load-bearing tests from test_dcisim.py, ported
  worker.mjs        worker protocol + pool
  bench.mjs         the 77 x 1640 x 8 benchmark, one process per case
  pool_bench.mjs    worker-pool scaling over a 24-set show
  run.mjs           invariants + worker + differential
```

## Build

```
npm run build      # tsc -> dist/*.js + dist/*.d.ts, plain ES modules
```

**No bundler, and zero runtime dependencies.** `package.json` has an empty
`dependencies`; the only `devDependency` is `typescript` itself, which is a
compiler, not a bundler — it emits one `.js` per `.ts` and leaves import
specifiers alone. `moduleResolution` is `NodeNext`, which *requires* explicit
`./x.js` specifiers, so the emitted `dist/` loads directly from a static host,
from Node, and from a module worker with no resolution step and no import map.

**One thing for the reviewer to decide:** `kernel/dist/` is currently in the
repo's `.gitignore`, so consuming this from `app/` — which is plain ES modules
with no build step of its own — means someone has to run `npm run build` first.
The spike's argument for TypeScript over Rust was that contributors should not
need a toolchain; committing `dist/` would apply that argument one level down.
It is a two-line `.gitignore` change either way, and it is not mine to make
unilaterally, so it is flagged rather than done.

`test/reference.json` is a 3.8 MB generated artifact (it is `dcisim`'s own
output for 41 cases). It regenerates in 4 seconds from `gen_reference.py`, so
there is a reasonable case for gitignoring it too — at the cost of making the
differential test require a working Python environment rather than just Node.

The one place this could have gone wrong is the worker entry: it needs
`node:worker_threads` under Node and nothing at all in a browser. That import is
written with an indirect specifier inside a branch a browser never takes, which
also keeps `@types/node` out of the build.

## Test

```
python3 test/gen_reference.py   # needs numpy + scipy + dcisim on the path
npm test                        # invariants, worker protocol, differential
npm run bench
```

`npm test` reports the differential stage as *skipped*, not failed, if
`reference.json` is absent — the invariants and the worker protocol do not need
Python.

## Using it

```js
import { simulate, arcForm, applyFacing, seatGrid, DEFAULT_STADIUM, dba }
  from './kernel/dist/index.js';

const performers = applyFacing(arcForm(), 'center');
const { points } = seatGrid(DEFAULT_STADIUM);
const res = simulate(performers, points);   // Float64Array outputs, (nR x 8)
console.log(dba(res)[0]);
```

Off the main thread:

```js
import { WorkerPool } from './kernel/dist/index.js';

const pool = new WorkerPool({ size: 4, batchSize: 4 });
await pool.uploadReceivers('house', points);        // once per show, not per set
const results = await pool.run(sets.map((s, i) => ({
  id: i,
  performers: s,
  receiversRef: 'house',
  outputs: ['bandSpl', 'arrivalSpreadMs'],
})));
```

The protocol is described in `src/protocol.ts`. Three things it does on purpose:

* **Batches jobs per `postMessage`.** The spike measured dispatch overhead as
  significant against a ~25 ms task (4 workers gave ~2x, not 4x), so the unit of
  dispatch is a batch of sets.
* **Uploads the receiver grid once** under an id. A show reuses the same seat
  grid for every set; resending 1640x3 doubles per set is pure waste.
* **Transfers result buffers**, so nothing is copied on the way back. No
  `SharedArrayBuffer`, no COOP/COEP, no cross-origin isolation, works on GitHub
  Pages.

Worker results are bit-identical to in-process `simulate()` (verified in
`test/worker.mjs`, exact equality, not a tolerance).

## Provenance and known limitations, carried over unchanged

The Python model's own verdict on itself is **ASSUMED**, and this port does not
try to improve on it. Carried over faithfully, including:

* Instrument sound-power spectra are representative, not measured.
* The rear hemisphere is not physics; it is the 90-degree value carried to an
  asserted front-to-back ratio by a smoothstep in dB. The aperture correction in
  `effectiveRadius` is an empirical fit to three published directivity indices.
* The front ensemble is eight acoustic point sources on the sideline, not a PA
  model, and sits far closer to the stands than anyone on the field.
* Ground effect is off by default and is described in the Python source as
  "near common-mode here".
* The far-side grandstand is a single specular reflector with a geometric gate.
* No diffraction, no scattering, no ground impedance model, no source coherence.

Nothing in `dcisim/` was changed, and no bug was found that would justify
changing it.

## Where this port is not bit-for-bit, and why

Four deliberate divergences. All are measured above; none is a silent one.

1. **`cos(theta)` indexing** replaces `acos` + theta indexing. Costs 1.4e-4 dB
   at the default table size. This is the point of the exercise.
2. **The air-absorption lookup table** replaces `exp`. Its contribution is below
   the directivity table's; `absorptionTableSize: 0` removes it entirely for
   1.4x the runtime.
3. **Energy additivity across sections is no longer exact.** The absorption
   table's domain is sized from the bounding box of whichever sources are
   present, so a section and the whole ensemble quantise `r` slightly
   differently. Measured drift: ~3e-8 dB, against `np.allclose`'s effective
   ~7e-4 dB tolerance at these levels. `absorptionTableSize: 0` restores exact
   additivity. This is the one invariant the restructuring genuinely weakens,
   and it is called out in `test/invariants.mjs` rather than tuned around.
4. **Arrival variance is accumulated from raw moments** (`E[t^2] - E[t]^2`)
   rather than numpy's two passes, because a single pass is what a streaming
   kernel can do. To keep that conditioned, times are accumulated relative to a
   per-receiver origin — the flight time from the ensemble centroid — so the
   cancellation that would otherwise destroy a near-zero spread never happens.
   Measured agreement: 7.6e-5 ms.

Two smaller things worth knowing:

* **`besselJ1` is not scipy's cephes implementation.** It is a power series
  below x = 15 and an optimally-truncated Hankel asymptotic above, agreeing with
  scipy to 4.5e-12 absolute. The model only ever asks for x ≲ 17. Writing it out
  rather than transliterating cephes' rational-approximation coefficients keeps
  the file auditable and its accuracy claim testable.
* **The ground-effect term is deliberately *not* restructured.** It is the one
  term that depends on (source, receiver, band) jointly, it is off by default,
  and enabling it costs ~488 `cos` evaluations per (source, receiver) — it will
  dominate everything else in this file. It is ported for completeness and
  covered by two differential cases.

## What is not ported

The propagation kernel is here; the surrounding tooling is not, because it is
not part of the kernel and has no browser role:

* `dcisim/sofa.py` — the SOFA/HDF5 measured-directivity loader. `Instrument`
  keeps its `setMeasured()` / `clearMeasured()` API and `Directivity` keeps
  `fromMeasured()`, so a table loaded anywhere else drops straight in; nothing
  reads `.sofa` files in the browser.
* `dcisim/provenance.py`, `report.py`, `simulate.py` — reporting and CLI.
* `dcisim/drill.py`'s CSV load/save. `Performer`, `applyFacing`, `blockForm` and
  `arcForm` are ported because the invariants need them.

The corresponding tests in `test_dcisim.py` (SOFA round-trip, SOFA rejection,
measured-directivity provenance, citation enforcement, provenance-weakest-link,
CSV round-trip, malformed CSV) are therefore not in `test/invariants.mjs`. The
31 that are there cover every invariant that touches the physics.
