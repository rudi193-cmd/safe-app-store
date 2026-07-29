# field-acoustics

A design-time acoustic model for marching drill. It answers one question with
numbers instead of opinions:

> What actually changes in the audience when the ensemble stops facing the front
> sideline and turns in to face the middle of the field?

Same coordinates, same players, same dynamic. Only the bells move.

Two implementations of the same physics — Python for analysis and validation,
TypeScript for the browser — held to each other by a differential suite.

```bash
pip install -r requirements.txt    # numpy, scipy, matplotlib
python simulate.py                 # default corps, arc form
python simulate.py --sections      # per-section breakdown
python simulate.py --provenance    # where every number came from
python -m pytest tests/ -q         # 38 invariants
```

Full detail on the model, including everything it does *not* do:
**[`dcisim/README.md`](dcisim/README.md)**.

---

## Why this exists

Every drill design tool in the category models visuals. Pyware's Virtual Clinic
runs four analyzers — strides, collisions, direction changes, inconsistencies —
and all four are visual. Nothing anywhere models what the drill *sounds like*
from the stands.

The closest adjacent product is CruSync, which serves the A1 running the PA:
SPL at listening zones and per-performer speaker delay, from an inverse-square
fit to a reference measurement. No directivity, no facing, no air absorption.
Different product, different user, and a plausible partner rather than a
competitor.

The value is *when* you get the number, not the number. Today a program finds
out the drill doesn't project at a full-ensemble run in July, when the drill is
written and the show is set. This moves that feedback to the moment the set is
written.

## The model

For every (performer, receiver) pair, per octave band from 63 Hz to 8 kHz:

```
Lp = Lw + D(theta, f) - 20*log10(r) - 11 - alpha(f)*r
```

summed on an energy basis, because independent players are mutually incoherent.

Directivity is a band-averaged circular-piston term with a sidelobe floor and a
rear taper, with the physical bell radius mapped through a fitted
frequency-dependent effective aperture — a flat piston is the wrong model for a
flaring bell. Atmospheric absorption is ISO 9613-1, so it responds to
temperature and humidity. The far-side grandstand is one specular image source
with per-band absorption, geometrically gated.

## Every number carries its provenance

```bash
python simulate.py --provenance
```

Every input is in exactly one of three states, and a result is worth its weakest
one:

```
  ! assumed   rear front-to-back ratios
  ~ fitted    trumpet directivity  [Meyer, brass directivity indices]
  * measured  atmospheric absorption  [ISO 9613-1:1993]

This result is ASSUMED -- no stronger than its weakest input.
```

**This is not a confidence score, and that is the point.** A number is not 70%
verified; it either traces to something a person can look up or it does not, and
blurring that into a percentage is how an unsupported figure ends up in a room
full of caption heads. One `assumed` input anywhere sinks the whole result,
however many measured terms sit beside it.

The current headline is `ASSUMED`, because the rear hemisphere rests on an
asserted front-to-back array — and turning the form in puts most of the hornline
into exactly that region. Replacing it with measured directivity is the single
highest-value improvement available. The loader is already there; see
[Loading measured directivity](dcisim/README.md#loading-measured-directivity).
BYU's library is CC BY 4.0 and compatible; TU Berlin's is CC BY-NC-SA and
deliberately unsupported as a bundled source, because the non-commercial clause
would propagate to programs that pay for things.

## Validation

`python -m pytest tests/ -q` runs 38 invariants rather than golden numbers, so they
stay meaningful when the inputs change. The load-bearing one:

**Radiated power must match the declared `Lw`.** Intensity is integrated over a
sphere around a single trumpet and has to recover the sound power the model was
handed. This catches the subtle way to get directivity wrong — normalising the
pattern to 0 dB on axis rather than to the sphere average leaves the beam shape
looking perfect while quietly redefining `Lw` as on-axis level. Nothing visibly
breaks. The radiated spectrum just tilts by the directivity index, under a dB at
63 Hz and about 13 dB at 8 kHz, and every A-weighted number downstream inherits
the tilt.

That failure survived two independent reimplementations agreeing to 1e-14 dB
with each other, on the same wrong input. **Correct code over unverified inputs
produces confident wrong answers, and nothing in a test suite catches that** —
which is why provenance above is a first-class output rather than a footnote.

## The browser kernel — [`kernel/`](kernel/README.md)

The same physics in TypeScript, verified against the Python across five
differential tiers:

| Tier | Max level error |
| --- | ---: |
| literal | 4.97e-13 dB |
| fine | 1.18e-4 dB |
| f64 | 1.37e-4 dB |
| f32 | 1.37e-4 dB |
| coarse | 1.27e-3 dB |

25.8 ms per set; a 100-set show in 2.6 s single-threaded.

```bash
cd kernel
npm install && npm run build
npm test                      # invariants + worker pool
npm run test:differential     # regenerates the reference from Python, then compares
```

`kernel/test/reference.json` is generated (3.7 MB) and not committed. `npm test`
skips the differential tier cleanly when it is absent; `npm run
test:differential` regenerates it in seconds. Generating it needs the Python
side installed, which is the point — the reference *is* the Python.

Rust→wasm was built and measured, and was **slower** than JS in-browser; SIMD
produced binaries differing by one byte. The win was algebra, not language.

## Using your own drill

`--drill mydrill.csv` takes a CSV of `instrument, x_ft, y_ft` with optional
`face_x, face_y`. `out/drill_forward.csv` and `out/drill_center.csv` are written
in exactly that format, so run once and use them as templates.

**Facing is applied by the simulator, not read from the file.** You supply
coordinates; the counterfactual is set, not recovered. Drill files encode
position and not facing, and inferring it from travel direction produces errors
that are ensemble-correlated and therefore do not average away.

## Status

Playground. Contested tier, not canonical, not promoted — scoped to its own SOIL
collection (`field_acoustics_*`) with no fleet-store writes.

The physics is validated; the headline result is honest about resting on one
assumed array. Field measurement against real programs — published including
where the model missed — comes before any number goes to a caption head.

Unlike the stdlib-only [`marching-arts`](../marching-arts) core, the Python side
here carries numpy, scipy and matplotlib. The TypeScript kernel under `kernel/`
has no runtime dependencies at all, which is the half that has to run in a
browser.

## Where this sits

`marching-arts` is the platform — storage, authorization, consent, transport.
This is one capability that will sit on it, and P5 of that build's
[`docs/BUILD_PLAN.md`](../marching-arts/docs/BUILD_PLAN.md) is where it lands.
Nothing here depends on that build, and nothing there depends on this one yet.

## Licence

Apache-2.0.
