"""The propagation engine.

For every (performer, receiver) pair, per octave band:

    Lp = Lw + D(theta, f) - 20*log10(r) - 11 - alpha(f)*r

summed on an energy basis across the ensemble, because independent players are
mutually incoherent. Optionally a specular image source across the far-side
grandstand is added, which matters here: when the hornline turns in, a large
share of the energy is thrown at the far stands, and some of it comes back as a
distinctly late arrival.

Everything the engine touches is metres and radians. Feet stay at the edges.
"""

from dataclasses import dataclass

import numpy as np

from .atmosphere import A_WEIGHT, BANDS, absorption_coefficients, speed_of_sound
from .field import FT_PER_M, Stadium
from .instruments import CATALOG

LF_BANDS = slice(1, 4)  # 125 / 250 / 500
HF_BANDS = slice(5, 8)  # 2k / 4k / 8k


@dataclass
class Conditions:
    temp_c: float = 24.0
    humidity_pct: float = 55.0
    pressure_kpa: float = 101.325
    ground_effect: bool = False  # see note in README; near common-mode here
    far_side_reflection: bool = True


@dataclass
class Result:
    band_spl: np.ndarray  # (n_receivers, n_bands), direct + reflected
    direct_spl: np.ndarray
    reflected_spl: np.ndarray
    arrival_mean_ms: np.ndarray  # energy-weighted, dBA-weighted arrival time
    arrival_spread_ms: np.ndarray  # energy-weighted std of arrival times

    @property
    def dba(self):
        return 10.0 * np.log10(
            np.sum(10.0 ** ((self.band_spl + A_WEIGHT) / 10.0), axis=1)
        )

    @property
    def brightness(self):
        """HF-to-LF energy ratio in dB. The timbre headline."""
        hf = np.sum(10.0 ** (self.band_spl[:, HF_BANDS] / 10.0), axis=1)
        lf = np.sum(10.0 ** (self.band_spl[:, LF_BANDS] / 10.0), axis=1)
        return 10.0 * np.log10(hf / lf)

    @property
    def reflected_ratio_db(self):
        """Reflected energy relative to direct, A-weighted."""
        r = np.sum(10.0 ** ((self.reflected_spl + A_WEIGHT) / 10.0), axis=1)
        d = np.sum(10.0 ** ((self.direct_spl + A_WEIGHT) / 10.0), axis=1)
        return 10.0 * np.log10(np.maximum(r, 1e-30) / np.maximum(d, 1e-30))


# Sources are point radiators, so the spreading term diverges as r -> 0. Clamp
# well inside any real listening position; a receiver closer than this to a bell
# is not a seat, it is the inside of the instrument.
MIN_RANGE_M = 0.5

SILENT_DB = -300.0


def _validate(performers, receivers_ft):
    """Fail loudly on inputs that would otherwise produce silent nonsense."""
    for i, p in enumerate(performers):
        if p.instrument not in CATALOG:
            raise ValueError(
                "performer %d has unknown instrument %r; known: %s"
                % (i, p.instrument, ", ".join(sorted(CATALOG)))
            )
        if not np.all(np.isfinite([p.x, p.y, p.fx, p.fy])):
            raise ValueError(
                "performer %d (%s) has a non-finite coordinate or facing"
                % (i, p.instrument)
            )
        if np.hypot(p.fx, p.fy) < 1e-9:
            raise ValueError(
                "performer %d (%s) has a zero-length facing vector; a bell has "
                "to point somewhere" % (i, p.instrument)
            )

    rcv = np.asarray(receivers_ft, dtype=float)
    if rcv.ndim != 2 or rcv.shape[1] != 3:
        raise ValueError("receivers must be an (n, 3) array of feet, got shape %s"
                         % (rcv.shape,))
    if not np.all(np.isfinite(rcv)):
        raise ValueError("receiver positions contain non-finite values")
    return rcv


def _silence(n_receivers):
    spl = np.full((n_receivers, len(BANDS)), SILENT_DB)
    nan = np.full(n_receivers, np.nan)
    return Result(band_spl=spl, direct_spl=spl.copy(), reflected_spl=spl.copy(),
                  arrival_mean_ms=nan, arrival_spread_ms=nan.copy())


