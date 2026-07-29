"""Instrument definitions: radiated power spectrum, bell geometry, aim.

Sound power levels are per player at a sustained fortissimo, in dB re 1 pW per
octave band. They are representative rather than measured -- calibrated so that
a full corps lands around 95-100 dBA in the low rows at typical stadium
distances, which is where measurements of the activity actually sit. Treat them
as a starting point and override them if you have real data.

`bell_azimuth_offset_deg` is the angle between the player's facing direction and
the bell axis. Everything in a hornline is zero. Marching bass drums are the
interesting exception: the heads face left and right, so a bass drum radiates
perpendicular to the way its player is facing, and the "everyone faces center"
question has a completely different answer for that section.
"""

from dataclasses import dataclass, field as dc_field

import numpy as np

from .directivity import DEFAULT_FRONT_TO_BACK, Directivity


@dataclass
class Instrument:
    name: str
    power_db: np.ndarray  # sound power level per octave band, dB re 1 pW
    bell_radius_m: float  # PHYSICAL bell/head radius; directivity.py maps this
    #                       through its own fitted aperture correction, so do
    #                       not pre-compensate it here
    bell_height_m: float  # height of the bell above the field surface
    bell_elevation_deg: float = 0.0  # positive tips the bell up ("horns up")
    bell_azimuth_offset_deg: float = 0.0  # bell axis relative to facing
    # copy(), not the shared module-level array: without it every brass
    # instrument holds the *same* object, so retuning one retunes all four.
    front_to_back: np.ndarray = dc_field(
        default_factory=lambda: DEFAULT_FRONT_TO_BACK.copy()
    )
    _cache: dict = dc_field(default_factory=dict, repr=False, compare=False)
    # Set by set_measured(); when present the analytic model is not used at all.
    _measured: object = dc_field(default=None, repr=False, compare=False)
    _measured_citation: str = dc_field(default="", repr=False, compare=False)

    def set_measured(self, table, citation, theta=None):
        """Replace the fitted directivity with measured data.

        `table` is (n_bands, n_theta), on-axis unity -- what
        `dcisim.sofa.load_directivity` returns. A citation is required rather
        than optional: measured data whose source nobody can look up is not
        meaningfully better than a fitted curve, and the provenance report
        exists to make that distinction visible.
        """
        if not citation or not str(citation).strip():
            raise ValueError(
                "measured directivity needs a citation -- the point of using it "
                "is that someone can check where it came from"
            )
        self._measured = (np.asarray(table, dtype=float), theta)
        self._measured_citation = str(citation).strip()
        self._cache.clear()
        return self

    def clear_measured(self):
        self._measured = None
        self._measured_citation = ""
        self._cache.clear()
        return self

    def provenance(self):
        """How this instrument's directivity is sourced."""
        from .provenance import MEYER_BRASS, Source, State

        if self._measured is not None:
            return Source(State.MEASURED, "%s directivity" % self.name,
                          self._measured_citation)
        return Source(
            State.FITTED, "%s directivity" % self.name, MEYER_BRASS,
            "piston model with a fitted aperture correction; the rear "
            "hemisphere is carried to an asserted front-to-back ratio",
        )

    def directivity(self, temp_c=24.0):
        # Keyed on everything the table is built from, not just temperature.
        # These instruments are module-level singletons and the module docstring
        # invites overriding them, so a cache keyed on less would silently serve
        # the old physics after any edit -- no error, no warning.
        if self._measured is not None:
            if "measured" not in self._cache:
                table, theta = self._measured
                self._cache["measured"] = Directivity.from_measured(table, theta)
            return self._cache["measured"]

        key = (
            round(float(temp_c), 3),
            float(self.bell_radius_m),
            np.asarray(self.front_to_back).tobytes(),
        )
        if key not in self._cache:
            self._cache[key] = Directivity(
                self.bell_radius_m, self.front_to_back, temp_c=temp_c
            )
        return self._cache[key]


def _db(*values):
    return np.array(values, dtype=float)


#                         63    125    250    500     1k     2k     4k     8k
TRUMPET = Instrument(
    "trumpet", _db(84, 94, 102, 109, 111, 109, 104, 96),
    bell_radius_m=0.062, bell_height_m=1.60, bell_elevation_deg=8.0,
)
MELLOPHONE = Instrument(
    "mellophone", _db(86, 98, 106, 110, 109, 105, 99, 90),
    bell_radius_m=0.130, bell_height_m=1.55, bell_elevation_deg=6.0,
)
BARITONE = Instrument(
    "baritone", _db(92, 103, 109, 110, 107, 102, 96, 87),
    bell_radius_m=0.140, bell_height_m=1.58, bell_elevation_deg=5.0,
)
CONTRA = Instrument(
    "contra", _db(104, 110, 111, 108, 103, 97, 90, 81),
    bell_radius_m=0.240, bell_height_m=1.85, bell_elevation_deg=4.0,
)

# Percussion. Battery radiates far less directionally than brass, so the
# front-to-back ratios are compressed. Each instrument gets its own copy for the
# same reason the brass do.
def _perc_ftb():
    return _db(1.0, 1.5, 2.5, 4.0, 6.0, 8.0, 10.0, 12.0)


# Carry angles matter more than they look. A modern marching snare is carried
# with the head close to horizontal, so its radiating axis is nearly vertical
# and turning the player barely changes what the audience receives. Modelling
# the snare at 45 degrees instead of ~80 gave the section a 3.4 dB penalty for
# turning in, against 0.2 dB at the real angle -- and with snares at a fifth of
# the ensemble's A-weighted energy, that alone moved the headline by 0.6 dB.
SNARE = Instrument(
    "snare", _db(86, 94, 101, 106, 109, 111, 111, 107),
    bell_radius_m=0.171, bell_height_m=0.95, bell_elevation_deg=80.0,
    front_to_back=_perc_ftb(),
)
TENOR = Instrument(
    "tenor", _db(94, 102, 107, 108, 107, 105, 102, 97),
    bell_radius_m=0.140, bell_height_m=0.95, bell_elevation_deg=72.0,
    front_to_back=_perc_ftb(),
)
BASS = Instrument(
    "bass", _db(110, 112, 108, 103, 98, 93, 88, 82),
    bell_radius_m=0.330, bell_height_m=1.00, bell_elevation_deg=0.0,
    bell_azimuth_offset_deg=90.0,  # heads face sideways, not forward
    front_to_back=_perc_ftb(),
)

# Front ensemble is amplified through a front-sideline PA, so it always fires
# into the house regardless of what the drill does. Included for completeness of
# the overall level; it is deliberately unaffected by the facing experiment.
# NOTE: this is eight acoustic point sources on the sideline, not a real PA
# model. Because they sit far closer to the stands than anyone on the field,
# they carry a disproportionate share of the level in the low rows, and that
# gradient shows up in results as if it were a property of the drill. See the
# limitations section of the README before reading anything into it.
PIT = Instrument(
    "pit", _db(100, 106, 108, 108, 107, 105, 102, 96),
    bell_radius_m=0.100, bell_height_m=1.80, bell_elevation_deg=0.0,
    front_to_back=_db(3, 4, 6, 9, 12, 14, 16, 18),
)

CATALOG = {
    inst.name: inst
    for inst in (TRUMPET, MELLOPHONE, BARITONE, CONTRA, SNARE, TENOR, BASS, PIT)
}
