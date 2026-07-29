#!/usr/bin/env python3
"""Generate the differential-test reference from the Python implementation.

Writes `kernel/test/reference.json`: a randomised ensemble of simulation cases
with their inputs and the exact outputs `dcisim` produces, plus a few isolated
probes (Bessel J1, absorption coefficients, directivity indices) so that when
the TypeScript port disagrees it is possible to say *where*.

Run from anywhere:  python3 kernel/test/gen_reference.py
"""

import json
import os
import random
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from scipy.special import j1  # noqa: E402

from dcisim.atmosphere import BANDS, absorption_coefficients, speed_of_sound  # noqa: E402
from dcisim.directivity import Directivity  # noqa: E402
from dcisim.drill import Performer, apply_facing, arc_form, block_form  # noqa: E402
from dcisim.engine import Conditions, simulate  # noqa: E402
from dcisim.field import Stadium  # noqa: E402
from dcisim.instruments import CATALOG  # noqa: E402

NAMES = sorted(CATALOG)
OUT = os.path.join(HERE, "reference.json")


def stadium_dict(st):
    return {
        "apronFt": st.apron_ft,
        "nRows": st.n_rows,
        "rowDepthFt": st.row_depth_ft,
        "rowRiseFt": st.row_rise_ft,
        "firstRowHeightFt": st.first_row_height_ft,
        "earHeightFt": st.ear_height_ft,
        "halfWidthFt": st.half_width_ft,
        "seatsAcross": st.seats_across,
        "farSide": st.far_side,
        "farSideSetbackFt": st.far_side_setback_ft,
        "farSideHeightFt": st.far_side_height_ft,
        "farSideAbsorption": list(st.far_side_absorption),
    }


def conditions_dict(c):
    return {
        "tempC": c.temp_c,
        "humidityPct": c.humidity_pct,
        "pressureKpa": c.pressure_kpa,
        "groundEffect": c.ground_effect,
        "farSideReflection": c.far_side_reflection,
    }


def performers_dict(ps):
    return [{"instrument": p.instrument, "x": p.x, "y": p.y, "fx": p.fx, "fy": p.fy} for p in ps]


def run_case(name, performers, receivers, stadium, cond):
    res = simulate(performers, receivers, stadium, cond)
    return {
        "name": name,
        "performers": performers_dict(performers),
        "receiversFt": np.asarray(receivers, dtype=float).ravel().tolist(),
        "stadium": stadium_dict(stadium),
        "conditions": conditions_dict(cond),
        "nReceivers": int(np.asarray(receivers).shape[0]),
        "bandSpl": res.band_spl.ravel().tolist(),
        "directSpl": res.direct_spl.ravel().tolist(),
        "reflectedSpl": res.reflected_spl.ravel().tolist(),
        "arrivalMeanMs": np.where(
            np.isnan(res.arrival_mean_ms), None, res.arrival_mean_ms
        ).tolist(),
        "arrivalSpreadMs": np.where(
            np.isnan(res.arrival_spread_ms), None, res.arrival_spread_ms
        ).tolist(),
        "dba": res.dba.tolist(),
        "brightness": res.brightness.tolist(),
        "reflectedRatioDb": res.reflected_ratio_db.tolist(),
    }


def random_receivers(rng, n):
    """A deliberately nasty mix: house seats, on-field points, very close-in
    points that exercise the MIN_RANGE clamp, and points behind the ensemble."""
    pts = []
    for _ in range(n):
        kind = rng.random()
        if kind < 0.45:  # grandstand
            pts.append([rng.uniform(-170, 170), rng.uniform(-140, -20), rng.uniform(3, 70)])
        elif kind < 0.65:  # on the field, among the players
            pts.append([rng.uniform(-90, 90), rng.uniform(0, 160), rng.uniform(0.5, 8)])
        elif kind < 0.80:  # behind the far-side plane
            pts.append([rng.uniform(-200, 200), rng.uniform(160, 320), rng.uniform(1, 60)])
        elif kind < 0.92:  # very close in — inside MIN_RANGE_M of a bell
            pts.append([rng.uniform(-5, 5), rng.uniform(40, 70), rng.uniform(4, 7)])
        else:  # far away
            pts.append([rng.uniform(-400, 400), rng.uniform(-600, -200), rng.uniform(3, 90)])
    return np.array(pts, dtype=float)