def _bell_axes(performers):
    """3D unit bell axes, with power weights. Shape (n_lobes, 3) and (n_lobes,).

    Instruments with a non-zero azimuth offset radiate from two opposed faces
    (marching bass drums), so they get two half-power lobes.
    """
    axes, weights, owner = [], [], []
    for i, p in enumerate(performers):
        inst = CATALOG[p.instrument]
        offsets = [inst.bell_azimuth_offset_deg]
        w = [1.0]
        if abs(inst.bell_azimuth_offset_deg) > 1e-6:
            offsets = [inst.bell_azimuth_offset_deg, -inst.bell_azimuth_offset_deg]
            w = [0.5, 0.5]

        el = np.radians(inst.bell_elevation_deg)
        for off, wi in zip(offsets, w):
            phi = np.radians(off)
            ax = p.fx * np.cos(phi) - p.fy * np.sin(phi)
            ay = p.fx * np.sin(phi) + p.fy * np.cos(phi)
            n = np.hypot(ax, ay) or 1.0
            axes.append([ax / n * np.cos(el), ay / n * np.cos(el), np.sin(el)])
            weights.append(wi)
            owner.append(i)
    return np.array(axes), np.array(weights), np.array(owner)


def _ground_excess_db(src_m, rcv_m, sub_freqs, c):
    """Two-path interference over soft ground, power-averaged within each band."""
    r_mag = np.array([0.90, 0.85, 0.75, 0.62, 0.48, 0.35, 0.25, 0.18])
    hs = src_m[:, None, 2]
    hr = rcv_m[None, :, 2]
    d = np.linalg.norm(src_m[:, None, :2] - rcv_m[None, :, :2], axis=2)

    direct = np.sqrt((hs - hr) ** 2 + d**2)
    image = np.sqrt((hs + hr) ** 2 + d**2)
    delta = image - direct  # (S, R)

    out = np.empty((len(BANDS), delta.shape[0], delta.shape[1]))
    for b in range(len(BANDS)):
        phase = 2.0 * np.pi * sub_freqs[b][None, None, :] * delta[..., None] / c
        p = np.abs(1.0 - r_mag[b] * np.exp(1j * phase)) ** 2
        out[b] = 10.0 * np.log10(np.maximum(np.mean(p, axis=2), 10.0 ** -1.0))
    return out


