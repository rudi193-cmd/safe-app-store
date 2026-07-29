"""Metrics tables and figures."""

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from .atmosphere import BANDS  # noqa: E402
from .engine import simulate  # noqa: E402
from .field import FIELD_WIDTH_FT, named_seats  # noqa: E402
from .instruments import CATALOG  # noqa: E402

SECTION_COLORS = {
    "trumpet": "#d64545", "mellophone": "#e08a1e", "baritone": "#3f7fbf",
    "contra": "#2f5d3a", "snare": "#7a5cbf", "tenor": "#9b7bd4",
    "bass": "#555555", "pit": "#9a9a9a",
}


def summarize(front, center, front_ref, center_ref, stadium):
    """Text summary comparing the two facings.

    `front`/`center` are results over the whole seat grid; `front_ref`/`center_ref`
    are results at the handful of reference seats from `named_seats`.
    """
    lines = []
    add = lines.append

    d_dba = center.dba - front.dba
    d_bright = center.brightness - front.brightness

    add("=" * 72)
    add("FIELD-FORWARD  vs  FACING CENTER   (negative = facing center is quieter)")
    add("=" * 72)
    add("")
    add("Across all seats:")
    add("  dBA          mean %+6.1f   min %+6.1f   max %+6.1f"
        % (d_dba.mean(), d_dba.min(), d_dba.max()))
    add("  brightness   mean %+6.1f   min %+6.1f   max %+6.1f   (HF/LF energy ratio, dB)"
        % (d_bright.mean(), d_bright.min(), d_bright.max()))
    add("")

    add("Per octave band, mean change across all seats (dB):")
    add("        " + "".join("%8s" % _fmt_hz(f) for f in BANDS))
    delta_band = _mean_energy_delta(center.band_spl, front.band_spl)
    add("        " + "".join("%+8.1f" % v for v in delta_band))
    add("")

    add("Reference seats:")
    header = "  %-26s %9s %9s %9s %9s" % ("", "dBA fwd", "dBA ctr", "delta", "d-bright")
    add(header)
    for i, label in enumerate(named_seats(stadium)):
        add("  %-26s %9.1f %9.1f %+9.1f %+9.1f" % (
            label, front_ref.dba[i], center_ref.dba[i],
            center_ref.dba[i] - front_ref.dba[i],
            center_ref.brightness[i] - front_ref.brightness[i],
        ))
    add("")

    add("Arrival structure (energy-weighted across the ensemble):")
    add("  %-26s %11s %11s" % ("", "forward", "center"))
    add("  %-26s %11.1f %11.1f" % ("mean arrival, ms",
                                   front.arrival_mean_ms.mean(),
                                   center.arrival_mean_ms.mean()))
    add("  %-26s %11.1f %11.1f" % ("spread (std), ms",
                                   front.arrival_spread_ms.mean(),
                                   center.arrival_spread_ms.mean()))
    add("  %-26s %11.1f %11.1f" % ("reflected/direct, dBA",
                                   front.reflected_ratio_db.mean(),
                                   center.reflected_ratio_db.mean()))
    add("")
    return "\n".join(lines)


def _fmt_hz(f):
    return "%gk" % (f / 1000) if f >= 1000 else "%g" % f


def _mean_energy_delta(a, b):
    """Mean per-band delta, averaged on an energy basis over receivers."""
    ea = 10.0 * np.log10(np.mean(10.0 ** (a / 10.0), axis=0))
    eb = 10.0 * np.log10(np.mean(10.0 ** (b / 10.0), axis=0))
    return ea - eb


