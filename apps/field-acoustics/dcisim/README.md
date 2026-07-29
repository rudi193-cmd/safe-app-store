# dcisim

A field-acoustics simulator for marching-arts drill design. It answers one
question with numbers instead of opinions:

> What actually changes in the audience when the ensemble stops facing the front
> sideline and turns in to face the middle of the field?

Same coordinates, same players, same dynamic. Only the bells move.

```
python simulate.py                       # default corps, arc form
python simulate.py --form block
python simulate.py --drill mydrill.csv   # your real coordinates
python simulate.py --sections            # per-section breakdown
python -m pytest tests/ -q               # invariants
```

Outputs land in `out/`: a text summary, a plan view of the drill with bell
arrows, three heat maps over the grandstand, and octave-band spectra at four
reference seats.

## The result, with the default corps in an arc

```
Across all seats:
  dBA          mean   -3.1   min   -3.8   max   -1.8
  brightness   mean   -1.5   min   -2.0   max   -0.2   (HF/LF energy ratio, dB)

Per octave band, mean change across all seats (dB):
              63     125     250     500      1k      2k      4k      8k
            -0.2    -0.6    -1.3    -2.5    -3.4    -3.4    -2.6    -1.6
```

Three things worth knowing before you write the drill:

**The loss is broadband with a midrange peak, not a treble cliff.** The bottom
octave is untouched and the top two suffer less than the middle, because there
is a limit to how dark a bell can get: behind the player the response bottoms out
at the instrument's front-to-back ratio rather than continuing to fall. So the
worst of it lands at 1-2 kHz — the region carrying weight and presence rather
than edge. Overall brightness drops 1.5 dB. That is audible, but it is a good
deal milder than "you lose the top end", which is what a model without a
physical rear limit will tell you.

**The hornline penalty depends on where you sit across the stands, not how high.**
Hornline alone, the low corners lose about 4 dB and dead centre loses about 7 —
the corners were already hearing the horns well off-axis, so they had less
on-axis energy to lose, and the turned-in bells actively spray more toward them.
That gradient is real drill physics.

The *height* gradient in the headline numbers is not. Hornline alone, row 0 and
row 39 differ by 0.27 dB — nothing. The 1.6 dB row gradient in the full-ensemble
figures comes almost entirely from the front ensemble sitting on the sideline
and diluting the loss more in the near rows than the far ones. That is an
artefact of modelling the pit as eight point sources rather than a PA, so do not
read a "judges get the worst of it" conclusion out of it.

**The wash is real and it is late.** Energy-weighted arrival spread goes from
28 ms to 51 ms, and the far-side grandstand reflection climbs from 25 dB below
the direct sound to 16 dB below it. That is the actual mechanism behind the
"sounds huge on the field, disappears in the stands" complaint: you are trading
direct sound for a delayed, diffuse return. Turning that reflection off
(`--no-reflection`) makes the penalty *worse*, from -3.1 to -3.3 dBA on average:
the far stands are quietly backfilling some of what the turn-in throws away. In
a venue with no far-side grandstand, expect the turn-in to cost slightly more
than these numbers say.

The per-section breakdown shows where the cost actually falls:

```
  trumpet         16       85.6       79.8      -5.8       -4.9
  mellophone      12       82.9       76.8      -6.2       -5.7
  baritone        14       82.2       76.6      -5.6       -5.9
  contra           8       77.6       72.5      -5.0       -5.3
  snare            9       81.6       81.6      -0.0       +0.3
  bass             5       68.3       68.3      +0.0       +0.1
  pit              8       81.5       81.5      +0.0       +0.0
```

It is entirely a hornline effect. The battery barely registers, for two reasons
worth knowing: a modern marching snare is carried nearly flat, so its radiating
axis is close to vertical and turning the player hardly changes what reaches the
audience; and a bass drum radiates from both heads, so rotating it 180 degrees
swaps two opposed lobes and changes almost nothing.

An earlier version of this file claimed bass drums get meaningfully *louder*
when the form turns in. They do not. The effect is about +0.04 dB for a centred
bass line, it lives in octaves where a bass drum has little output anyway, and
the section is well under 1% of the ensemble's A-weighted energy. The larger
number that claim was based on turned out to be reporting how far off centre the
default bass line had been placed, not anything about drums.

## What the model does

For every (performer, receiver) pair, per octave band from 63 Hz to 8 kHz:

