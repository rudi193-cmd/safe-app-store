"""Invariants the model must not violate.

Run with `python -m pytest test_dcisim.py -q`, or just `python test_dcisim.py`.
"""

import numpy as np

from dcisim import drill
from dcisim.atmosphere import BANDS
from dcisim.directivity import Directivity, REFERENCE_DI
from dcisim.drill import Performer, apply_facing
from dcisim.engine import Conditions, simulate
from dcisim.field import FIELD_CENTER, Stadium, named_seats
from dcisim.instruments import CATALOG, Instrument

REF = np.array([[0.0, -30.0, 12.0], [90.0, -60.0, 40.0]])


def test_pattern_is_unity_on_axis():
    d = Directivity(0.062)
    assert np.allclose(d.pattern_db(0.0), 0.0, atol=1e-6)


def test_on_axis_gain_equals_the_directivity_index():
    """`gain_db` must be referenced to the sphere average, not to the axis.

    If it is normalised to 0 dB on axis instead, `Lw` silently stops meaning
    sound power and the radiated spectrum tilts by the DI -- about 13 dB at
    8 kHz, which wrecks every A-weighted and HF/LF number downstream.
    """
    d = Directivity(0.130)
    assert np.allclose(d.gain_db(0.0), d.directivity_index_db(), atol=1e-9)


def test_radiated_sound_power_matches_the_declared_lw():
    """Integrate intensity over a sphere and recover Lw."""
    from dcisim.atmosphere import absorption_coefficients

    src = Performer("trumpet", 0.0, 60.0, 0.0, -1.0)
    h = CATALOG["trumpet"].bell_height_m * 3.280839895
    th = np.linspace(1e-3, np.pi - 1e-3, 160)
    ph = np.linspace(0.0, 2 * np.pi, 320, endpoint=False)
    T, P = np.meshgrid(th, ph, indexing="ij")
    d_ft = 10.0 * 3.280839895

    rcv = np.stack([
        (d_ft * np.sin(T) * np.cos(P)).ravel(),
        60.0 + (d_ft * np.sin(T) * np.sin(P)).ravel(),
        h + (d_ft * np.cos(T)).ravel(),
    ], axis=1)

    res = simulate([src], rcv, conditions=Conditions(far_side_reflection=False))
    inten = (10.0 ** (res.band_spl / 10.0)).reshape(len(th), len(ph), 8)
    w = np.sin(T)[:, :, None]
    implied = 10.0 * np.log10(np.sum(inten * w, axis=(0, 1)) / np.sum(w)) \
        + 20.0 * np.log10(10.0) + 11.0

    # The only legitimate shortfall is air absorption over the 10 m radius.
    err = implied - CATALOG["trumpet"].power_db + absorption_coefficients() * 10.0
    assert np.all(np.abs(err) < 0.15), np.round(err, 2)


def test_no_direction_is_louder_than_the_axis():
    for radius, _ in REFERENCE_DI.values():
        g = Directivity(radius).table
        assert np.all(g <= 1.0 + 1e-9)
        assert np.all(g[:, -1] <= g[:, 0])


def test_rear_response_never_dips_below_the_stated_front_to_back_ratio():
    """The rear hemisphere is supposed to be pinned to a published ratio.

    Tapering the sidelobe floor along with everything else instead lets the
    response dive past that ratio in the 140-170 degree region and climb back
    to it at 180 -- up to 12 dB past, for percussion at 8 kHz. It is invisible
    to the directivity-index check (DI moves under 0.1 dB) and it is not
    common-mode: facing front, no brass path lands in that angular window;
    facing center, about 40% of them do.
    """
    from dcisim.directivity import DEFAULT_FRONT_TO_BACK

    for name, inst in sorted(CATALOG.items()):
        d = inst.directivity()
        table_db = 20.0 * np.log10(d.table)
        rear = table_db[:, d.theta >= np.pi / 2.0]
        floor = -np.asarray(inst.front_to_back, dtype=float)
        assert np.all(rear.min(axis=1) >= floor - 1e-6), \
            "%s dips below its stated front-to-back ratio: %s vs %s" % (
                name, np.round(rear.min(axis=1), 1), floor)
        # And it must actually reach the ratio at 180 degrees.
        assert np.allclose(table_db[:, -1], floor, atol=1e-6), name