def plot_stands(front, center, xs, rows, path, quantity="dba", title=None):
    """Three-panel heat map over the grandstand: forward, center, delta."""
    getter = {
        "dba": lambda r: r.dba,
        "brightness": lambda r: r.brightness,
        "hf4k": lambda r: r.band_spl[:, 6],
    }[quantity]

    a = getter(front).reshape(len(xs), len(rows)).T
    b = getter(center).reshape(len(xs), len(rows)).T
    d = b - a

    fig, axes = plt.subplots(1, 3, figsize=(16, 4.6), constrained_layout=True)
    # imshow reads `extent` as the outer edges of the image, but xs/rows are
    # cell centres, so passing them raw misregisters every map by half a cell.
    dx = (xs[1] - xs[0]) / 2.0 if len(xs) > 1 else 0.5
    dr = (rows[1] - rows[0]) / 2.0 if len(rows) > 1 else 0.5
    extent = [xs[0] - dx, xs[-1] + dx, rows[0] - dr, rows[-1] + dr]
    vmin, vmax = min(a.min(), b.min()), max(a.max(), b.max())

    for ax, data, name, cmap, lim in (
        (axes[0], a, "field forward", "magma", (vmin, vmax)),
        (axes[1], b, "facing center", "magma", (vmin, vmax)),
        (axes[2], d, "difference", "RdBu_r", (-np.abs(d).max(), np.abs(d).max())),
    ):
        im = ax.imshow(data, origin="lower", aspect="auto", extent=extent,
                       cmap=cmap, vmin=lim[0], vmax=lim[1])
        ax.set_title(name, fontsize=11)
        ax.set_xlabel("position along the stands (ft from the 50)")
        ax.set_ylabel("row")
        fig.colorbar(im, ax=ax, shrink=0.9)

    unit = {"dba": "dBA", "brightness": "HF/LF ratio, dB", "hf4k": "4 kHz band, dB"}[quantity]
    fig.suptitle(title or ("Audience %s" % unit), fontsize=13)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_drill(front_performers, center_performers, path):
    """Plan view of the form with facing arrows for both configurations."""
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.6), constrained_layout=True)

    for ax, performers, title in (
        (axes[0], front_performers, "field forward"),
        (axes[1], center_performers, "facing center"),
    ):
        ax.add_patch(Rectangle((-150, 0), 300, FIELD_WIDTH_FT,
                               facecolor="#eef4ea", edgecolor="#9bbf9b", zorder=0))
        for yl in range(-150, 151, 15):
            ax.plot([yl, yl], [0, FIELD_WIDTH_FT], color="#c8dcc8", lw=0.7, zorder=1)
        for hy in (60.0, 100.0):
            ax.plot([-150, 150], [hy, hy], color="#c8dcc8", lw=0.7, ls="--", zorder=1)

        for p in performers:
            col = SECTION_COLORS.get(p.instrument, "#333333")
            ax.scatter(p.x, p.y, s=16, color=col, zorder=3)
            ax.arrow(p.x, p.y, p.fx * 7.0, p.fy * 7.0, head_width=2.0,
                     head_length=2.2, fc=col, ec=col, lw=0.6, zorder=2, alpha=0.75)

        ax.axhline(0.0, color="#444", lw=1.2)
        ax.text(-146, -8, "audience this way", fontsize=9, color="#444")
        ax.set_xlim(-155, 155)
        ax.set_ylim(-16, FIELD_WIDTH_FT + 6)
        ax.set_aspect("equal")
        ax.set_title(title)
        ax.set_xlabel("feet from the 50")
        ax.set_ylabel("feet from the front sideline")

    fig.suptitle("Drill and bell orientation", fontsize=13)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_spectra(front_ref, center_ref, stadium, path):
    """Octave-band spectra at the reference seats."""
    front, center = front_ref, center_ref
    seats = list(named_seats(stadium).items())
    fig, axes = plt.subplots(1, len(seats), figsize=(4.2 * len(seats), 4.0),
                             constrained_layout=True, sharey=True)

    for i, (ax, (label, _)) in enumerate(zip(np.atleast_1d(axes), seats)):
        ax.semilogx(BANDS, front.band_spl[i], "o-", color="#d64545", label="field forward")
        ax.semilogx(BANDS, center.band_spl[i], "s-", color="#3f7fbf", label="facing center")
        ax.set_xticks(BANDS)
        ax.set_xticklabels([_fmt_hz(f) for f in BANDS], fontsize=8)
        ax.grid(alpha=0.3, which="both")
        ax.set_title(label, fontsize=10)
        ax.set_xlabel("Hz")
        if i == 0:
            ax.set_ylabel("band SPL, dB")
            ax.legend(fontsize=9)

    fig.suptitle("Spectrum at reference seats", fontsize=13)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def section_breakdown(performers_front, performers_center, receivers, stadium, conditions):
    """How much each section gains or loses when the form turns in."""
    rows = []
    sections = sorted({p.instrument for p in performers_front})
    for name in sections:
        f = [p for p in performers_front if p.instrument == name]
        c = [p for p in performers_center if p.instrument == name]
        rf = simulate(f, receivers, stadium, conditions)
        rc = simulate(c, receivers, stadium, conditions)
        rows.append((name, len(f), rf.dba.mean(), rc.dba.mean(),
                     rc.dba.mean() - rf.dba.mean(),
                     rc.brightness.mean() - rf.brightness.mean()))

    out = ["Per-section change, averaged over all seats:",
           "  %-12s %5s %10s %10s %9s %10s"
           % ("section", "n", "dBA fwd", "dBA ctr", "delta", "d-bright")]
    for name, n, a, b, d, db in rows:
        out.append("  %-12s %5d %10.1f %10.1f %+9.1f %+10.1f" % (name, n, a, b, d, db))
    return "\n".join(out)
