"""Frequency-dependent directivity for bell-radiating instruments.

The model has two pieces that get combined:

1. A circular-piston term, ``2*J1(u)/u`` with ``u = k*a*sin(theta)``. This is
   what produces the beaming everyone knows about -- a trumpet at 8 kHz is
   genuinely a flashlight, while the same trumpet at 250 Hz is close to
   omnidirectional. The piston term is averaged in power across each octave
   band, which smears out the sidelobe nulls the same way real broadband
   playing does.

2. A sidelobe floor and a rear taper. A piston is front/back symmetric and
   nulls to nothing, both of which are wrong for a real bell. The floor sets
   how far down the off-axis energy can actually get (diffraction around the
   flare, radiation from the body of the instrument and the player); the rear
   taper carries the response from the 90-degree level down to a published
   front-to-back ratio at 180 degrees.

That back hemisphere is the entire story of this simulation, so it is worth not
hand-waving. The defaults are tuned so the resulting directivity indices land on
the published values for brass -- see `python -m dcisim.directivity`.
"""

import numpy as np
from scipy.special import j1

from .atmosphere import BANDS, speed_of_sound

# Front-to-back ratio (dB, level at 180 deg relative to on-axis) by octave band.
# Brass is nearly omni in the bottom octaves and strongly forward above ~1 kHz.
DEFAULT_FRONT_TO_BACK = np.array([2.0, 3.0, 5.0, 9.0, 14.0, 18.0, 22.0, 25.0])

# Off-axis floor (dB below on-axis) that the piston term is not allowed to fall
# below. This is what stops the model predicting physically absurd nulls.
DEFAULT_SIDELOBE_FLOOR = np.linspace(4.0, 14.0, 8)

# A brass bell is a flare, not a flat piston, so the physical bell radius is the
# wrong aperture to hand the piston expression: it under-predicts directivity in
# the low mids and over-predicts it on top, and it exaggerates the difference
# between a trumpet and a contra. Mapping the physical radius through
#
#     a_eff(f) = A_REF * (a / A_REF)**APERTURE_COMPRESSION * (1 kHz / f)**FLARE_EXPONENT
#
# fits the published directivity indices for trumpet, mellophone and contra to
# about 0.8 dB RMS across all eight bands. It is an empirical correction, fitted
# against the targets in REFERENCE_DI below; re-run `python -m dcisim.directivity`
# after touching any of it.
A_REF = 0.13
APERTURE_COMPRESSION = 0.45
FLARE_EXPONENT = 0.50
MAX_EFFECTIVE_RADIUS = 0.60

_THETA_GRID = np.radians(np.linspace(0.0, 180.0, 721))


def effective_radius(radius_m, freq_hz):
    """Frequency-dependent radiating aperture (see note above)."""
    a = A_REF * (radius_m / A_REF) ** APERTURE_COMPRESSION
    return min(a * (1000.0 / freq_hz) ** FLARE_EXPONENT, MAX_EFFECTIVE_RADIUS)


def _band_averaged_piston(radius_m, band_hz, theta, c, n_sub=9):
    """Power-averaged piston directivity across one octave band."""
    lo, hi = band_hz / np.sqrt(2.0), band_hz * np.sqrt(2.0)
    sub = np.geomspace(lo, hi, n_sub)
    k = 2.0 * np.pi * sub / c

    u = np.outer(np.sin(theta), k * radius_m)  # (theta, sub)
    with np.errstate(divide="ignore", invalid="ignore"):
        d = np.where(u == 0.0, 1.0, 2.0 * j1(u) / u)
    return np.sqrt(np.mean(d**2, axis=1))


def build_directivity_table(
    radius_m,
    front_to_back=DEFAULT_FRONT_TO_BACK,
    sidelobe_floor=DEFAULT_SIDELOBE_FLOOR,
    temp_c=24.0,
    theta=_THETA_GRID,
):
    """Linear directivity factor on a (band, theta) grid.

    `radius_m` is the effective radiating aperture -- close to the physical bell
    radius for brass. Returns an array of shape (len(BANDS), len(theta)) with
    1.0 on axis.
    """
    c = speed_of_sound(temp_c)
    front_to_back = np.asarray(front_to_back, dtype=float)
    sidelobe_floor = np.asarray(sidelobe_floor, dtype=float)

    # The piston expression depends on sin(theta), so it is already symmetric
    # about 90 degrees; evaluating it directly gives the front-hemisphere shape
    # mirrored into the rear, which the taper below then corrects.
    if radius_m <= 0.0:
        # Explicit escape hatch: radius 0 means an ideal omnidirectional source.
        # Note that a merely *small* radius is not the same thing, because the
        # aperture fit above never collapses all the way to a point.
        piston = np.ones((len(BANDS), len(theta)))
    else:
        piston = np.stack([
            _band_averaged_piston(effective_radius(radius_m, f), f, theta, c)
            for f in BANDS
        ])

    # A floor deeper than the front-to-back ratio contradicts it: the model
    # cannot simultaneously claim you never get more than X dB off-axis and
    # exactly Y > X dB down at 180. Percussion hits this at 8 kHz.
    floor = 10.0 ** (-np.minimum(sidelobe_floor, front_to_back) / 20.0)[:, None]
    front = np.maximum(piston, floor)

    # The piston expression depends on sin(theta), so its rear-hemisphere values
    # are just the front hemisphere mirrored -- an artefact with no physical
    # content, which climbs back toward the main lobe as theta approaches 180.
    # So the rear is not built from it at all. Instead the response is carried
    # from whatever it reached at 90 degrees down to the published
    # front-to-back ratio at 180, interpolated smoothly in dB.
    #
    # Tapering the front-hemisphere curve instead (including its floor) let the
    # response dive well past the stated ratio around 140-160 degrees before
    # climbing back to it -- contra at 8 kHz reached -34.6 dB against a stated
    # -25 dB, percussion overshot by 12 dB. That artefact is invisible to the
    # directivity-index calibration, which moves under 0.1 dB either way, and it
    # is not common-mode across the experiment this model exists to run: facing
    # front, no brass path lands in the 120-175 degree window; facing center,
    # about 40% of them do.
    at_90 = np.interp(np.pi / 2.0, theta, np.arange(len(theta)))
    d90 = front[:, int(round(at_90))][:, None]
    rear_target = 10.0 ** (-front_to_back / 20.0)[:, None]

    s = np.clip((theta - np.pi / 2.0) / (np.pi / 2.0), 0.0, 1.0)
    s = s * s * (3.0 - 2.0 * s)  # smoothstep, C1 at both ends
    rear = d90 * (rear_target / d90) ** s

    return np.where(theta[None, :] <= np.pi / 2.0, front, rear)


