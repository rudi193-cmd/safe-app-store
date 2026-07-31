#!/usr/bin/env python3
"""stores/seam.py — the seam (D3): where a build's plan crosses from
sandbox to store.

Ties together what's built as of 2026-08-01 into the actual pipeline the
design's own diagram describes:

    SANDBOX (kart, per-build) --plan--> SEAM (store-side): validate plan vs
    gate (D4) + this builder's scope --> apply, or deny + report why.

Store-side by construction (D1/D13): imports FROM `the_forge` (the plan
schema, the scan) and FROM `stores/sap_gate.py` (the manifest gate) — never
the reverse. The Forge, even once promoted, does not get to orchestrate its
own crossing; that authority stays here.

Pipeline, in order, each stage fail-closed:
  1. D4 — verify the signed manifest. `builder_id` for every later stage
     comes from THIS verified identity, never from the plan itself — same
     reasoning as D11 and `plan.py`'s own docstring: a plan can't assert
     its own identity, and now there's a legitimate, cryptographically
     checked source for one.
  2. D3 (scope) — `validate_plan` against that verified `builder_id`.
  3. D3 (content) — `scan_plan` over every `.py` FileWrite.
  4. Apply — FileWrite entries actually get written. McpCall entries are
     explicitly DEFERRED, not executed and not silently dropped: D5 (the
     per-server allowlist) doesn't exist yet, and nothing crosses without
     one. This is the real, current boundary between what D3/D4 cover and
     what D5 still has to.

Usage:
    python stores/seam.py cross <signed-manifest.json> <plan.json> \\
        [--apps-root DIR] [--key-root DIR] [--ledger PATH]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

# the_forge is a real package with relative imports (scan.py does
# `from .plan import FileWrite`) — sys.path, not spec_from_file_location,
# so Python's normal import machinery resolves that correctly. Loaded
# straight from apps/the-forge/src; no `pip install -e` required to run
# this script, matching every other stores/ tool's "just run it" contract.
_FORGE_SRC = str(_REPO / "apps" / "the-forge" / "src")
if _FORGE_SRC not in sys.path:
    sys.path.insert(0, _FORGE_SRC)

from the_forge.plan import FileWrite, McpCall, Plan, PlanError, plan_from_dict, validate_plan  # noqa: E402
from the_forge.scan import scan_plan  # noqa: E402

# sap_gate.py has no relative imports of its own — same
# spec_from_file_location pattern promote_check.py already uses to load
# tools/vault_leak_lint.py.
_spec = importlib.util.spec_from_file_location("sap_gate", _REPO / "stores" / "sap_gate.py")
sap_gate = importlib.util.module_from_spec(_spec)
sys.modules["sap_gate"] = sap_gate
_spec.loader.exec_module(sap_gate)


class SeamError(Exception):
    """Refused at the seam — the gate, the scope check, or the content
    scan. Nothing crosses when this is raised."""


def cross(*, signed_manifest: "sap_gate.SignedManifest", plan: Plan,
          keystore: "sap_gate.KeyStore", ledger: "sap_gate.SigningLedger",
          apps_root: Path) -> dict:
    """The whole pipeline, fail-closed at every stage.

    Returns a report dict on success:
        {"builder_id": ..., "written": [...], "deferred_mcp_calls": [...]}

    `deferred_mcp_calls` is never empty-vs-absent by accident — it's always
    a list, present or empty, so a caller can tell "no mcp_call entries in
    this plan" apart from "entries existed but got silently forgotten,"
    which is exactly the distinction a seam should never blur.
    """
    try:
        sap_gate.verify_manifest(signed_manifest, keystore=keystore, ledger=ledger)
    except sap_gate.GateError as e:
        raise SeamError(f"gate denied: {e}") from e

    builder_id = signed_manifest.builder_id

    try:
        resolved = validate_plan(plan, builder_id=builder_id, apps_root=apps_root)
    except PlanError as e:
        raise SeamError(f"plan out of scope: {e}") from e

    findings = scan_plan(plan.entries)
    if findings:
        detail = "; ".join(f"{path}:{f.line} {f.rule}" for path, fs in findings.items() for f in fs)
        raise SeamError(f"pre-crossing scan refused: {detail}")

    written: list[str] = []
    file_writes = [e for e in plan.entries if isinstance(e, FileWrite)]
    for entry, dest in zip(file_writes, resolved):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(entry.content)
        if entry.executable:
            dest.chmod(0o755)
        written.append(str(dest))

    deferred_mcp_calls = [
        {"server": e.server, "tool": e.tool} for e in plan.entries if isinstance(e, McpCall)
    ]

    return {"builder_id": builder_id, "written": written, "deferred_mcp_calls": deferred_mcp_calls}


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cmd_cross(args: argparse.Namespace) -> int:
    ks = sap_gate.FilesystemKeyStore(Path(args.key_root))
    ledger = sap_gate.SigningLedger(Path(args.ledger))
    signed = sap_gate.SignedManifest.from_dict(json.loads(Path(args.signed_manifest).read_text()))
    try:
        plan = plan_from_dict(json.loads(Path(args.plan_file).read_text()))
    except PlanError as e:
        print(f"plan refused: {e}", file=sys.stderr)
        return 1

    try:
        report = cross(signed_manifest=signed, plan=plan, keystore=ks, ledger=ledger,
                        apps_root=Path(args.apps_root))
    except SeamError as e:
        print(f"DENIED: {e}", file=sys.stderr)
        return 1

    print(json.dumps(report, indent=2))
    n = len(report["deferred_mcp_calls"])
    if n:
        print(f"note: {n} mcp_call entr{'y' if n == 1 else 'ies'} deferred — "
              f"D5's allowlist doesn't exist yet, nothing was executed", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="seam.py")
    sub = p.add_subparsers(dest="command", required=True)

    cr = sub.add_parser("cross", help="run a signed manifest + plan through the full D3/D4 pipeline")
    cr.add_argument("signed_manifest")
    cr.add_argument("plan_file")
    # subparser-level, not parent-level: argparse won't accept a parent
    # optional AFTER the subcommand name, and "cross <files> --apps-root X"
    # is the natural order to type this, not "--apps-root X cross <files>".
    cr.add_argument("--apps-root", default=str(_REPO / "apps"))
    cr.add_argument("--key-root", default=str(sap_gate.DEFAULT_KEY_ROOT))
    cr.add_argument("--ledger", default=str(sap_gate.DEFAULT_LEDGER_PATH))
    cr.set_defaults(func=_cmd_cross)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