def test_directivity_falls_monotonically_through_the_rear_hemisphere():
    for radius, _ in REFERENCE_DI.values():
        d = Directivity(radius)
        rear = d.table[:, d.theta >= np.pi / 2.0]
        assert np.all(np.diff(rear, axis=1) <= 1e-9)


def test_direction_cosines_use_the_true_range_not_the_clamped_one():
    """Very close receivers must not lose the pattern.

    Normalising by the clamped range shortens the direction vector, pulling
    every angle toward 90 degrees and flattening the instrument out.
    """
    p = [Performer("trumpet", 0.0, 60.0, 0.0, -1.0)]
    cond = Conditions(far_side_reflection=False)
    for dist_ft in (0.3, 1.0, 3.0, 30.0):
        h = CATALOG["trumpet"].bell_height_m * 3.280839895
        front = simulate(p, np.array([[0.0, 60.0 - dist_ft, h]]), conditions=cond)
        back = simulate(p, np.array([[0.0, 60.0 + dist_ft, h]]), conditions=cond)
        ratio = front.band_spl[0, 7] - back.band_spl[0, 7]
        assert ratio > 20.0, "8 kHz front/back collapsed to %.1f dB at %.1f ft" % (
            ratio, dist_ft)


def test_directivity_index_matches_published_values():
    for name, (radius, target) in REFERENCE_DI.items():
        di = Directivity(radius).directivity_index_db()
        err = di - np.array(target)
        assert np.sqrt(np.mean(err**2)) < 2.0, "%s drifted: %s" % (name, np.round(err, 1))


def test_high_frequencies_are_more_directional_than_low():
    di = Directivity(0.130).directivity_index_db()
    assert np.all(np.diff(di) > 0.0)


def test_facing_is_idempotent():
    base = drill.block_form()
    once = apply_facing(base, "front")
    twice = apply_facing(once, "front")
    assert all(
        (a.fx, a.fy) == (b.fx, b.fy) and (a.x, a.y) == (b.x, b.y)
        for a, b in zip(once, twice)
    )


def test_amplified_pit_is_unaffected_by_the_drill_facing():
    pit = [Performer("pit", -20.0, 2.0), Performer("pit", 20.0, 2.0)]
    fwd = simulate(apply_facing(pit, "front"), REF)
    ctr = simulate(apply_facing(pit, "center"), REF)
    assert np.allclose(fwd.dba, ctr.dba)


def test_an_omnidirectional_source_does_not_care_which_way_it_faces():
    omni = Instrument(
        "omni", np.full(8, 110.0), bell_radius_m=0.0, bell_height_m=1.6,
        front_to_back=np.zeros(8),
    )
    CATALOG["omni"] = omni
    try:
        band = [Performer("omni", x, 60.0) for x in (-30.0, 0.0, 30.0)]
        fwd = simulate(apply_facing(band, "front"), REF)
        ctr = simulate(apply_facing(band, "center"), REF)
        assert np.allclose(fwd.dba, ctr.dba, atol=1e-6)
    finally:
        del CATALOG["omni"]


def test_turning_in_costs_level_and_costs_more_treble_than_bass():
    """The headline result, stated as a constraint rather than a number."""
    base = drill.arc_form()
    stadium = Stadium(n_rows=20)
    seats, _, _ = stadium.seat_grid()

    fwd = simulate(apply_facing(base, "front"), seats, stadium)
    ctr = simulate(apply_facing(base, "center", focus=FIELD_CENTER), seats, stadium)

    assert np.all(ctr.dba < fwd.dba), "facing in should never be louder in the house"

    per_band = np.mean(ctr.band_spl - fwd.band_spl, axis=0)
    assert per_band[7] < per_band[0], "8 kHz must suffer more than 63 Hz"
    assert np.mean(ctr.brightness - fwd.brightness) < -1.0


