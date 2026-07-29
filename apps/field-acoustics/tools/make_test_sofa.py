#!/usr/bin/env python3
"""Write a synthetic AES69 (SOFA) directivity file with a known pattern.

Used to test `dcisim.sofa` without redistributing anyone's measurements. The
pattern is a circular piston of a chosen radius, so the loader's output can be
checked against the closed form rather than against a fixture nobody can verify.

    python tools/make_test_sofa.py out.sofa --radius 0.062
"""

import argparse

import numpy as np
from scipy.special import j1


def fibonacci_sphere(n):
    """n roughly-equidistant unit vectors, +x as the reference axis."""
    i = np.arange(n, dtype=float) + 0.5
    phi = np.arccos(1.0 - 2.0 * i / n)          # polar from +x
    theta = np.pi * (1.0 + 5.0**0.5) * i        # golden-angle azimuth
    return np.stack([
        np.cos(phi),
        np.sin(phi) * np.cos(theta),
        np.sin(phi) * np.sin(theta),
    ], axis=1)


def piston_response(directions, freqs, radius_m, c=346.0, axis=(1.0, 0.0, 0.0)):
    """|2 J1(u)/u| for each direction and frequency, floored to stay physical."""
    axis = np.asarray(axis, dtype=float)
    axis = axis / np.linalg.norm(axis)
    sin_t = np.sqrt(np.clip(1.0 - (directions @ axis) ** 2, 0.0, 1.0))
    u = np.outer(sin_t, 2.0 * np.pi * freqs / c * radius_m)
    with np.errstate(divide="ignore", invalid="ignore"):
        d = np.where(u == 0.0, 1.0, 2.0 * j1(np.where(u == 0.0, 1.0, u)) / np.where(u == 0.0, 1.0, u))
    return np.maximum(np.abs(d), 1e-4)


def write_sofa(path, directions, freqs, mag, convention="FreeFieldDirectivityTF"):
    """Write a minimal but conformant SOFA TF file. mag is (R, N)."""
    import h5py

    r, n = mag.shape
    with h5py.File(path, "w") as f:
        f.attrs["Conventions"] = "SOFA"
        f.attrs["SOFAConventions"] = convention
        f.attrs["SOFAConventionsVersion"] = "1.1"
        f.attrs["Version"] = "2.1"
        f.attrs["DataType"] = "TF"
        f.attrs["RoomType"] = "free field"
        f.attrs["Title"] = "synthetic piston directivity (test fixture)"
        f.attrs["DateCreated"] = "2026-07-28 00:00:00"
        f.attrs["DateModified"] = "2026-07-28 00:00:00"
        f.attrs["APIName"] = "dcisim.tools.make_test_sofa"
        f.attrs["APIVersion"] = "1.0"
        f.attrs["AuthorContact"] = "n/a"
        f.attrs["License"] = "Apache-2.0"
        f.attrs["Organization"] = "n/a"

        # M=1 measurement, R receivers, N frequencies.
        f.create_dataset("Data.Real", data=mag[None, :, :].astype(float))
        f.create_dataset("Data.Imag", data=np.zeros((1, r, n), dtype=float))
        nvar = f.create_dataset("N", data=np.asarray(freqs, dtype=float))
        nvar.attrs["LongName"] = "frequency"
        nvar.attrs["Units"] = "hertz"

        # Cartesian receiver positions on the unit sphere, shaped [R][C][I].
        rp = f.create_dataset("ReceiverPosition",
                              data=directions[:, :, None].astype(float))
        rp.attrs["Type"] = "cartesian"
        rp.attrs["Units"] = "metre"

        for name, val in (("ListenerPosition", [0.0, 0.0, 0.0]),
                          ("SourcePosition", [0.0, 0.0, 0.0]),
                          ("EmitterPosition", [0.0, 0.0, 0.0])):
            d = f.create_dataset(name, data=np.asarray(val, dtype=float)[None, :, None])
            d.attrs["Type"] = "cartesian"
            d.attrs["Units"] = "metre"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out")
    ap.add_argument("--radius", type=float, default=0.062, help="piston radius, m")
    ap.add_argument("--receivers", type=int, default=1024)
    ap.add_argument("--freqs", type=int, default=240)
    args = ap.parse_args()

    directions = fibonacci_sphere(args.receivers)
    freqs = np.geomspace(45.0, 11500.0, args.freqs)
    mag = piston_response(directions, freqs, args.radius)
    write_sofa(args.out, directions, freqs, mag)
    print("wrote %s: %d receivers x %d frequencies, piston radius %.3f m"
          % (args.out, len(directions), len(freqs), args.radius))


if __name__ == "__main__":
    main()
