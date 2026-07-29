"""Field and stadium geometry.

Coordinates are in feet, matching how drill is actually written:

    x   0 at the 50, negative toward side 1, positive toward side 2.
        The goal lines are at -150 and +150.
    y   0 at the front sideline, increasing upfield. Back sideline at 160.
        College hashes sit at y = 60 and y = 100.
    z   0 at the field surface, positive up.

The audience lives at negative y, elevated on a raked grandstand. Metres are
used internally by the propagation engine; everything the user touches is feet
and steps.
"""

from dataclasses import dataclass

import numpy as np

FT_PER_M = 3.280839895
STEP_FT = 22.5 / 12.0  # 8-to-5 marching step

FIELD_LENGTH_FT = 300.0  # goal line to goal line
FIELD_WIDTH_FT = 160.0  # sideline to sideline
FRONT_HASH_FT = 60.0
BACK_HASH_FT = 100.0
FIELD_CENTER = (0.0, FIELD_WIDTH_FT / 2.0)


def yards_to_x(yard_line, side):
    """Convert a yard line and side ('1' or '2') to an x coordinate in feet."""
    offset = (50.0 - yard_line) * 3.0
    return -offset if str(side) == "1" else offset


def steps_from_sideline(n_steps):
    """y coordinate n steps behind the front sideline."""
    return n_steps * STEP_FT


@dataclass
class Stadium:
    """A raked grandstand along the front sideline, plus an optional far-side
    grandstand that reflects backfield energy into the house."""

    apron_ft: float = 25.0  # sideline to the first row
    n_rows: int = 40
    row_depth_ft: float = 2.6
    row_rise_ft: float = 1.35  # ~27 degree rake
    first_row_height_ft: float = 3.0
    ear_height_ft: float = 3.6  # seated ear above the local riser
    half_width_ft: float = 165.0  # stands extend +/- this in x
    seats_across: int = 41

    # Far-side grandstand, modelled as a single specular reflector.
    far_side: bool = True
    far_side_setback_ft: float = 30.0  # back sideline to the reflecting face
    far_side_height_ft: float = 45.0  # reflecting face extends this high
    # Occupied grandstand seating, which is far more absorptive than bare
    # structure -- audience areas run roughly 0.6-0.9 through the mid and high
    # bands. Understating this inflates both the reflected-to-direct ratio and
    # the arrival spread.
    far_side_absorption: tuple = (0.45, 0.55, 0.70, 0.80, 0.85, 0.85, 0.85, 0.85)

    def seat_grid(self):
        """Receiver positions for every seat.

        Returns (points, xs, rows) where `points` is (n_seats, 3) in feet and
        `xs`/`rows` are the axis vectors for reshaping results into a map.
        """
        xs = np.linspace(-self.half_width_ft, self.half_width_ft, self.seats_across)
        rows = np.arange(self.n_rows)

        y = -(self.apron_ft + rows * self.row_depth_ft)
        z = self.first_row_height_ft + rows * self.row_rise_ft + self.ear_height_ft

        gx, grow = np.meshgrid(xs, rows, indexing="ij")
        gy = np.broadcast_to(y, gx.shape)
        gz = np.broadcast_to(z, gx.shape)

        points = np.stack([gx.ravel(), gy.ravel(), gz.ravel()], axis=1)
        return points, xs, rows

    @property
    def far_side_plane_y(self):
        return FIELD_WIDTH_FT + self.far_side_setback_ft

    def mirror(self, points):
        """Reflect source points across the far-side grandstand face."""
        mirrored = np.array(points, dtype=float, copy=True)
        mirrored[:, 1] = 2.0 * self.far_side_plane_y - mirrored[:, 1]
        return mirrored


def named_seats(stadium):
    """A few reference seats worth quoting in a report.

    Row indices are clamped to the stand that actually exists, so a short
    grandstand reports real seats rather than extrapolating off the top of it.
    """
    if stadium.n_rows < 1:
        raise ValueError("a grandstand needs at least one row, got %d" % stadium.n_rows)

    top = stadium.n_rows - 1
    low = min(3, top)
    mid = min(max(stadium.n_rows // 2, low), top)

    def seat(x, row):
        return np.array([
            x,
            -(stadium.apron_ft + row * stadium.row_depth_ft),
            stadium.first_row_height_ft + row * stadium.row_rise_ft + stadium.ear_height_ft,
        ])

    # Labels carry the row number, so a stand too short to distinguish them
    # collapses to fewer entries rather than reporting the same seat twice.
    out = {}
    for label, x, row in (
        ("low 50", 0.0, low),
        ("mid 50", 0.0, mid),
        ("high 50", 0.0, top),
        ("corner side 2", 120.0, mid),
    ):
        out["%s (row %d)" % (label, row)] = seat(x, row)
    return out