def random_ensemble(rng, n):
    ps = []
    for _ in range(n):
        name = rng.choice(NAMES)
        x = rng.uniform(-85.0, 85.0)
        y = rng.uniform(-8.0, 155.0)
        # Unnormalised facings on purpose: the engine normalises inside
        # `_bell_axes`, and a port that assumes unit input would drift.
        mag = rng.choice([1.0, 0.13, 7.5, 1e-6 * 3, 250.0])
        ang = rng.uniform(0.0, 2.0 * np.pi)
        ps.append(Performer(name, x, y, mag * np.cos(ang), mag * np.sin(ang)))
    return ps


def main():
    rng = random.Random(20260729)
    cases = []

    # --- deterministic edge cases -----------------------------------------
    ref2 = np.array([[0.0, -30.0, 12.0], [90.0, -60.0, 40.0]])

    cases.append(
        run_case(
            "single-trumpet-inverse-square",
            [Performer("trumpet", 0.0, 60.0)],
            np.array([[0.0, 60.0 - 32.8, 5.2], [0.0, 60.0 - 65.6, 5.2]]),
            Stadium(),
            Conditions(far_side_reflection=False),
        )
    )
    cases.append(
        run_case(
            "bass-two-lobes",
            apply_facing([Performer("bass", x, 30.0) for x in (-7.5, -2.5, 2.5, 7.5)], "center"),
            Stadium(n_rows=6).seat_grid()[0],
            Stadium(n_rows=6),
            Conditions(),
        )
    )
    cases.append(
        run_case(
            "pit-only",
            apply_facing([Performer("pit", -20.0, 2.0), Performer("pit", 20.0, 2.0)], "center"),
            ref2,
            Stadium(),
            Conditions(),
        )
    )
    cases.append(
        run_case("empty-ensemble", [], ref2, Stadium(), Conditions()),
    )
    for form_name, form in (("block", block_form), ("arc", arc_form)):
        for mode in ("front", "center"):
            for refl in (True, False):
                st = Stadium(n_rows=8)
                cases.append(
                    run_case(
                        "%s-%s-refl%d" % (form_name, mode, refl),
                        apply_facing(form(), mode),
                        st.seat_grid()[0],
                        st,
                        Conditions(far_side_reflection=refl),
                    )
                )
    # Battery pinned front while the hornline turns in.
    st = Stadium(n_rows=6)
    cases.append(
        run_case(
            "arc-center-battery-front",
            apply_facing(arc_form(), "center", battery_faces_front=True),
            st.seat_grid()[0],
            st,
            Conditions(),
        )
    )
    # A stadium whose far side is so distant the gate rejects everything.
    cases.append(
        run_case(
            "far-side-out-of-reach",
            apply_facing(arc_form(), "front"),
            Stadium(n_rows=5).seat_grid()[0],
            Stadium(n_rows=5, far_side_setback_ft=5000.0),
            Conditions(far_side_reflection=True),
        )
    )
    # Perfectly absorptive far side.
    cases.append(
        run_case(
            "far-side-dead",
            apply_facing(arc_form(), "front"),
            Stadium(n_rows=5).seat_grid()[0],
            Stadium(n_rows=5, far_side_absorption=(1.0,) * 8),
            Conditions(far_side_reflection=True),
        )
    )

    # --- randomised ensemble ----------------------------------------------
    for i in range(24):
        n_perf = rng.randint(3, 45)
        performers = random_ensemble(rng, n_perf)
        mode = rng.choice(["as-is", "front", "center", "focus"])
        if mode != "as-is":
            focus = (rng.uniform(-60, 60), rng.uniform(20, 140))
            performers = apply_facing(
                performers, mode, focus=focus, battery_faces_front=rng.random() < 0.4
            )
        st = Stadium(
            n_rows=rng.randint(3, 12),
            seats_across=rng.randint(3, 11),
            half_width_ft=rng.uniform(80.0, 220.0),
            far_side=rng.random() < 0.85,
            far_side_setback_ft=rng.uniform(2.0, 120.0),
            far_side_height_ft=rng.uniform(5.0, 90.0),
            far_side_absorption=tuple(rng.uniform(0.0, 1.0) for _ in range(8)),
        )
        cond = Conditions(
            temp_c=rng.uniform(-5.0, 42.0),
            humidity_pct=rng.uniform(2.0, 98.0),
            pressure_kpa=rng.uniform(80.0, 106.0),
            ground_effect=False,
            far_side_reflection=rng.random() < 0.75,
        )
        rcv = random_receivers(rng, rng.randint(20, 180))
        cases.append(run_case("random-%02d" % i, performers, rcv, st, cond))

    # --- ground effect, small and slow ------------------------------------
    for i in range(2):
        performers = random_ensemble(rng, 6)
        st = Stadium(n_rows=4, seats_across=5)
        cond = Conditions(
            temp_c=rng.uniform(0.0, 35.0),
            humidity_pct=rng.uniform(10.0, 90.0),
            ground_effect=True,
            far_side_reflection=(i == 0),
        )
        cases.append(
            run_case("ground-%02d" % i, performers, random_receivers(rng, 24), st, cond)
        )

    # --- isolated probes ---------------------------------------------------
    j1_x = list(np.linspace(0.0, 25.0, 501))
    probes = {
        "besselJ1": {"x": j1_x, "y": [float(j1(v)) for v in j1_x]},
        "speedOfSound": {
            "tempC": [-40.0, -5.0, 0.0, 15.0, 24.0, 35.0, 55.0],
            "c": [float(speed_of_sound(t)) for t in (-40.0, -5.0, 0.0, 15.0, 24.0, 35.0, 55.0)],
        },
        "absorption": [],
        "directivityIndex": {},
        "directivityTable": {},
    }
    for t, h, p in [
        (24.0, 55.0, 101.325),
        (-5.0, 5.0, 80.0),
        (40.0, 95.0, 106.0),
        (10.0, 30.0, 95.0),
    ]:
        probes["absorption"].append(
            {
                "tempC": t,
                "humidityPct": h,
                "pressureKpa": p,
                "alpha": absorption_coefficients(BANDS, t, h, p).tolist(),
            }
        )
    for name, inst in sorted(CATALOG.items()):
        for temp in (24.0, 5.0):
            d = inst.directivity(temp)
            key = "%s@%g" % (name, temp)
            probes["directivityIndex"][key] = d.directivity_index_db().tolist()
            # Every 12th theta sample keeps the file a sane size while still
            # covering the whole sweep including both endpoints.
            idx = list(range(0, d.table.shape[1], 12))
            if idx[-1] != d.table.shape[1] - 1:
                idx.append(d.table.shape[1] - 1)
            probes["directivityTable"][key] = {
                "thetaIndex": idx,
                "theta": [float(d.theta[i]) for i in idx],
                "amp": [float(d.table[b, i]) for b in range(8) for i in idx],
            }

    payload = {
        "generator": "kernel/test/gen_reference.py",
        "bands": BANDS.tolist(),
        "probes": probes,
        "cases": cases,
    }
    with open(OUT, "w") as fh:
        json.dump(payload, fh)
    print(
        "wrote %s: %d cases, %d receiver-band values"
        % (
            OUT,
            len(cases),
            sum(len(c["bandSpl"]) for c in cases),
        )
    )


if __name__ == "__main__":
    main()
