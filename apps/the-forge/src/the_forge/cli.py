"""cli.py — The Forge stdio front end.

Thin argparse shell, same shape as njord's: a subcommand parses args, calls
core, prints to stdout. There is no core yet beyond `status` — this exists
so `make run app=the-forge` has something honest to run, not to simulate
functionality that isn't built.

Subcommands:
  status    what's designed (docs/design/the-forge.md, D1-D13) vs what's
            actually implemented (nothing, yet). Exits 0.
"""
from __future__ import annotations

import argparse
import sys

from . import __version__

_STATUS = f"""\
The Forge v{__version__} — design-phase scaffold.

Full architecture: docs/design/the-forge.md (D1-D13, two independent reviews
folded in as of 2026-08-01).

Implemented: this package skeleton only. No sandboxing (D2), no seam (D3),
no signing gate (D4), no MCP connector (D5), no tenancy (D6/D11), no model
routing (D7), no checkpoints (D8/D9), no Nestor wiring (D12).

Built import-pure from the start (D13): this package does not import
`safe-app-store` internals, and nothing outside it should need to import
back in — there's nothing here yet for the store's seam to gate.
"""


def status(_args: argparse.Namespace) -> int:
    print(_STATUS)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="the-forge")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="what's designed vs. what's implemented").set_defaults(func=status)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
