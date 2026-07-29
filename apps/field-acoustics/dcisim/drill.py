"""Performer placement and facing.

A form is just a list of `Performer` records, so swapping in real drill means
writing a CSV with the same columns rather than touching any of the physics.
Use `load_csv` / `save_csv` for that.

Facing is stored as a unit vector in the field plane. `apply_facing` rewrites it
for the whole ensemble, which is the experiment this simulator exists to run:

    "front"   every performer faces the front sideline, bells into the house
    "center"  every performer faces the middle of the field
    "focus"   every performer faces an arbitrary point you nominate

Percussion can be pinned to front-facing independently, since in practice a
battery often stays out while the hornline turns in.
"""

import csv
from dataclasses import dataclass

import numpy as np

from .field import FIELD_CENTER, STEP_FT
from .instruments import CATALOG

# A representative modern corps: 50 brass, 19 battery, 8 amplified front ensemble.
DEFAULT_INSTRUMENTATION = [
    ("trumpet", 16),
    ("mellophone", 12),
    ("baritone", 14),
    ("contra", 8),
]
DEFAULT_BATTERY = [("snare", 9), ("tenor", 5), ("bass", 5)]
DEFAULT_PIT = [("pit", 8)]


@dataclass
class Performer:
    instrument: str
    x: float  # feet, 0 at the 50
    y: float  # feet, 0 at the front sideline
    fx: float = 0.0  # facing unit vector, field plane
    fy: float = -1.0

    @property
    def position(self):
        return np.array([self.x, self.y])

    @property
    def facing(self):
        return np.array([self.fx, self.fy])


