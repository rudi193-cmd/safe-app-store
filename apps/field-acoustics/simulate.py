#!/usr/bin/env python3
"""Compare an ensemble facing the front sideline against the same ensemble,
in the same coordinates, facing the middle of the field.

    python simulate.py                          # default corps, arc form
    python simulate.py --form block
    python simulate.py --drill mydrill.csv      # your real coordinates
    python simulate.py --focus 0 80 --battery-front
    python simulate.py --humidity 30 --temp 33  # dry, hot: HF dies faster
"""

import argparse
import os

import numpy as np

from dcisim import drill, report
from dcisim.engine import Conditions, simulate
from dcisim.field import FIELD_CENTER, Stadium, named_seats


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--form", choices=sorted(drill.FORMS), default="arc",
                   help="built-in form to use when --drill is not given")
    p.add_argument("--drill", help="CSV of real drill coordinates")
    p.add_argument("--focus", nargs=2, type=float, metavar=("X", "Y"),
                   help="point everyone faces in the 'center' config, feet "
                        "(default: middle of the field, 0 80)")
    p.add_argument("--battery-front", action="store_true",
                   help="keep the battery facing the box even when the horns turn in")
    p.add_argument("--temp", type=float, default=24.0, help="air temperature, C")
    p.add_argument("--humidity", type=float, default=55.0, help="relative humidity, %%")
    p.add_argument("--no-reflection", action="store_true",
                   help="disable the far-side grandstand reflection")
    p.add_argument("--ground-effect", action="store_true",
                   help="enable the approximate soft-ground interference term")
    p.add_argument("--rows", type=int, default=40, help="rows in the grandstand")
    p.add_argument("--out", default="out", help="output directory")
    p.add_argument("--sections", action="store_true",
                   help="also compute the per-section breakdown (slower)")
    p.add_argument("--sofa", nargs=2, action="append", metavar=("INSTRUMENT", "FILE"),
                   help="load measured directivity from a SOFA file, e.g. "
                        "--sofa trumpet byu_trumpet.sofa. Repeatable. No data "
                        "ships with this tool; see README for sources.")
    p.add_argument("--cite", default="",
                   help="citation recorded for --sofa data (required with --sofa)")
    p.add_argument("--provenance", action="store_true",
                   help="print where every input came from and stop")
    return p.parse_args()


def apply_sofa(args):
    """Attach measured directivity to instruments named on the command line."""
    from dcisim.instruments import CATALOG
    from dcisim.sofa import load_directivity

    if not args.sofa:
        return
    if not args.cite.strip():
        raise ValueError(
            "--sofa needs --cite: measured data whose source nobody can look up "
            "is not meaningfully better than a fitted curve"
        )
    for name, path in args.sofa:
        if name not in CATALOG:
            raise ValueError("unknown instrument %r; known: %s"
                             % (name, ", ".join(sorted(CATALOG))))
        table, info = load_directivity(path)
        CATALOG[name].set_measured(table, citation=args.cite)
        print("loaded %s -> %s (%d receivers, %.1f dB azimuthal spread discarded)"
              % (path, name, info["n_receivers"], info["azimuthal_asymmetry_db"]))
        if info["empty_bands_hz"]:
            print("  WARNING: no measured coverage in %s Hz; those bands are "
                  "interpolated" % info["empty_bands_hz"])


def main():
    args = parse_args()
    if args.rows < 1:
        raise SystemExit("error: --rows must be at least 1, got %d" % args.rows)

    apply_sofa(args)

    if args.provenance:
        from dcisim.provenance import model_provenance
        print(model_provenance().report())
        return

    os.makedirs(args.out, exist_ok=True)

    focus = tuple(args.focus) if args.focus else FIELD_CENTER
    stadium = Stadium(n_rows=args.rows)
    conditions = Conditions(
        temp_c=args.temp,
        humidity_pct=args.humidity,
        ground_effect=args.ground_effect,
        far_side_reflection=not args.no_reflection,
    )

    base = drill.load_csv(args.drill) if args.drill else drill.FORMS[args.form]()
    forward = drill.apply_facing(base, "front")
    center = drill.apply_facing(base, "center", focus=focus,
                                battery_faces_front=args.battery_front)

    seats, xs, rows = stadium.seat_grid()
    ref = np.array(list(named_seats(stadium).values()))

    print("Simulating %d performers -> %d seats ..." % (len(base), len(seats)))
    f_grid = simulate(forward, seats, stadium, conditions)
    c_grid = simulate(center, seats, stadium, conditions)
    f_ref = simulate(forward, ref, stadium, conditions)
    c_ref = simulate(center, ref, stadium, conditions)

    from dcisim.provenance import model_provenance
    prov = model_provenance()

    text = report.summarize(f_grid, c_grid, f_ref, c_ref, stadium)
    text += "\n" + prov.report() + "\n"
    print()
    print(text)

    if args.sections:
        breakdown = report.section_breakdown(forward, center, seats, stadium, conditions)
        print(breakdown)
        text += "\n" + breakdown + "\n"

    with open(os.path.join(args.out, "summary.txt"), "w") as fh:
        fh.write(text + "\n")

    report.plot_drill(forward, center, os.path.join(args.out, "drill.png"))
    report.plot_stands(f_grid, c_grid, xs, rows, os.path.join(args.out, "stands_dba.png"),
                       "dba", "Audience level (dBA)")
    report.plot_stands(f_grid, c_grid, xs, rows,
                       os.path.join(args.out, "stands_brightness.png"),
                       "brightness", "Audience brightness (HF/LF energy ratio, dB)")
    report.plot_stands(f_grid, c_grid, xs, rows, os.path.join(args.out, "stands_4k.png"),
                       "hf4k", "Audience 4 kHz octave band (dB)")
    report.plot_spectra(f_ref, c_ref, stadium, os.path.join(args.out, "spectra.png"))
    drill.save_csv(forward, os.path.join(args.out, "drill_forward.csv"))
    drill.save_csv(center, os.path.join(args.out, "drill_center.csv"))

    print("Wrote figures and summary to %s/" % args.out)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, FileNotFoundError) as exc:
        # Model and input errors are the user's problem to fix, not a bug to
        # read a traceback about.
        raise SystemExit("error: %s" % exc)
