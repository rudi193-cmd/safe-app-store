#!/usr/bin/env python3
"""stores/forge_build.py — The Forge, bite 0: the spine.

One build runs end-to-end, single-tenant, through the store's real trust
boundary — no shortcuts, no mocked stage. This is the wiring, not new
policy: every stage below is a real call into code that already exists and
already has its own tests (`the_forge.mount_policy.run_scoped_build`,
`stores/sap_gate.py`'s D4 signing, `stores/seam.py`'s D3/D4/D5 pipeline).
Nothing here re-implements a check any of those already make.

    BuildTask --Kart, scoped to apps/<builder_id>/<app_name>/--> Plan
              --dev_manifest, D4-signed-------------------------> SignedManifest
    (SignedManifest, Plan) --stores/seam.py cross()---------------> written files
                                                                    or SeamError

Store-side by construction (D1/D13): imports FROM `the_forge` (the sandbox
runner, the mount policy, the stub builder) and FROM `stores/sap_gate.py` /
`stores/seam.py` (the gate, the seam) — never the reverse. The Forge does
not get to orchestrate its own crossing; that authority stays here, same as
`stores/seam.py`'s own module docstring says.

Single-tenant, not a bypass of D4/D11: `dev_manifest` below signs a
single, hard-coded `builder_id` ("dev" by default) as both the manifest's
`maker` and the identity `sap_gate.sign_manifest` binds the signature to.
This is the store signing *for* the one dev builder it's provisioning right
now, not a shortcut around the gate — the same real `sign_manifest`/
`verify_manifest` pair that `tests/test_sap_gate.py` and
`tests/test_seam.py` already exercise runs unmodified here. Multi-tenant
identity (D11's GitHub-OAuth-backed session layer) is out of scope for this
bite; nothing here assumes it exists.

Usage:
    python stores/forge_build.py build <app_name> [--builder-id dev] \\
        [--apps-root DIR] [--key-root DIR] [--ledger PATH] \\
        [--no-require-isolation]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

# Same loading convention `stores/seam.py` uses for `the_forge`: sys.path,
# not spec_from_file_location, because `the_forge` is a real package with
# relative imports of its own (`mount_policy.py` does `from .sandbox_runner
# import ...`) — Python's normal import machinery has to resolve that, a
# single-file spec load can't. Loaded straight from apps/the-forge/src; no
# `pip install -e` required to run this script, matching every other
# stores/ tool's "just run it" contract.
_FORGE_SRC = str(_REPO / "apps" / "the-forge" / "src")
if _FORGE_SRC not in sys.path:
    sys.path.insert(0, _FORGE_SRC)

from the_forge.mount_policy import run_scoped_build  # noqa: E402
from the_forge.plan import PlanError  # noqa: E402
from the_forge.sandbox_runner import BuildResult, BuildTask, SandboxError  # noqa: E402
from the_forge.stub_builder import hello_world_command  # noqa: E402
# build_and_cross() itself catches NONE of these: every stage's denial —
# SandboxError/PlanError from the sandbox side, GateError/SeamError from the
# store side — propagates out of the library function uncaught, so a denial can
# never come back disguised as a return value a caller forgets to check. The
# CLI (_cmd_build) is the top-level caller and catches all four to present them
# uniformly as `DENIED: ...`; a library caller that wants per-stage handling
# catches the specific type itself. (These are imported for that CLI catch —
# `SeamError`/`GateError` are aliased further down, off the loaded seam/gate.)

# `stores/seam.py` has no relative imports of its own — spec_from_file_location
# is how it loads `sap_gate.py`, and it's how we load `seam.py` itself here,
# for the same reason `tests/test_seam.py` does: this is a script, not an
# installed package, and this repo's convention (per `stores/seam.py`'s own
# preamble) is to load store-side tools this way rather than requiring a
# package install just to import one function. `seam.py`'s own module-level
# code already does the sys.path insert above (redundant, harmless) and its
# own spec_from_file_location load of sap_gate.py — reusing it here means
# there is exactly one place that loads sap_gate.py, not two copies that
# could drift.
_spec = importlib.util.spec_from_file_location("seam", _REPO / "stores" / "seam.py")
seam = importlib.util.module_from_spec(_spec)
sys.modules["seam"] = seam
_spec.loader.exec_module(seam)

sap_gate = seam.sap_gate
SeamError = seam.SeamError
GateError = sap_gate.GateError


def dev_manifest(builder_id: str, app_name: str) -> dict:
    """The single-tenant manifest bite 0 signs and crosses.

    `store_scope` is set honestly to this builder's own SAPS1 lane
    (`saps1/builder-<builder_id>`, matching D6's per-builder collection
    namespace naming) even though bite 0's plan never carries an `McpCall`
    entry — nothing exercises `store_scope` yet, because the hello-world
    stub only emits `FileWrite` entries. Those are bounded by `plan.py`'s
    path-containment check (`apps/<builder_id>/<app_name>/`), not by
    `store_scope` — `store_scope` only becomes load-bearing once a plan can
    carry an `McpCall` for a registered MCP server (D5), which is a later
    bite. `permissions` is empty for the same reason: nothing in bite 0's
    plan asks for a permission beyond "write files inside my own app
    directory," which the seam already enforces unconditionally.
    """
    return {
        "app_id": app_name,
        "permissions": [],
        "store_scope": [f"saps1/builder-{builder_id}"],
        "maker": builder_id,
    }


def build_and_cross(
    *,
    builder_id: str,
    app_name: str,
    command: str,
    apps_root: Path,
    keystore: "sap_gate.KeyStore",
    ledger: "sap_gate.SigningLedger",
    require_isolation: bool = True,
    mcp_registry=None,
) -> dict:
    """The whole spine, one call: sandbox -> plan -> D4 sign -> D3/D4/D5
    seam. Raises whatever the stage that refuses raises
    (`SandboxError`/`PlanError` from the sandbox side, `GateError`/
    `SeamError` from the store side) — a denial must never come back
    disguised as a return value a caller could forget to check.
    """
    task = BuildTask(builder_id=builder_id, app_name=app_name, command=command)

    # Kart runs the build, scoped to apps/<builder_id>/<app_name>/ (D6) —
    # the build never touches the real filesystem outside that one bind.
    result: BuildResult = run_scoped_build(task, apps_root, require_isolation=require_isolation)

    # D4: the store signs a manifest binding this build's identity — real
    # signing, real ledger append, not a bypass (see module docstring).
    manifest = dev_manifest(builder_id, app_name)
    signed = sap_gate.sign_manifest(manifest, builder_id=builder_id, keystore=keystore, ledger=ledger)

    # D3(scope) -> D3(scan) -> D5(allowlist) -> apply, all inside cross().
    report = seam.cross(
        signed_manifest=signed,
        plan=result.plan,
        keystore=keystore,
        ledger=ledger,
        apps_root=apps_root,
        mcp_registry=mcp_registry,
    )

    # Honest isolation provenance rides along with the report — D10's "a
    # seam-side record that doesn't say whether the build was actually
    # contained is recording half a fact," applied to this driver's own
    # return value the same way `BuildResult.isolated`/`.warnings` already
    # apply it to the sandbox-runner layer.
    return {**report, "isolated": result.isolated, "warnings": list(result.warnings)}


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cmd_build(args: argparse.Namespace) -> int:
    apps_root = Path(args.apps_root)
    keystore = sap_gate.FilesystemKeyStore(Path(args.key_root))
    ledger = sap_gate.SigningLedger(Path(args.ledger))
    command = hello_world_command(args.app_name)

    try:
        report = build_and_cross(
            builder_id=args.builder_id,
            app_name=args.app_name,
            command=command,
            apps_root=apps_root,
            keystore=keystore,
            ledger=ledger,
            require_isolation=not args.no_require_isolation,
        )
    except (SandboxError, PlanError, GateError, SeamError) as e:
        # Every stage's denial, one uniform line — ordered the way a build
        # passes through them: sandbox side first (SandboxError: no isolation,
        # or the build failed/timed out; PlanError: a malformed or out-of-scope
        # plan) then store side (GateError: signature/gate; SeamError: refused
        # at the seam). Before this, SandboxError/PlanError fell through as a
        # raw traceback while GateError/SeamError printed cleanly — bite 0's own
        # recorded follow-up, now closed.
        print(f"DENIED: {e}", file=sys.stderr)
        return 1

    print(json.dumps(report, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="forge_build.py")
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser(
        "build",
        help="bite 0's spine: run a hello-world stub build through Kart, D4 signing, and the D3/D5 seam",
    )
    b.add_argument("app_name")
    b.add_argument("--builder-id", default="dev", help="single-tenant dev identity (default: dev)")
    # Subparser-level, not parent-level — same argparse ordering reasoning
    # stores/seam.py's own build_parser() already documents: "cross <files>
    # --apps-root X" is the natural order to type this.
    b.add_argument("--apps-root", default=str(_REPO / "apps"))
    b.add_argument("--key-root", default=str(sap_gate.DEFAULT_KEY_ROOT))
    b.add_argument("--ledger", default=str(sap_gate.DEFAULT_LEDGER_PATH))
    b.add_argument(
        "--no-require-isolation",
        action="store_true",
        help="dev-only: allow kartikeya's plain (unsandboxed) fallback when bwrap is unavailable; "
             "the report's isolated field will honestly say False",
    )
    b.set_defaults(func=_cmd_build)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