```
Lp = Lw + D(theta, f) - 20*log10(r) - 11 - alpha(f)*r
```

summed on an energy basis, because independent players are mutually incoherent.

- **Directivity** `D(theta, f)` is a band-averaged circular-piston term with a
  sidelobe floor and a rear taper. A flat piston is the wrong model for a
  flaring bell, so the physical bell radius is mapped through a fitted
  frequency-dependent effective aperture. The fit reproduces published
  directivity indices for trumpet, mellophone and contra to about 0.8 dB RMS
  across all eight bands — check it any time with `python -m dcisim.directivity`.
  This is the part that matters: the whole question is what happens behind a
  bell, so the back hemisphere is pinned to measured front-to-back ratios rather
  than left to whatever a piston formula happens to produce.
- **Air absorption** is ISO 9613-1, so it responds to temperature and humidity.
  A dry, hot day costs high frequencies noticeably more over a 100 m throw; try
  `--temp 33 --humidity 30`.
- **The far-side grandstand** is modelled as a single specular image source with
  per-band absorption, geometrically gated so it only contributes where the ray
  actually strikes the reflector. This is on by default because it is a large
  part of what changes when you turn the form around; `--no-reflection` isolates
  the direct sound.
- **Geometry** is a standard field in feet — 0 at the 50, front sideline at
  y = 0, college hashes at 60 and 100 — with a raked grandstand along the front.

## Checking it yourself

`python -m pytest tests/ -q` runs 38 invariants rather than golden numbers, so they
stay meaningful when you change the inputs. The load-bearing ones:

- **Radiated power matches the declared `Lw`.** Intensity is integrated over a
  sphere around a single trumpet and has to recover the sound power the model
  was handed, to within the air absorption over that sphere. This is the test
  that catches the subtle version of getting directivity wrong: normalising the
  pattern to 0 dB on axis rather than to the sphere average leaves the beam
  shape looking perfect while quietly redefining `Lw` as on-axis level. Nothing
  visibly breaks -- the radiated spectrum just tilts by the directivity index,
  under a dB at 63 Hz and about 13 dB at 8 kHz, and every A-weighted and HF/LF
  number computed downstream inherits the tilt.
- **The rear response never dips below the stated front-to-back ratio.** It is
  supposed to be pinned to that ratio; an earlier construction tapered the
  sidelobe floor along with everything else and let the response dive up to
  12 dB past it before climbing back. The directivity-index calibration was
  blind to it — DI moved under 0.1 dB — and it was not common-mode: facing
  front, no brass path lands in that angular window; facing center, about 40%
  of them do. It was worth roughly 1.4 dB of the reported high-frequency loss.
- **Sections sum energetically to the whole ensemble** (to 1e-14 dB).
- **Directivity indices track published brass values** to under 2 dB RMS.
- **The reflection can only ever add energy**, vanishes when the reflector is
  made fully absorptive, and vanishes when it is moved away.
- **Inverse-square holds** to 0.15 dB over a 10 m to 20 m doubling.
- **A symmetric form produces a symmetric field**, in both facings.
- **Amplified and omnidirectional sources are facing-independent**, which is the
  null case the whole experiment is measured against.

## Where every number came from

```
python simulate.py --provenance
```

Every input is in one of three states, and results carry the weakest one:

```
  ! assumed   rear front-to-back ratios
  ~ fitted    trumpet directivity  [Meyer, brass directivity indices]
  * measured  atmospheric absorption  [ISO 9613-1:1993]

This result is ASSUMED -- no stronger than its weakest input.
```

This is not a confidence score, and that is the point. A number is not 70%
verified; it either traces to something a person can look up or it does not, and
blurring that into a percentage is how an unsupported figure ends up in a room
full of caption heads. One `assumed` input anywhere sinks the whole result,
however many measured terms sit beside it.

The audits are the argument for this. The propagation core was verified correct
to 1e-14 dB against two independent reimplementations, and the results were
still wrong — because a directivity floor was asserted instead of measured,
because a snare carry angle was guessed at 45 degrees when the real one is near
80, because a bass line sat off centre and its asymmetry got read as a finding.
Correct code over unverified inputs produces confident, wrong answers, and
nothing in a test suite catches that.

### Loading measured directivity

The tool reads AES69 (SOFA) directivity files and **ships no data**:

