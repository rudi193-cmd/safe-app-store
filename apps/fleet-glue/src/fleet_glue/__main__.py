"""CLI for fleet-glue.

    python -m fleet_glue [--lab DIR] [--seed-jeles-demo] [--probe]

Also invoked by the ``fleet-glue`` console script (pyproject) and by
``apps/fleet-glue/app.py`` (the ``make run app=fleet-glue`` entry).
"""
from __future__ import annotations

import argparse
import json

from . import configure_lab, install, doctor_summary, log_gap, triage_summary
from .triage import render as triage_render


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="fleet-glue", description="fleet-glue playground entry")
    p.add_argument("--lab", default="./lab", help="lab root directory (default: ./lab)")
    p.add_argument("--seed-jeles-demo", action="store_true",
                   help="also seed the four demo nuggets (three human, one asserted decoy)")
    p.add_argument("--probe", action="store_true",
                   help="run a small end-to-end probe after standup")
    args = p.parse_args(argv)

    print(f"configure_lab({args.lab!r})")
    print(json.dumps(configure_lab(args.lab), indent=2, default=str))

    print(f"\ninstall(seed_jeles_demo={args.seed_jeles_demo})")
    r = install(seed_jeles_demo=args.seed_jeles_demo)
    print(json.dumps(
        {"wire": r["wire"], "seal_key": r["seal_key"],
         "seeded": len(r["jeles_seed"]) if isinstance(r.get("jeles_seed"), list) else r.get("jeles_seed")},
        indent=2, default=str,
    ))

    print("\ndoctor_summary()")
    print(json.dumps(doctor_summary(), indent=2, default=str))

    if args.probe:
        print("\n--- probe ---")
        g = log_gap("What is the current freeze window?", topic="ops")
        print("log_gap:", json.dumps({k: g[k] for k in ("willow_gap_id", "jeles_gap_id")}))
        tri = triage_summary()
        print("\ntriage:\n" + triage_render(tri))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