def test_turning_in_increases_arrival_spread():
    base = drill.arc_form()
    stadium = Stadium(n_rows=12)
    seats, _, _ = stadium.seat_grid()
    cond = Conditions(far_side_reflection=True)

    fwd = simulate(apply_facing(base, "front"), seats, stadium, cond)
    ctr = simulate(apply_facing(base, "center"), seats, stadium, cond)
    assert ctr.arrival_spread_ms.mean() > fwd.arrival_spread_ms.mean()
    assert ctr.reflected_ratio_db.mean() > fwd.reflected_ratio_db.mean()


def test_levels_land_in_a_plausible_range_for_a_corps():
    base = drill.arc_form()
    fwd = simulate(apply_facing(base, "front"), np.array([[0.0, -30.0, 12.0]]))
    assert 88.0 < fwd.dba[0] < 105.0, fwd.dba[0]


def test_inverse_square_holds_for_a_single_source():
    p = [Performer("trumpet", 0.0, 60.0)]
    near = simulate(p, np.array([[0.0, 60.0 - 32.8, 5.2]]),
                    conditions=Conditions(far_side_reflection=False))
    far = simulate(p, np.array([[0.0, 60.0 - 65.6, 5.2]]),
                   conditions=Conditions(far_side_reflection=False))
    # 10 m -> 20 m, low band so air absorption is negligible.
    assert abs((near.band_spl[0, 1] - far.band_spl[0, 1]) - 6.02) < 0.15


def _write_piston_sofa(path, radius=0.062, n_recv=1024):
    import sys
    sys.path.insert(0, "tools")
    from make_test_sofa import fibonacci_sphere, piston_response, write_sofa

    directions = fibonacci_sphere(n_recv)
    freqs = np.geomspace(45.0, 11500.0, 240)
    write_sofa(path, directions, freqs, piston_response(directions, freqs, radius))
    return radius


def test_sofa_loader_recovers_a_known_analytic_pattern():
    """Round-trip a synthesised SOFA file against the closed form.

    No third-party measurements are redistributed to test this -- the fixture is
    a piston whose response can be written down, so the loader is checked
    against arithmetic rather than against an opaque golden file.
    """
    import os
    import tempfile

    from scipy.special import j1

    from dcisim.sofa import load_directivity
    from dcisim.atmosphere import speed_of_sound

    d = tempfile.mkdtemp()
    path = os.path.join(d, "piston.sofa")
    radius = _write_piston_sofa(path)

    table, info = load_directivity(path)
    assert table.shape[0] == len(BANDS)
    assert np.allclose(table[:, 0], 1.0, atol=1e-6), "on-axis must normalise to unity"

    # The recovered axis must be the one the fixture was built around.
    assert info["axis"] @ np.array([1.0, 0.0, 0.0]) > 0.99, info["axis"]

    theta = np.linspace(0.0, np.pi, table.shape[1])
    c = speed_of_sound(24.0)
    for bi, f in enumerate(BANDS):
        for deg in (30.0, 60.0, 90.0):
            t = np.radians(deg)
            u = 2.0 * np.pi * f / c * radius * np.sin(t)
            expect = abs(2.0 * j1(u) / u) if u > 1e-9 else 1.0
            got = np.interp(t, theta, table[bi])
            if expect < 0.02:
                continue  # near a null; band-averaging legitimately fills it
            err = 20.0 * np.log10(max(got, 1e-9) / expect)
            assert abs(err) < 2.5, "%g Hz at %g deg: %.1f dB off" % (f, deg, err)


