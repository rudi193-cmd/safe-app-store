"""Read measured instrument directivity from AES69 (SOFA) files.

This module ships **no data**. It reads a SOFA file you supply and reduces it to
the same (band, theta) table the analytic model produces, so measured
directivity can be dropped in wherever a fitted curve is currently used.

Why no data: the two comprehensive open databases have incompatible terms. The
BYU Spatial Audio Library defaults to CC BY 4.0 -- attribution only, compatible
with this project's Apache-2.0 licence, and usable commercially, which matters
because programs pay for things. The TU Berlin database is CC BY-NC-SA, and the
non-commercial clause would propagate to anyone using this tool. So the loader
is general, the licence stays clean, and you point it at whatever you have:

    from dcisim.sofa import load_directivity
    table = load_directivity("trumpet.sofa")          # (8, n_theta), on-axis 1.0
    TRUMPET.set_measured(table, citation="Bellows et al., BYU ...")

The reduction is deliberately lossy in one specific way: the engine's model is
axisymmetric about the bell axis, so measured data is averaged over azimuth at
each polar angle. Real instruments are not axisymmetric -- the player's body is
on one side -- and that asymmetry is discarded here rather than silently
half-used. `azimuthal_asymmetry_db` reports how much was thrown away so you can
judge whether it mattered.
"""

import numpy as np

from .atmosphere import BANDS

# SOFA is NetCDF-4, i.e. HDF5. h5py is an optional dependency: the analytic
# model works without it and the import cost is only paid if you load a file.
try:  # pragma: no cover - trivial import guard
    import h5py
    _HAVE_H5PY = True
except ImportError:  # pragma: no cover
    _HAVE_H5PY = False


class SofaError(Exception):
    """Raised when a file is not readable as directivity data."""


def _require_h5py():
    if not _HAVE_H5PY:
        raise SofaError(
            "reading SOFA files needs h5py (pip install h5py). The analytic "
            "directivity model works without it."
        )


def _attr(obj, name, default=""):
    v = obj.attrs.get(name, default)
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    if isinstance(v, np.ndarray) and v.size == 1:
        v = v.reshape(-1)[0]
        return v.decode("utf-8", "replace") if isinstance(v, bytes) else str(v)
    return str(v)


def _positions_to_unit_vectors(pos, coord_type, units):
    """(n, 3) positions in the file's coordinate system -> unit vectors."""
    pos = np.asarray(pos, dtype=float)
    if pos.ndim == 3:
        # [n][C][I] or [n][C][M]; take the first slice along the trailing axis.
        pos = pos[:, :, 0]
    if pos.ndim != 2 or pos.shape[1] < 3:
        raise SofaError("position array has shape %s; expected (n, 3)" % (pos.shape,))

    if "spherical" in coord_type.lower():
        az, el = pos[:, 0], pos[:, 1]
        if "rad" not in units.lower():
            az, el = np.radians(az), np.radians(el)
        xyz = np.stack([
            np.cos(el) * np.cos(az),
            np.cos(el) * np.sin(az),
            np.sin(el),
        ], axis=1)
    else:
        xyz = pos[:, :3]

    norm = np.linalg.norm(xyz, axis=1, keepdims=True)
    if np.any(norm < 1e-12):
        raise SofaError("a receiver position is at the origin; cannot form a direction")
    return xyz / norm


def _band_average(freqs, mag, bands=BANDS):
    """Power-average |H| over each octave band. mag is (..., n_freq)."""
    out = np.empty(mag.shape[:-1] + (len(bands),))
    power = mag**2
    for i, fc in enumerate(bands):
        lo, hi = fc / np.sqrt(2.0), fc * np.sqrt(2.0)
        sel = (freqs >= lo) & (freqs < hi)
        if not np.any(sel):
            # No measured content in this band -- mark it rather than inventing.
            out[..., i] = np.nan
        else:
            out[..., i] = np.sqrt(np.mean(power[..., sel], axis=-1))
    return out


def read_sofa(path):
    """Parse a SOFA directivity file into raw per-receiver band magnitudes.

    Returns a dict with `directions` (n_recv, 3 unit vectors), `band_mag`
    (n_recv, n_bands), `convention`, and `n_measurements`.
    """
    _require_h5py()

    with h5py.File(path, "r") as f:
        convention = _attr(f, "SOFAConventions", "unknown")
        data_type = _attr(f, "DataType", "unknown")

        if "Data.Real" in f and "Data.Imag" in f:
            real = np.asarray(f["Data.Real"])
            imag = np.asarray(f["Data.Imag"])
            mag = np.abs(real + 1j * imag)  # (M, R, N)
        elif "Data.IR" in f:
            # Impulse responses: transform, then use magnitude.
            ir = np.asarray(f["Data.IR"])  # (M, R, N)
            mag = np.abs(np.fft.rfft(ir, axis=-1))
        else:
            raise SofaError(
                "%s has neither Data.Real/Data.Imag nor Data.IR; it does not look "
                "like a directivity or impulse-response file (DataType=%r, "
                "SOFAConventions=%r)" % (path, data_type, convention)
            )

        if "N" in f:
            freqs = np.asarray(f["N"], dtype=float).reshape(-1)
        else:
            raise SofaError("%s has no frequency variable 'N'" % path)

        if mag.ndim != 3:
            raise SofaError("expected 3-D (M, R, N) data, got shape %s" % (mag.shape,))
        if mag.shape[-1] != len(freqs):
            if mag.shape[-1] == len(freqs) // 2 + 1:
                freqs = np.fft.rfftfreq(len(freqs), d=1.0 / (2.0 * freqs[-1]))
            else:
                raise SofaError(
                    "frequency axis mismatch: data has %d bins, N has %d values"
                    % (mag.shape[-1], len(freqs))
                )

        if "ReceiverPosition" not in f:
            raise SofaError("%s has no ReceiverPosition" % path)
        rp = f["ReceiverPosition"]
        directions = _positions_to_unit_vectors(
            np.asarray(rp), _attr(rp, "Type", "cartesian"), _attr(rp, "Units", "degree")
        )

        if directions.shape[0] != mag.shape[1]:
            raise SofaError(
                "ReceiverPosition has %d entries but data has %d receivers"
                % (directions.shape[0], mag.shape[1])
            )

        # Average across measurements (notes, repetitions) on a power basis.
        band_mag = _band_average(freqs, mag)  # (M, R, bands)
        band_mag = np.sqrt(np.nanmean(band_mag**2, axis=0))  # (R, bands)

    return {
        "directions": directions,
        "band_mag": band_mag,
        "convention": convention,
        "n_measurements": mag.shape[0],
        "n_receivers": mag.shape[1],
    }