class Directivity:
    """Callable directivity lookup, interpolated over off-axis angle."""

    def __init__(self, radius_m, front_to_back=DEFAULT_FRONT_TO_BACK,
                 sidelobe_floor=DEFAULT_SIDELOBE_FLOOR, temp_c=24.0,
                 table=None, theta=None):
        self.radius_m = radius_m
        if table is not None:
            # Measured data, already reduced to (n_bands, n_theta) with on-axis
            # unity -- see dcisim.sofa. The analytic construction below is
            # bypassed entirely; nothing here is fitted any more.
            table = np.asarray(table, dtype=float)
            self.theta = (np.linspace(0.0, np.pi, table.shape[1])
                          if theta is None else np.asarray(theta, dtype=float))
            if table.shape != (len(BANDS), len(self.theta)):
                raise ValueError(
                    "measured table must be (%d bands, n_theta), got %s"
                    % (len(BANDS), (table.shape,))
                )
            self.table = table
        else:
            self.theta = _THETA_GRID
            self.table = build_directivity_table(
                radius_m, front_to_back, sidelobe_floor, temp_c, self.theta
            )
        self._di = None

    @classmethod
    def from_measured(cls, table, theta=None):
        return cls(radius_m=0.0, table=table, theta=theta)

    def pattern_db(self, theta_rad):
        """Radiation pattern in dB, normalised to 0 dB on axis.

        This is the shape of the beam. It is *not* what the propagation equation
        wants -- see `gain_db`.
        """
        shape = np.shape(theta_rad)
        flat = np.clip(np.ravel(theta_rad), 0.0, np.pi)
        out = np.empty((len(BANDS),) + flat.shape)
        for i in range(len(BANDS)):
            out[i] = np.interp(flat, self.theta, self.table[i])
        out = 20.0 * np.log10(np.maximum(out, 1e-6))
        return out.reshape((len(BANDS),) + shape)

    def gain_db(self, theta_rad):
        """Directivity index in a given direction, dB re. the sphere average.

        This is the DI(theta) term in

            Lp = Lw - 20*log10(r) - 11 + DI(theta)

        and it is what the engine must use. Normalising the pattern to 0 dB on
        axis instead would quietly redefine `Lw` as "on-axis level" rather than
        sound power, which throws the radiated power off by the directivity
        index -- under a dB at 63 Hz but around 13 dB at 8 kHz. That tilts the
        whole spectrum and, because it is band-dependent, corrupts any
        A-weighted or high-to-low band ratio computed from it.
        """
        di = self.directivity_index_db()
        pattern = self.pattern_db(theta_rad)
        return pattern + di.reshape((len(BANDS),) + (1,) * (pattern.ndim - 1))

    def directivity_index_db(self):
        """DI per band: on-axis gain over the sphere-averaged power."""
        if self._di is None:
            self._di = self._compute_di()
        return self._di

    def _compute_di(self):
        w = np.sin(self.theta)
        mean_power = np.trapezoid(self.table**2 * w, self.theta, axis=1) / np.trapezoid(
            w, self.theta
        )
        return -10.0 * np.log10(mean_power)


# Published directivity indices for brass, used as the calibration target.
# Trumpet values follow the general trend in Meyer, "Acoustics and the
# Performance of Music": near-omni at the bottom, ~10-13 dB by 8 kHz.
REFERENCE_DI = {
    "trumpet": (0.062, [0.3, 0.6, 1.2, 2.5, 4.5, 7.0, 10.0, 12.5]),
    "mellophone": (0.130, [0.5, 1.2, 2.5, 4.5, 7.0, 9.5, 11.5, 13.0]),
    "contra": (0.240, [1.0, 2.2, 4.2, 6.5, 9.0, 11.0, 12.5, 13.5]),
}


def _report():
    """Print modelled vs. published directivity indices."""
    hdr = "".join("%8s" % ("%gk" % (f / 1000) if f >= 1000 else "%g" % f) for f in BANDS)
    print("Directivity index, dB (model vs. published target)")
    print("            " + hdr)
    for name, (radius, target) in REFERENCE_DI.items():
        di = Directivity(radius).directivity_index_db()
        print("%-11s " % name + "".join("%8.1f" % v for v in di))
        print("%-11s " % "  target" + "".join("%8.1f" % v for v in target))
        print("%-11s " % "  error" + "".join("%+8.1f" % v for v in (di - np.array(target))))


if __name__ == "__main__":
    _report()