def test_sofa_rejects_files_that_are_not_directivity():
    import os
    import tempfile

    import h5py

    from dcisim.sofa import SofaError, read_sofa

    d = tempfile.mkdtemp()
    path = os.path.join(d, "bogus.sofa")
    with h5py.File(path, "w") as f:
        f.attrs["SOFAConventions"] = "SimpleFreeFieldHRIR"
        f.create_dataset("Nonsense", data=np.zeros(4))
    _expect(SofaError, lambda: read_sofa(path))


def test_measured_directivity_replaces_the_fitted_model_and_is_tracked():
    import os
    import tempfile

    from dcisim.provenance import State
    from dcisim.sofa import load_directivity

    d = tempfile.mkdtemp()
    path = os.path.join(d, "piston.sofa")
    _write_piston_sofa(path, radius=0.30)  # deliberately unlike a trumpet
    table, _ = load_directivity(path)

    inst = CATALOG["trumpet"]
    assert inst.provenance().state is State.FITTED
    before = inst.directivity().table.copy()
    try:
        inst.set_measured(table, citation="synthetic piston, test fixture")
        assert inst.provenance().state is State.MEASURED
        assert "synthetic piston" in inst.provenance().citation
        assert not np.allclose(inst.directivity().table.shape, before.shape) or \
            not np.allclose(inst.directivity().table, before)
    finally:
        inst.clear_measured()
    assert inst.provenance().state is State.FITTED
    assert np.allclose(inst.directivity().table, before)


def test_measured_data_without_a_citation_is_refused():
    inst = CATALOG["mellophone"]
    _expect(ValueError, lambda: inst.set_measured(np.ones((8, 181)), citation=""))
    _expect(ValueError, lambda: inst.set_measured(np.ones((8, 181)), citation="   "))


def test_a_result_is_only_as_verified_as_its_weakest_input():
    from dcisim.provenance import Provenance, State

    p = Provenance()
    p.add(State.MEASURED, "a").add(State.MEASURED, "b")
    assert p.state is State.MEASURED
    p.add(State.ASSUMED, "c")
    assert p.state is State.ASSUMED, "one assumed input must sink the whole result"
    assert [s.what for s in p.weakest()] == ["c"]
    p.add(State.FITTED, "d")
    assert p.state is State.ASSUMED


def _expect(exc, fn):
    try:
        fn()
    except exc:
        return
    raise AssertionError("expected %s from %r" % (exc.__name__, fn))


def test_unknown_instrument_is_rejected_with_a_useful_message():
    try:
        simulate([Performer("kazoo", 0.0, 60.0)], REF)
    except ValueError as e:
        assert "kazoo" in str(e) and "trumpet" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_non_finite_and_degenerate_inputs_are_rejected():
    _expect(ValueError, lambda: simulate([Performer("trumpet", np.nan, 60.0)], REF))
    _expect(ValueError, lambda: simulate([Performer("trumpet", 0.0, 60.0, 0.0, 0.0)], REF))
    _expect(ValueError, lambda: simulate([Performer("trumpet", 0.0, 60.0)],
                                         np.array([[0.0, np.inf, 5.0]])))
    _expect(ValueError, lambda: simulate([Performer("trumpet", 0.0, 60.0)],
                                         np.array([0.0, -30.0, 12.0])))


def test_impossible_atmospheres_are_rejected():
    p = [Performer("trumpet", 0.0, 60.0)]
    _expect(ValueError, lambda: simulate(p, REF, conditions=Conditions(temp_c=-300.0)))
    _expect(ValueError, lambda: simulate(p, REF, conditions=Conditions(humidity_pct=-5.0)))
    _expect(ValueError, lambda: simulate(p, REF, conditions=Conditions(humidity_pct=150.0)))


def test_empty_ensemble_is_silence_not_a_crash():
    res = simulate([], REF)
    assert res.band_spl.shape == (len(REF), 8)
    assert np.all(res.band_spl < -200.0)