def simulate(performers, receivers_ft, stadium=None, conditions=None):
    """Run the model.

    `receivers_ft` is (n, 3) in feet. Returns a `Result`.
    """
    stadium = stadium or Stadium()
    cond = conditions or Conditions()

    rcv_ft = _validate(performers, receivers_ft)
    if not performers:
        return _silence(len(rcv_ft))

    c = speed_of_sound(cond.temp_c)
    alpha = absorption_coefficients(
        BANDS, cond.temp_c, cond.humidity_pct, cond.pressure_kpa
    )
    # Linear, not log, spacing, and enough points to resolve the interference
    # comb. The ground term's phase sweeps several full cycles across the top
    # octave, so 7 log-spaced points both biased the bottom three bands by
    # ~0.2 dB and aliased the top ones by up to 1 dB.
    sub_freqs = [np.linspace(f / np.sqrt(2), f * np.sqrt(2), 61) for f in BANDS]

    src_ft = np.array([
        [p.x, p.y, CATALOG[p.instrument].bell_height_m * FT_PER_M] for p in performers
    ])
    src_m = src_ft / FT_PER_M
    rcv_m = rcv_ft / FT_PER_M

    axes, lobe_w, owner = _bell_axes(performers)
    power = np.array([CATALOG[p.instrument].power_db for p in performers])
    dirs = [CATALOG[p.instrument].directivity(cond.temp_c) for p in performers]

    def path(src, axes_xyz, extra_db=None):
        """Energy and arrival times for one set of source points and bell axes."""
        vec = rcv_m[None, :, :] - src[:, None, :]  # (S, R, 3)
        true_r = np.linalg.norm(vec, axis=2)
        # Direction must be normalised by the TRUE range. Using the clamped
        # range here leaves `unit` short for anything inside MIN_RANGE_M, which
        # drags every direction cosine toward zero and collapses the pattern
        # toward 90 degrees -- a trumpet's 8 kHz front-to-back ratio fell from
        # 24 dB to 1 dB at 0.1 m. The clamp exists to bound the spreading term,
        # nothing else.
        unit = vec / np.maximum(true_r, 1e-12)[..., None]
        r = np.maximum(true_r, MIN_RANGE_M)

        cos_t = np.einsum("sd,srd->sr", axes_xyz, unit)
        theta = np.arccos(np.clip(cos_t, -1.0, 1.0))

        spread = -20.0 * np.log10(r) - 11.0  # (S, R)
        energy = np.zeros((r.shape[1], len(BANDS)))

        # (bands, S, R): directivity has to be evaluated per source since each
        # instrument carries its own aperture.
        lp = np.empty((len(BANDS), r.shape[0], r.shape[1]))
        for s in range(r.shape[0]):
            g = dirs[owner[s]].gain_db(theta[s])  # (bands, R)
            lp[:, s, :] = (
                power[owner[s]][:, None]
                + g
                + spread[s][None, :]
                - alpha[:, None] * r[s][None, :]
                + 10.0 * np.log10(lobe_w[s])
            )

        if extra_db is not None:
            lp = lp + extra_db
        if cond.ground_effect:
            lp = lp + _ground_excess_db(src, rcv_m, sub_freqs, c)

        e = 10.0 ** (lp / 10.0)  # (bands, S, R)
        energy = np.sum(e, axis=1).T  # (R, bands)
        return energy, e, r / c * 1000.0  # ms

    direct_e, direct_full, t_direct = path(src_m[owner], axes)

    refl_e = np.zeros_like(direct_e)
    refl_full = np.zeros_like(direct_full)
    t_refl = None
    if cond.far_side_reflection and stadium.far_side:
        img_ft = stadium.mirror(src_ft[owner])
        img_m = img_ft / FT_PER_M
        img_axes = axes.copy()
        img_axes[:, 1] *= -1.0

        absorb = np.asarray(stadium.far_side_absorption, dtype=float)
        refl_db = 10.0 * np.log10(np.maximum(1.0 - absorb, 1e-4))[:, None, None]

        valid = _reflection_valid(img_m, rcv_m, stadium)
        gate = np.where(valid, 0.0, -300.0)[None, :, :]

        refl_e, refl_full, t_refl = path(img_m, img_axes, extra_db=refl_db + gate)

    total_e = direct_e + refl_e
    band_spl = 10.0 * np.log10(np.maximum(total_e, 1e-30))

    # Energy-weighted arrival statistics, A-weighted so the numbers track what
    # the ear actually uses to judge blend and slap.
    aw = 10.0 ** (A_WEIGHT / 10.0)[:, None, None]
    w = direct_full * aw
    times = np.broadcast_to(t_direct[None, :, :], w.shape)
    if t_refl is not None:
        w = np.concatenate([w, refl_full * aw], axis=1)
        times = np.concatenate(
            [times, np.broadcast_to(t_refl[None, :, :], refl_full.shape)], axis=1
        )

    wsum = np.sum(w, axis=(0, 1))
    mean_t = np.sum(w * times, axis=(0, 1)) / np.maximum(wsum, 1e-30)
    var_t = np.sum(w * (times - mean_t[None, None, :]) ** 2, axis=(0, 1)) / np.maximum(
        wsum, 1e-30
    )

    return Result(
        band_spl=band_spl,
        direct_spl=10.0 * np.log10(np.maximum(direct_e, 1e-30)),
        reflected_spl=10.0 * np.log10(np.maximum(refl_e, 1e-30)),
        arrival_mean_ms=mean_t,
        arrival_spread_ms=np.sqrt(np.maximum(var_t, 0.0)),
    )


def _reflection_valid(img_m, rcv_m, stadium):
    """True where the image-source ray actually strikes the far grandstand face."""
    plane_y = stadium.far_side_plane_y / FT_PER_M
    sy = img_m[:, None, 1]
    ry = rcv_m[None, :, 1]
    denom = sy - ry
    # Guard the divisor before dividing: np.where evaluates both branches, so
    # the naive form still warns on source/receiver pairs at equal y.
    safe = np.where(np.abs(denom) < 1e-9, np.nan, denom)
    t = (sy - plane_y) / safe

    x = img_m[:, None, 0] + t * (rcv_m[None, :, 0] - img_m[:, None, 0])
    z = img_m[:, None, 2] + t * (rcv_m[None, :, 2] - img_m[:, None, 2])

    half_w = stadium.half_width_ft / FT_PER_M
    max_h = stadium.far_side_height_ft / FT_PER_M
    ok = (t > 0.0) & (t < 1.0) & (np.abs(x) <= half_w) & (z >= 0.0) & (z <= max_h)
    return np.nan_to_num(ok.astype(float), nan=0.0) > 0.5
