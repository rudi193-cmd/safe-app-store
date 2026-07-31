"""cli.py — The Forge stdio front end.

Thin argparse shell, same shape as njord's: a subcommand parses args, calls
core, prints to stdout. There is no core yet beyond `status` — this exists
so `make run app=the-forge` has something honest to run, not to simulate
functionality that isn't built.

Subcommands:
  status      what's designed (docs/design/the-forge.md, D1-D13) vs what's
              actually implemented. Exits 0.
  plan-check  validate a plan JSON file against D3's schema (plan.py) —
              structural + scope checks only, not the gate (D4) or the
              allowlist (D5), neither of which exist yet.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .plan import PlanError, plan_from_dict, validate_plan

_STATUS = f"""\
The Forge v{__version__} — design-phase scaffold.

Full architecture: docs/design/the-forge.md (D1-D13, two independent reviews
folded in as of 2026-08-01).

Implemented: the seam's plan schema (D3, plan.py) — structural + scope
validation only. No sandboxing (D2), no gate/signing (D4), no MCP connector
or allowlist (D5), no tenancy (D6/D11), no model routing (D7), no
checkpoints (D8/D9), no Nestor wiring (D12). A validated plan isn't an
authorized one yet — D4 and D5 are separate stages plan.py doesn't perform.

Built import-pure from the start (D13): this package does not import
`safe-app-store` internals, and nothing outside it should need to import
back in — there's nothing here yet for the store's seam to gate.
"""


def status(_args: argparse.Namespace) -> int:
    print(_STATUS)
    return 0


def plan_check(args: argparse.Namespace) -> int:
    try:
        payload = json.loads(Path(args.plan_file).read_text())
        plan = plan_from_dict(payload)
        resolved = validate_plan(plan, builder_id=args.builder_id, apps_root=Path(args.apps_root))
    except PlanError as e:
        print(f"plan refused: {e}", file=sys.stderr)
        return 1
    print(f"plan accepted: {len(plan.entries)} entr{'y' if len(plan.entries) == 1 else 'ies'}")
    for path in resolved:
        print(f"  file_write -> {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="the-forge")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="what's designed vs. what's implemented").set_defaults(func=status)

    plan_cmd = sub.add_parser(
        "plan-check",
        help="validate a plan JSON against D3's schema (structural + scope only, not the gate or allowlist)",
    )
    plan_cmd.add_argument("plan_file", help="path to a plan JSON file")
    plan_cmd.add_argument("--builder-id", required=True, help="caller-supplied — never read from the plan itself")
    plan_cmd.add_argument("--apps-root", default="apps", help="default: apps (this store's own apps/ root)")
    plan_cmd.set_defaults(func=plan_check)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