def test_directivity_cache_respects_temperature_and_geometry():
    inst = CATALOG["trumpet"]
    cold = inst.directivity(0.0)
    hot = inst.directivity(50.0)
    assert cold is not hot
    assert not np.allclose(cold.table, hot.table)

    # The module docstring invites overriding these, so the cache must notice.
    original_radius, original_ftb = inst.bell_radius_m, inst.front_to_back
    try:
        before = inst.directivity().table.copy()
        inst.bell_radius_m = 0.60
        assert not np.allclose(inst.directivity().table, before)
        inst.bell_radius_m = original_radius
        inst.front_to_back = np.zeros(8)
        assert not np.allclose(inst.directivity().table, before)
    finally:
        inst.bell_radius_m, inst.front_to_back = original_radius, original_ftb


def test_instruments_do_not_share_one_front_to_back_array():
    a, b = CATALOG["trumpet"], CATALOG["contra"]
    assert a.front_to_back is not b.front_to_back
    assert CATALOG["snare"].front_to_back is not CATALOG["bass"].front_to_back


def test_an_empty_section_list_is_honoured_rather_than_replaced():
    for form in (drill.block_form, drill.arc_form):
        assert form(instrumentation=[], battery=[], pit=[]) == []
        only_battery = form(instrumentation=[], pit=[])
        assert only_battery and {p.instrument for p in only_battery} <= {
            "snare", "tenor", "bass"}
    _expect(ValueError, lambda: drill.block_form(per_row=0))
    _expect(ValueError, lambda: drill.arc_form(per_rank=0))


def test_a_leftover_single_performer_lands_on_the_arc_centre():
    form = drill.arc_form(instrumentation=[("mellophone", 19)], battery=[], pit=[],
                          per_rank=18)
    lone = form[-1]
    assert abs(lone.x) < 1e-6, "stranded at x=%.1f" % lone.x


def test_the_battery_is_laid_out_symmetrically():
    form = drill.block_form()
    for name in ("snare", "tenor", "bass"):
        xs = [p.x for p in form if p.instrument == name]
        assert abs(sum(xs)) < 1e-6, "%s line is off centre: %s" % (name, xs)


def test_a_centred_bass_line_barely_notices_turning_in():
    """Two opposed half-power lobes nearly map onto each other under the flip.

    A bass drum radiates from both heads, so rotating it 180 degrees swaps the
    lobes and changes almost nothing. Any apparent bass-drum "result" is really
    a report on how far off centre the bass line was placed.
    """
    basses = [Performer("bass", x, 30.0) for x in (-7.5, -2.5, 2.5, 7.5)]
    st = Stadium(n_rows=8)
    seats, _, _ = st.seat_grid()
    fwd = simulate(apply_facing(basses, "front"), seats, st)
    ctr = simulate(apply_facing(basses, "center"), seats, st)

    assert np.max(np.abs(ctr.dba - fwd.dba)) < 0.15

    # ...and negligible against what the same flip does to a hornline.
    horns = [Performer("trumpet", x, 30.0) for x in (-7.5, -2.5, 2.5, 7.5)]
    h_fwd = simulate(apply_facing(horns, "front"), seats, st)
    h_ctr = simulate(apply_facing(horns, "center"), seats, st)
    assert np.abs(np.mean(h_ctr.dba - h_fwd.dba)) > 20.0 * np.abs(
        np.mean(ctr.dba - fwd.dba))


def test_reference_seats_stay_inside_a_short_grandstand():
    for n in (1, 2, 3, 40):
        st = Stadium(n_rows=n)
        seats = named_seats(st)
        lowest_y = -(st.apron_ft + (n - 1) * st.row_depth_ft)
        for pos in seats.values():
            assert pos[1] >= lowest_y - 1e-9, "seat extrapolated past row %d" % (n - 1)
    _expect(ValueError, lambda: named_seats(Stadium(n_rows=0)))


