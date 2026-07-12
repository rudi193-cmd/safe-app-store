#!/usr/bin/env python3
"""
receipt_gate.py — the outward-compatible receipt gate (SAFE installer D2/D4/D8)

"Outwardly-facing compatible" is an EARNED receipt, not a claim (D2). This gate
runs the required checks and only stamps the receipt when ALL of them pass.
Fail-closed: an unimplemented required gate leaves the receipt WITHHELD — you
cannot earn it on unproven checks.

Required gates:
  vault_clean       — the app leaks no user DATA to fixed paths (D8).
                      IMPLEMENTED via tools/vault_leak_lint.py (--strict).
  install_verified  — the app installed once through the seam (D3/D4).  PENDING.
  launch_verified   — the installed app launched.                        PENDING.

Outcomes per app:
  BLOCKED  — a required gate FAILED (e.g. a vault leak). Never earns the receipt
             until fixed. This is what wiring --strict buys: leaks block.
  PENDING  — all implemented gates pass, but a required gate isn't proven yet.
  GRANTED  — every required gate passed; receipt stamped.

Usage:
  tools/receipt_gate.py                 # gate every app
  tools/receipt_gate.py --app utety-chat
  tools/receipt_gate.py --json
  tools/receipt_gate.py --emit receipts/   # write <app>.receipt.json for GRANTED
  tools/receipt_gate.py --strict           # exit 1 if any target app is BLOCKED
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vault_leak_lint as vll  # noqa: E402

DEFAULT_RECEIPTS = Path(__file__).resolve().parent / ".seam-receipts"

# Gate order matters: cheapest / most-blocking first.
REQUIRED_GATES = ["vault_clean", "install_verified", "launch_verified"]


def gate_vault_clean(app_dir: Path | None) -> dict:
    # An installed sovereign artifact has no willow-native source in the repo to
    # lint; it manages its own data per the Sovereignty Test → vacuously clean.
    if app_dir is None or not app_dir.exists():
        return {"status": "pass", "detail": "no in-repo source (installed sovereign artifact)"}
    r = vll.lint_app(app_dir)
    if r["verdict"] == "FAIL":
        n = len(r["leaks"])
        return {"status": "fail",
                "detail": f"{n} data leak(s): " +
                          "; ".join(f"{f['path']} ({f['reason']})" for f in r["leaks"][:4])}
    if r["verdict"] == "WARN":
        return {"status": "pass",
                "detail": f"no data leaks ({len(r['warns'])} non-blocking warn(s))"}
    return {"status": "pass", "detail": "no data leaks"}


def _seam_receipt(app_id: str, receipts: Path) -> dict | None:
    p = receipts / f"{app_id}.seam.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def gate_install_verified(app_id: str, receipts: Path) -> dict:
    r = _seam_receipt(app_id, receipts)
    if r is None:
        return {"status": "pending", "detail": "no seam install receipt"}
    iv = r.get("install_verified", {})
    if iv.get("ok"):
        return {"status": "pass", "detail": f"installed via seam (sha {iv.get('sha256','')[:12]}…)"}
    return {"status": "fail", "detail": "seam install failed"}


def gate_launch_verified(app_id: str, receipts: Path) -> dict:
    r = _seam_receipt(app_id, receipts)
    if r is None:
        return {"status": "pending", "detail": "no seam launch receipt"}
    lv = r.get("launch_verified", {})
    if lv.get("ok"):
        return {"status": "pass", "detail": f"launched (rc {lv.get('rc')})"}
    return {"status": "fail", "detail": f"launch failed: {lv.get('out','')}"}


def evaluate(app_id: str, app_dir: Path | None, receipts: Path) -> dict:
    gates = {
        "vault_clean": gate_vault_clean(app_dir),
        "install_verified": gate_install_verified(app_id, receipts),
        "launch_verified": gate_launch_verified(app_id, receipts),
    }
    if any(gates[g]["status"] == "fail" for g in REQUIRED_GATES):
        outcome = "BLOCKED"
    elif all(gates[g]["status"] == "pass" for g in REQUIRED_GATES):
        outcome = "GRANTED"
    else:
        outcome = "PENDING"

    receipt = None
    if outcome == "GRANTED":
        receipt = {
            "app_id": app_id,
            "outward_compatible": True,
            "stamped_at": datetime.now(timezone.utc).isoformat(),
            "gates": {g: gates[g]["status"] for g in REQUIRED_GATES},
        }
    return {"app": app_id, "outcome": outcome, "gates": gates, "receipt": receipt}


def main() -> int:
    ap = argparse.ArgumentParser(description="Outward-compatible receipt gate")
    ap.add_argument("--path", help="repo root (default: parent of this script's dir)")
    ap.add_argument("--app", help="gate a single app")
    ap.add_argument("--receipts", default=str(DEFAULT_RECEIPTS), help="seam receipts dir")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--emit", metavar="DIR", help="write <app>.receipt.json for GRANTED apps")
    ap.add_argument("--strict", action="store_true", help="exit 1 if any target app is BLOCKED")
    args = ap.parse_args()

    repo = Path(args.path) if args.path else Path(__file__).resolve().parent.parent
    apps_dir = repo / "apps" if (repo / "apps").is_dir() else repo
    receipts = Path(args.receipts)

    if args.app:
        d = apps_dir / args.app
        results = [evaluate(args.app, d if d.exists() else None, receipts)]
    else:
        dirs = [d for d in sorted(apps_dir.iterdir()) if d.is_dir() and not d.name.startswith(".")]
        results = [evaluate(d.name, d, receipts) for d in dirs]

    if args.emit:
        out = Path(args.emit); out.mkdir(parents=True, exist_ok=True)
        for r in results:
            if r["receipt"]:
                (out / f"{r['app']}.receipt.json").write_text(json.dumps(r["receipt"], indent=2))

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        mark = {"BLOCKED": "⛔", "PENDING": "⏳", "GRANTED": "🎖️ "}
        order = {"BLOCKED": 0, "PENDING": 1, "GRANTED": 2}
        for r in sorted(results, key=lambda r: (order[r["outcome"]], r["app"])):
            print(f"{mark[r['outcome']]} {r['outcome']:8} {r['app']}")
            vc = r["gates"]["vault_clean"]
            tag = "PASS" if vc["status"] == "pass" else vc["status"].upper()
            print(f"      vault_clean: {tag} — {vc['detail']}")
            if r["outcome"] == "PENDING":
                pend = [g for g in REQUIRED_GATES if r["gates"][g]["status"] == "pending"]
                print(f"      awaiting: {', '.join(pend)}")
        nb = sum(1 for r in results if r["outcome"] == "BLOCKED")
        npd = sum(1 for r in results if r["outcome"] == "PENDING")
        ng = sum(1 for r in results if r["outcome"] == "GRANTED")
        print(f"\n{len(results)} apps: {nb} BLOCKED · {npd} PENDING · {ng} GRANTED")

    if args.strict and any(r["outcome"] == "BLOCKED" for r in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
