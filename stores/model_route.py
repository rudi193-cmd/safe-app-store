#!/usr/bin/env python3
"""stores/model_route.py — The Forge's D7-A gate: declared-not-ambient model
routing (docs/design/the-forge.md, D7).

D7's rule, made mechanical: a model request runs LOCAL first (the vLLM/loopback
default, no network), and cloud fallback is a **per-build declared permission**
— it "shows up in the manifest like any other permission, and only then gets a
network-enabled Kart invocation." No silent egress: a build that never declares
cloud fallback never gets network.

Two reuses, one policy:
  * **Detection** is willow-mcp's fail-closed loopback check, vendored in
    `stores/model_egress.py` (`is_local_host`): only an all-loopback host is
    LOCAL; an unparseable/unresolvable/mixed host reads as OFF the machine and
    needs a permission.
  * **Authorization** is NOT a separate signed envelope (willow-mcp's
    `egress_authorization` signs per-task net authority for its queue). The
    Forge's cloud-fallback permission rides inside the build's **D4-signed
    manifest** — the sap-gate signature already binds it to the maker, so the
    "declared, signed, tamper-evident, bound-to-the-maker" property comes from
    D4 for free. This module is the POLICY over that permission, exactly as
    `stores/seam.py`'s D5 allowlist is the policy over a manifest the D4 gate
    already verified. **It does not check signatures** — the caller passes a
    manifest whose signature the D4 gate verified upstream, same trust boundary
    seam's own stages operate on.

Store-side (D1): `apps/the-forge/` never imports this; a build does not get to
decide its own egress. The actual vLLM/LiteLLM call is out of scope (D7's model
is stubbed everywhere this session — the checkpoint `Decision`s are stubs, the
build is a stub); this is the GATE that call will consult, built and tested now,
live once the model exists — the same "machinery real, D7 input stubbed" posture
bites 0-1 took.

Usage:
    from model_route import route
    d = route(verified_manifest)              # host from OLLAMA_HOST or default
    if d.denial: refuse(d.denial)             # declared-not-ambient refusal
    else: run(..., allow_net=d.allow_net)     # Kart gets net ONLY for permitted cloud
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

_me_spec = importlib.util.spec_from_file_location("model_egress", _REPO / "stores" / "model_egress.py")
model_egress = importlib.util.module_from_spec(_me_spec)
sys.modules["model_egress"] = model_egress
_me_spec.loader.exec_module(model_egress)

# The manifest permission that declares "this build may fall back to a cloud
# model." One line in the D4-signed manifest, like any other permission.
CLOUD_FALLBACK_PERMISSION = "cloud_llm_fallback"


@dataclass(frozen=True)
class RouteDecision:
    """Where a model request goes and whether the run may touch the network.

    `target`: `"local"` (loopback, no net), `"cloud"` (off-machine, permitted),
    or `None` (refused — an off-machine host with no declared permission).
    `allow_net`: True ONLY for a permitted `cloud` route — the value to pass to
    Kart's `allow_net` directive (off by default, D2). Never True for `local`
    (loopback needs no network namespace) or a refusal.
    `denial`: `None` when permitted, else an error dict (mirroring
    `model_egress.denial`'s shape) naming the missing permission and the host —
    a gate that only says "no" trains people to route around it.
    `host`: the model host this decision was made against (resolved from the
    argument or the environment), for the record.
    """

    target: str | None
    allow_net: bool
    denial: dict | None
    host: str


def _ensure_scheme(host: str) -> str:
    """`is_local_host`/`urlparse` need a scheme to extract a hostname — a bare
    `host:port` or `localhost` (the STANDARD scheme-less `OLLAMA_HOST` form)
    otherwise parses with the host as the URL *scheme*, yielding `hostname=None`
    and reading as off-machine. That over-refusal is worse than cosmetic: the
    only way to unblock a purely-local ollama pointed at by a scheme-less env
    var would be to declare `cloud_llm_fallback` and take `allow_net=True` — an
    over-grant. So normalize here (the Forge's own adaptation; the vendored
    detector stays byte-identical) by prepending `http://` when no scheme is
    present. A value that already has a scheme is left alone."""
    h = (host or "").strip()
    if "://" not in h:
        h = "http://" + h
    return h


def permits(manifest: dict) -> bool:
    """True iff `manifest` declares the cloud-fallback permission. Reads the
    permission list only — the manifest's SIGNATURE is the D4 gate's job, not
    this one (see module docstring)."""
    perms = manifest.get("permissions") if isinstance(manifest, dict) else None
    return isinstance(perms, list) and CLOUD_FALLBACK_PERMISSION in perms


def route(manifest: dict, *, model_host: str | None = None) -> RouteDecision:
    """Decide where a model request for this build goes. `manifest` must be a
    build manifest whose signature the D4 gate has already verified (this module
    reads its permissions, it does not verify them — see module docstring).
    `model_host` defaults to `OLLAMA_HOST`/the loopback default.

    Local (all-loopback host) → `local`, no net, always allowed. Off-machine →
    `cloud` with net IF the manifest declares `CLOUD_FALLBACK_PERMISSION`, else a
    refusal with no net (declared, not ambient).

    Known limit (inherent to gate-time detection, carried from the vendored
    detector's own upstream note): resolution happens HERE, the connection
    happens later in the eventual client, so a hostname that resolves to
    loopback now and to a public address at connect time (DNS rebinding /
    TOCTOU) reads as `local` with no permission. Closing that needs a
    socket-time check in the client that actually makes the model call; this
    layer cannot."""
    host = _ensure_scheme(model_host if model_host is not None else model_egress.model_host())

    if model_egress.is_local_host(host):
        return RouteDecision(target="local", allow_net=False, denial=None, host=host)

    if permits(manifest):
        return RouteDecision(target="cloud", allow_net=True, denial=None, host=host)

    return RouteDecision(
        target=None,
        allow_net=False,
        denial={"error": (
            f"cloud_llm_denied: this build would send a model request to {host}, "
            f"which is not on this machine (loopback). D7 requires that cloud "
            f"fallback be declared as a {CLOUD_FALLBACK_PERMISSION!r} permission "
            f"in the build's manifest — where the D4 signature binds it to the "
            f"maker — before any network-enabled run. To keep inference local "
            f"instead, point the model host at loopback (a local vLLM) and no "
            f"permission is needed."
        )},
        host=host,
    )


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cmd_route(args: argparse.Namespace) -> int:
    # DEV INSPECTOR ONLY: this reads a manifest file WITHOUT verifying its D4
    # signature — it exists to eyeball what route() would decide, not to gate a
    # live run. The live caller (the eventual model-invocation path) must pass a
    # manifest that seam/sap_gate already verified; route() is policy over a
    # verified permission, not the signature check (see module docstring).
    manifest = json.loads(Path(args.manifest).read_text()) if args.manifest else {"permissions": []}
    d = route(manifest, model_host=args.host)
    print(json.dumps(
        {"target": d.target, "allow_net": d.allow_net, "host": d.host, "denial": d.denial}, indent=2
    ))
    return 0 if d.denial is None else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="model_route.py")
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("route", help="decide local vs cloud for a build manifest + model host")
    r.add_argument("--manifest", default="", help="path to a (verified) manifest JSON; default: no permissions")
    r.add_argument("--host", default=None, help="model host URL; default: OLLAMA_HOST or the loopback default")
    r.set_defaults(func=_cmd_route)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