def test_malformed_drill_files_are_rejected_clearly():
    import os
    import tempfile

    d = tempfile.mkdtemp()

    def write(text):
        path = os.path.join(d, "x%d.csv" % abs(hash(text)))
        with open(path, "w") as fh:
            fh.write(text)
        return path

    _expect(ValueError, lambda: drill.load_csv(write("instrument,x_ft\ntrumpet,0\n")))
    _expect(ValueError, lambda: drill.load_csv(write("instrument,x_ft,y_ft\n")))
    _expect(ValueError, lambda: drill.load_csv(
        write("instrument,x_ft,y_ft\ntrumpet,zero,60\n")))

    try:
        drill.load_csv(write("instrument,x_ft,y_ft\ntrumpet,0,60\nkazoo,0,60\n"))
    except ValueError as e:
        assert "line 3" in str(e), str(e)
    else:
        raise AssertionError("expected ValueError naming the offending line")


def test_sections_sum_energetically_to_the_whole_ensemble():
    base = apply_facing(drill.arc_form(), "front")
    st = Stadium(n_rows=6)
    seats, _, _ = st.seat_grid()

    whole = simulate(base, seats, st)
    total = np.zeros((len(seats), 8))
    for name in {p.instrument for p in base}:
        part = [p for p in base if p.instrument == name]
        total += 10.0 ** (simulate(part, seats, st).band_spl / 10.0)
    assert np.allclose(10.0 * np.log10(total), whole.band_spl, atol=1e-9)


def test_a_symmetric_form_produces_a_symmetric_field():
    band = [Performer("trumpet", x, 60.0) for x in (-40.0, -20.0, 0.0, 20.0, 40.0)]
    pair = np.array([[-80.0, -30.0, 12.0], [80.0, -30.0, 12.0]])
    for mode in ("front", "center"):
        r = simulate(apply_facing(band, mode, focus=(0.0, 80.0)), pair)
        assert abs(r.dba[0] - r.dba[1]) < 1e-9, mode


def test_reflection_only_ever_adds_energy_and_can_be_switched_off():
    base = apply_facing(drill.arc_form(), "front")
    st = Stadium(n_rows=6)
    seats, _, _ = st.seat_grid()

    on = simulate(base, seats, st, Conditions(far_side_reflection=True))
    off = simulate(base, seats, st, Conditions(far_side_reflection=False))
    assert np.all(on.band_spl >= off.band_spl - 1e-9)

    dead = simulate(base, seats, Stadium(n_rows=6, far_side_absorption=(1.0,) * 8),
                    Conditions(far_side_reflection=True))
    assert np.allclose(dead.band_spl, off.band_spl, atol=1e-6)

    distant = simulate(base, seats, Stadium(n_rows=6, far_side_setback_ft=5000.0),
                       Conditions(far_side_reflection=True))
    assert np.allclose(distant.band_spl, off.band_spl, atol=0.05)


def test_level_falls_monotonically_with_distance():
    base = apply_facing(drill.arc_form(), "front")
    line = np.array([[0.0, -y, 12.0] for y in np.linspace(30.0, 400.0, 40)])
    lv = simulate(base, line, conditions=Conditions(far_side_reflection=False)).dba
    assert np.all(np.diff(lv) < 0.0)


def test_drill_csv_round_trips(tmp_path=None):
    import tempfile, os
    base = drill.block_form()
    d = tempfile.mkdtemp()
    path = os.path.join(d, "drill.csv")
    drill.save_csv(base, path)
    back = drill.load_csv(path)
    assert len(back) == len(base)
    assert all(
        a.instrument == b.instrument
        and abs(a.x - b.x) < 1e-3 and abs(a.y - b.y) < 1e-3
        and abs(a.fx - b.fx) < 1e-4 and abs(a.fy - b.fy) < 1e-4
        for a, b in zip(base, back)
    )


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("ok  %s" % fn.__name__)
    print("\n%d passed" % len(fns))
