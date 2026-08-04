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
  4. D5 (allowlist) — every McpCall entry checked against a caller-supplied
     `McpRegistry`; ANY entry not on its server's allowlist denies the
     WHOLE plan (same all-or-nothing posture as the scope check and the
     scan — a seam that let some entries cross while silently dropping
     others would be exactly the ambiguity this design has avoided
     everywhere else). A plan with McpCall entries and no registry
     supplied is denied outright — nothing is allowed by default.
  5. Apply — FileWrite entries actually get written. McpCall entries that
     passed the allowlist are still DEFERRED, not executed: real MCP
     client/stdio execution is later work (the "thin connector" D5 also
     names), and being on an allowlist is permission to be called, not a
     substitute for actually calling it. Reported as
     `allowed_mcp_calls`, distinct from a denial — allowed-but-not-yet-
     executed is not the same fact as refused.

Usage:
    python stores/seam.py cross <signed-manifest.json> <plan.json> \\
        [--apps-root DIR] [--key-root DIR] [--ledger PATH] [--registry FILE]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
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
from the_forge.mcp_registry import McpRegistry  # noqa: E402

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
          apps_root: Path, mcp_registry: McpRegistry | None = None) -> dict:
    """The whole pipeline, fail-closed at every stage.

    Returns a report dict on success:
        {"builder_id": ..., "written": [...], "allowed_mcp_calls": [...]}

    `allowed_mcp_calls` is never empty-vs-absent by accident — it's always a
    list, present or empty, so a caller can tell "no mcp_call entries in
    this plan" apart from "entries existed but got silently forgotten,"
    which is exactly the distinction a seam should never blur. Every entry
    in it passed D5's allowlist; none of them were executed — see the
    module docstring's step 5.
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

    mcp_calls = [e for e in plan.entries if isinstance(e, McpCall)]
    if mcp_calls:
        if mcp_registry is None:
            raise SeamError(
                f"plan has {len(mcp_calls)} mcp_call entr"
                f"{'y' if len(mcp_calls) == 1 else 'ies'} but no registry was supplied "
                f"— nothing is allowed by default"
            )
        for call in mcp_calls:
            if not mcp_registry.is_allowed(call.server, call.tool):
                raise SeamError(f"mcp_call denied: {mcp_registry.deny_reason(call.server, call.tool)}")

    allow_root = (apps_root / builder_id / plan.app_name).resolve()

    written: list[str] = []
    file_writes = [e for e in plan.entries if isinstance(e, FileWrite)]
    for entry, dest in zip(file_writes, resolved):
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            # validate_plan() resolved `dest` before ANY of this ran — a
            # symlink planted at an intermediate directory since then would
            # otherwise let the write land somewhere the containment check
            # never actually saw. Re-resolve now that the directory really
            # exists (resolve() only chases real symlinks on disk; at
            # validate-plan time most of this path didn't exist yet, so
            # there was nothing to chase). This narrows the race; it does
            # not close it completely — a symlink planted in the
            # microseconds between this check and the O_NOFOLLOW open below
            # is not caught by anything short of platform-specific syscalls
            # (openat2/RESOLVE_NO_SYMLINKS) this module doesn't use. Said
            # plainly rather than implied solved.
            real_parent = dest.parent.resolve(strict=True)
            if real_parent != allow_root and not real_parent.is_relative_to(allow_root):
                raise SeamError(
                    f"seam refused: {dest} — an intermediate directory was replaced "
                    f"with a symlink after validation"
                )
            fd = os.open(str(dest), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
            with os.fdopen(fd, "w") as f:  # closes fd on any exit path, including an exception
                f.write(entry.content)
        except (OSError, ValueError) as e:
            raise SeamError(f"seam refused: cannot write {dest}: {e}") from e
        if entry.executable:
            os.chmod(dest, 0o755)
        written.append(str(dest))

    allowed_mcp_calls = [{"server": e.server, "tool": e.tool} for e in mcp_calls]

    return {"builder_id": builder_id, "written": written, "allowed_mcp_calls": allowed_mcp_calls}


# ── CLI ──────────────────────────────────────────────────────────────────────

def _load_registry(path: str | None) -> McpRegistry | None:
    """Registry file format:
        {"nestor": {"launch_command": ["nestor", "serve"],
                     "allowed_tools": ["nestor_ask", ...]}}
    No file supplied -> None, meaning a plan with any mcp_call entries is
    denied outright (D5's default-deny, all the way to the CLI)."""
    if path is None:
        return None
    registry = McpRegistry()
    for name, spec in json.loads(Path(path).read_text()).items():
        registry.register(name, launch_command=spec["launch_command"], allowed_tools=spec["allowed_tools"])
    return registry


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
        registry = _load_registry(args.registry)
    except Exception as e:  # RegistryError or a malformed registry file — refuse, don't guess
        print(f"registry file refused: {e}", file=sys.stderr)
        return 1

    try:
        report = cross(signed_manifest=signed, plan=plan, keystore=ks, ledger=ledger,
                        apps_root=Path(args.apps_root), mcp_registry=registry)
    except SeamError as e:
        print(f"DENIED: {e}", file=sys.stderr)
        return 1

    print(json.dumps(report, indent=2))
    n = len(report["allowed_mcp_calls"])
    if n:
        print(f"note: {n} mcp_call entr{'y' if n == 1 else 'ies'} allowed but not executed — "
              f"real MCP client/stdio execution is later work", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="seam.py")
    sub = p.add_subparsers(dest="command", required=True)

    cr = sub.add_parser("cross", help="run a signed manifest + plan through the full D3/D4/D5 pipeline")
    cr.add_argument("signed_manifest")
    cr.add_argument("plan_file")
    # subparser-level, not parent-level: argparse won't accept a parent
    # optional AFTER the subcommand name, and "cross <files> --apps-root X"
    # is the natural order to type this, not "--apps-root X cross <files>".
    cr.add_argument("--apps-root", default=str(_REPO / "apps"))
    cr.add_argument("--key-root", default=str(sap_gate.DEFAULT_KEY_ROOT))
    cr.add_argument("--ledger", default=str(sap_gate.DEFAULT_LEDGER_PATH))
    cr.add_argument("--registry", default=None, help="JSON file of server allowlists (see _load_registry); omit to deny all mcp_call entries")
    cr.set_defaults(func=_cmd_cross)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