def _reference_axis(directions, band_mag, axis=None):
    """The instrument's acoustic axis as a unit vector.

    Defaults to the direction of greatest broadband energy, which is what an
    unaligned measurement needs. Files that already place the frontal axis at
    (1, 0, 0) resolve to the same answer.
    """
    if axis is not None:
        axis = np.asarray(axis, dtype=float)
        return axis / np.linalg.norm(axis)
    energy = np.nansum(band_mag**2, axis=1)
    return directions[int(np.argmax(energy))]


def reduce_to_axisymmetric(raw, axis=None, n_theta=181, min_per_bin=1):
    """Collapse measured directions to the engine's (band, theta) table.

    Returns (table, info). `table` is (n_bands, n_theta), 1.0 on axis. `info`
    carries the discarded azimuthal asymmetry and any bands with no coverage.
    """
    directions, band_mag = raw["directions"], raw["band_mag"]
    ref = _reference_axis(directions, band_mag, axis)

    cos_t = np.clip(directions @ ref, -1.0, 1.0)
    theta = np.arccos(cos_t)

    grid = np.linspace(0.0, np.pi, n_theta)
    edges = np.concatenate([[0.0], (grid[1:] + grid[:-1]) / 2.0, [np.pi]])
    idx = np.clip(np.searchsorted(edges, theta) - 1, 0, n_theta - 1)

    n_bands = band_mag.shape[1]
    table = np.full((n_bands, n_theta), np.nan)
    spread = np.zeros((n_bands, n_theta))

    for b in range(n_bands):
        for t in range(n_theta):
            vals = band_mag[idx == t, b]
            vals = vals[np.isfinite(vals)]
            if len(vals) >= min_per_bin:
                table[b, t] = np.sqrt(np.mean(vals**2))
                if len(vals) > 1:
                    spread[b, t] = 20.0 * np.log10(
                        np.max(vals) / max(np.min(vals), 1e-12))

    # Fill gaps by interpolation across theta, per band.
    for b in range(n_bands):
        row = table[b]
        good = np.isfinite(row)
        if not good.any():
            continue
        table[b] = np.interp(grid, grid[good], row[good])

    empty_bands = [int(BANDS[b]) for b in range(n_bands)
                   if not np.isfinite(table[b]).any()]

    # Normalise so on-axis is unity, matching the analytic model's convention.
    on_axis = table[:, :1].copy()
    on_axis[~np.isfinite(on_axis) | (on_axis <= 0)] = 1.0
    table = table / on_axis

    info = {
        "axis": ref,
        "azimuthal_asymmetry_db": float(np.nanmax(spread)) if spread.size else 0.0,
        "mean_asymmetry_db": float(np.nanmean(spread)) if spread.size else 0.0,
        "empty_bands_hz": empty_bands,
        "n_receivers": raw["n_receivers"],
        "n_measurements": raw["n_measurements"],
        "convention": raw["convention"],
    }
    return np.nan_to_num(table, nan=1e-6), info


def load_directivity(path, axis=None, n_theta=181):
    """Read a SOFA file and return a (n_bands, n_theta) directivity table."""
    return reduce_to_axisymmetric(read_sofa(path), axis=axis, n_theta=n_theta)


def describe(path):
    """Human-readable summary of what a SOFA file contains."""
    raw = read_sofa(path)
    table, info = reduce_to_axisymmetric(raw)
    lines = [
        "%s" % path,
        "  convention        %s" % info["convention"],
        "  receivers         %d" % info["n_receivers"],
        "  measurements      %d" % info["n_measurements"],
        "  acoustic axis     [%+.3f %+.3f %+.3f]" % tuple(info["axis"]),
        "  azimuthal spread  %.1f dB max, %.1f dB mean (discarded by the "
        "axisymmetric model)" % (info["azimuthal_asymmetry_db"],
                                 info["mean_asymmetry_db"]),
    ]
    if info["empty_bands_hz"]:
        lines.append("  NO COVERAGE in   %s Hz" % info["empty_bands_hz"])
    db = 20.0 * np.log10(np.maximum(table, 1e-6))
    lines.append("  on-axis / 90 / 180 dB, per band:")
    mid, back = table.shape[1] // 2, table.shape[1] - 1
    for i, f in enumerate(BANDS[: table.shape[0]]):
        lines.append("    %6s  %6.1f %6.1f %6.1f"
                     % (int(f), db[i, 0], db[i, mid], db[i, back]))
    return "\n".join(lines)
