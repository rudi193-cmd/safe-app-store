"""cli.py — The Forge stdio front end.

Thin argparse shell, same shape as njord's: a subcommand parses args, calls
core, prints to stdout.

Subcommands:
  status      what's designed (docs/design/the-forge.md, D1-D13) vs what's
              actually implemented. Exits 0.
  plan-check  validate a plan JSON against D3's schema (plan.py) — scope,
              then the pre-crossing content scan (scan.py) over every .py
              FileWrite entry. Deliberately does NOT call the gate (D4) or
              the allowlist (D5): both are store-side authority
              (`stores/sap_gate.py`, `stores/seam.py`), and this package
              stays import-pure (D13) — it can't reach into
              `safe-app-store` internals even to check itself. The real,
              full pipeline is `stores/seam.py cross`, not this command;
              `plan-check` is the in-package subset a builder can run
              standalone, before anything is signed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .plan import PlanError, plan_from_dict, validate_plan
from .scan import scan_plan

_STATUS = f"""\
The Forge v{__version__} — design-phase scaffold.

Full architecture: docs/design/the-forge.md (D1-D13, two independent reviews
folded in as of 2026-08-01).

Implemented and wired together (2026-08-01): D3's plan schema (plan.py) and
pre-crossing content scan (scan.py), D4's signing gate (stores/sap_gate.py,
store-side per D1), D5's MCP allowlist (mcp_registry.py) — all four run as
one real pipeline in `stores/seam.py cross`: verify the signed manifest,
validate the plan's scope against that verified identity, scan its content,
check every mcp_call against a supplied registry, then apply.

Also implemented: D2's sandbox invocation (sandbox_runner.py) — a build
command runs inside kartikeya's bwrap sandbox and its stdout is parsed into
a plan for that pipeline to consume. Kart is trusted for isolation, never
for policy; the runner decides nothing and writes nothing. On a host with
no bubblewrap it refuses by default, and an explicit dev opt-out is
reported as unisolated rather than passed off as sandboxed.

Not yet done: real MCP client/stdio execution (an allowed call is still not
executed, only permitted), D6's per-build mount boundary (Kart's binds come
from its own mount policy, not from a build's working directory), tenancy/
auth (D6/D11), model routing and code generation (D7 — nothing yet produces
a build command), checkpoints (D8/D9), Nestor wiring (D12).

This CLI (`the-forge`) only ever runs the in-package subset — `plan-check`
covers D3 alone. The gate and the allowlist are store-side authority by
design (D1/D13); this package doesn't import them, and can't check itself
against rules it doesn't hold. Run `stores/seam.py cross` for the real
pipeline.

Built import-pure from the start (D13): this package does not import
`safe-app-store` internals, and nothing outside it should need to import
back in except `stores/seam.py`, which does exactly that — the host
importing the builder, never the reverse.
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

    scan_results = scan_plan(plan.entries)
    if scan_results:
        print("plan refused: pre-crossing scan found dangerous patterns", file=sys.stderr)
        for path, findings in scan_results.items():
            for f in findings:
                print(f"  {path}:{f.line}: {f.rule} — {f.detail}", file=sys.stderr)
        return 1

    print(f"plan accepted: {len(plan.entries)} entr{'y' if len(plan.entries) == 1 else 'ies'}, scan clean")
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