def _normalize(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else np.array([0.0, -1.0])


def apply_facing(performers, mode="front", focus=FIELD_CENTER, battery_faces_front=False):
    """Return a new performer list with facing rewritten. Does not mutate."""
    out = []
    for p in performers:
        is_battery = p.instrument in ("snare", "tenor", "bass")
        if p.instrument == "pit":
            f = np.array([0.0, -1.0])  # amplified, always into the house
        elif mode == "front" or (battery_faces_front and is_battery):
            f = np.array([0.0, -1.0])
        elif mode in ("center", "focus"):
            f = _normalize(np.asarray(focus, dtype=float) - p.position)
        else:
            raise ValueError("unknown facing mode: %r" % mode)
        out.append(Performer(p.instrument, p.x, p.y, float(f[0]), float(f[1])))
    return out


def block_form(instrumentation=None, battery=None, pit=None,
               center=(0.0, 55.0), interval_steps=2.0, rows_spacing_steps=2.0,
               per_row=12):
    """A rectangular block centred upfield of the 50 -- the classic 'wall'.

    Sections are laid out front-to-back in score order, which puts trumpets at
    the front of the block and contras at the back.
    """
    # `is None`, not `or`: an empty list is a legitimate "no hornline" request,
    # and treating it as falsy silently conjures the full 50-piece default.
    instrumentation = DEFAULT_INSTRUMENTATION if instrumentation is None else instrumentation
    battery = DEFAULT_BATTERY if battery is None else battery
    pit = DEFAULT_PIT if pit is None else pit
    if per_row < 1:
        raise ValueError("per_row must be at least 1, got %d" % per_row)

    performers = []
    dx = interval_steps * STEP_FT
    dy = rows_spacing_steps * STEP_FT
    row = 0

    for name, count in instrumentation:
        placed = 0
        while placed < count:
            n = min(per_row, count - placed)
            xs = (np.arange(n) - (n - 1) / 2.0) * dx + center[0]
            y = center[1] + row * dy
            for x in xs:
                performers.append(Performer(name, float(x), float(y)))
            placed += n
            row += 1

    performers += _battery_line(battery, y=center[1] - 5 * dy, dx=dx)
    performers += _pit_line(pit)
    return apply_facing(performers, "front")


def arc_form(instrumentation=None, battery=None, pit=None,
             center=(0.0, 118.0), radius_ft=88.0, spread_deg=120.0,
             rank_spacing_ft=6.0, per_rank=18):
    """A concave arc opening toward the audience.

    This is the shape most likely to make 'everyone face center' sound like a
    good idea on paper, because the form is already curved around a focal point.
    """
    instrumentation = DEFAULT_INSTRUMENTATION if instrumentation is None else instrumentation
    battery = DEFAULT_BATTERY if battery is None else battery
    pit = DEFAULT_PIT if pit is None else pit
    if per_rank < 1:
        raise ValueError("per_rank must be at least 1, got %d" % per_rank)

    performers = []
    rank = 0
    for name, count in instrumentation:
        placed = 0
        while placed < count:
            n = min(per_rank, count - placed)
            r = radius_ft + rank * rank_spacing_ft
            # linspace of length 1 returns the *start* of the range, which would
            # strand a leftover single performer on the end of the arc.
            angles = (np.zeros(1) if n == 1 else
                      np.radians(np.linspace(-spread_deg / 2.0, spread_deg / 2.0, n)))
            for a in angles:
                x = center[0] + r * np.sin(a)
                y = center[1] - r * np.cos(a)
                performers.append(Performer(name, float(x), float(y)))
            placed += n
            rank += 1

    performers += _battery_line(battery, y=18.0, dx=2.0 * STEP_FT)
    performers += _pit_line(pit)
    return apply_facing(performers, "front")


def _battery_line(battery, y, dx, section_depth_ft=6.0):
    """Lay the battery out one centred rank per section.

    Laying every section end to end in a single rank instead puts the whole
    snare line on side 1 and the basses twenty-odd feet onto side 2. No corps
    does that, and the asymmetry leaks into results as if it were a finding --
    it was the only reason the bass drums showed any response to turning in at
    all, since a centred bass line is symmetric under the flip.
    """
    performers = []
    for depth, (name, count) in enumerate(battery):
        if count < 1:
            continue
        xs = (np.arange(count) - (count - 1) / 2.0) * dx
        row_y = y + depth * section_depth_ft
        performers += [Performer(name, float(x), float(row_y)) for x in xs]
    return performers


def _pit_line(pit):
    names = [n for n, c in pit for _ in range(c)]
    if not names:
        return []
    # The front ensemble sits on the track, just in front of the front sideline.
    xs = np.linspace(-60.0, 60.0, len(names)) if len(names) > 1 else np.array([0.0])
    return [Performer(n, float(x), -6.0) for n, x in zip(names, xs)]


FORMS = {"block": block_form, "arc": arc_form}


def save_csv(performers, path):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["instrument", "x_ft", "y_ft", "face_x", "face_y"])
        for p in performers:
            w.writerow([p.instrument, "%.3f" % p.x, "%.3f" % p.y,
                        "%.5f" % p.fx, "%.5f" % p.fy])


def load_csv(path):
    """Load drill from CSV. Facing columns are optional; front is assumed."""
    performers = []
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        missing = {"instrument", "x_ft", "y_ft"} - set(reader.fieldnames or ())
        if missing:
            raise ValueError(
                "%s is missing required column(s): %s. Expected at least "
                "instrument, x_ft, y_ft (face_x and face_y are optional)."
                % (path, ", ".join(sorted(missing)))
            )

        for n, row in enumerate(reader, start=2):  # start=2: row 1 is the header
            name = (row["instrument"] or "").strip()
            if name not in CATALOG:
                raise ValueError(
                    "%s line %d: unknown instrument %r; known: %s"
                    % (path, n, name, ", ".join(sorted(CATALOG)))
                )
            try:
                performers.append(Performer(
                    name, float(row["x_ft"]), float(row["y_ft"]),
                    float(row.get("face_x") or 0.0), float(row.get("face_y") or -1.0),
                ))
            except (TypeError, ValueError) as e:
                raise ValueError("%s line %d: bad numeric field (%s)" % (path, n, e))

    if not performers:
        raise ValueError("%s contains no performers" % path)
    return performers