```
python simulate.py --sofa trumpet byu_trumpet.sofa \
                   --cite "Bellows et al., BYU Spatial Audio Library (CC BY 4.0)"
python -c "from dcisim.sofa import describe; print(describe('byu_trumpet.sofa'))"
```

A citation is required, not optional. Measured data whose source nobody can
check is not meaningfully better than a fitted curve.

Two databases cover the instruments that matter, and only one of them is usable
here:

- **[BYU Spatial Audio Library](https://scholarsarchive.byu.edu/directivity/)** —
  trumpet, tuba, euphonium, flute and more, high-resolution spherical, including
  musician diffraction. BYU ScholarsArchive Data defaults to **CC BY 4.0**:
  attribution only, commercial use permitted, compatible with this project's
  Apache-2.0 licence. This is the one to use.
- **[TU Berlin](https://arxiv.org/abs/2307.02110)** — 41 instruments, 32-channel
  spherical array. Released **CC BY-NC-SA**. The non-commercial clause would
  propagate to anyone using this tool, including programs that pay for things,
  so it is deliberately unsupported as a bundled source. You can still point the
  loader at it for your own non-commercial work; that is your call to make, not
  a default this project ships.

Reading SOFA needs `h5py` (`pip install h5py`). The analytic model works
without it.

One thing the loader discards on purpose: the engine's directivity is
axisymmetric about the bell axis, so measured data is averaged over azimuth at
each polar angle. Real instruments are not axisymmetric — the player's body is
on one side of the bell. `describe()` reports how much asymmetry was thrown
away so you can judge whether it mattered for your case.

## Using your own drill

`--drill mydrill.csv` takes a CSV with `instrument, x_ft, y_ft` and optional
`face_x, face_y`. `out/drill_forward.csv` and `out/drill_center.csv` are written
in exactly that format, so run once and use them as templates. Instrument names
come from `dcisim.instruments.CATALOG`.

The facing experiment is applied by the simulator, not read from the file, so
you only need to supply real coordinates. `--focus X Y` points the ensemble at
something other than the middle of the field; `--battery-front` keeps the
battery out while the horns turn in, which is what most shows would actually do.

## What it does not model

Worth knowing before you quote a number at anyone:

- **The rear hemisphere rests on an assumed number.** Behind about 90 degrees
  the response is carried down to a per-band front-to-back ratio that is
  asserted in `directivity.py`, not measured. Since turning in puts most of the
  hornline into exactly that region, the headline result is more sensitive to
  that one array than to anything else in the model. Replacing it with measured
  directivity data is the single highest-value improvement available.
- **The front ensemble is eight point sources on the sideline, not a PA.** It is
  much closer to the stands than anyone on the field, so it carries a
  disproportionate share of the near-row level and produces a height gradient
  that looks like a drill effect and is not one.
- **The ensemble does not shadow itself.** Seventy-plus bodies stand on the
  field and sound passes through all of them unimpeded. In the turned-in
  configuration the energy has to cross the form to reach the audience, so the
  real penalty is probably somewhat larger than reported.
- **No transient content.** This is a steady-state octave-band power sum. It
  says nothing directly about attack or articulation, whatever the temptation to
  read that into a high-frequency number.
- **Sound powers are representative, not measured.** They are calibrated so a
  full corps lands around 98 dBA in the low rows at realistic distances, which
  is where measurements of the activity sit, but they are not your ensemble.
  The default instrumentation is also about half the size of a full corps.
  Override `power_db` in `dcisim/instruments.py` if you have real data. The
  *differences* the simulator reports are far more trustworthy than the absolute
  levels, because most calibration error is common to both configurations.
- **No ensemble coherence.** Players are summed as incoherent sources. Real
  unisons partially correlate, which would raise both configurations similarly.
- **One reflection, no reverberation.** Real stadiums have a press box, a bowl,
  and a roof line. Only the far-side grandstand is modelled, as a single
  specular image with no diffusion.
- **Ground effect is off by default** (`--ground-effect` enables it). The
  two-path soft-ground term is approximate, and it is very nearly common-mode
  between the two configurations, so leaving it out keeps the comparison clean
  rather than hiding anything.
- **Static snapshot.** No motion, no Doppler, no phasing of a moving form.
- **No wind**, which on a real show day can swamp several dB of this.
- Directivity is axisymmetric about the bell axis; real players have a body on
  one side of it.
