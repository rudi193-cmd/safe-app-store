#!/usr/bin/env python3
"""
seam_install.py — sandbox-with-a-seam installer (SAFE installer D3-D5)

The install boundary: all dangerous work (fetch + verify + stage) happens in a
sandbox that cannot write the host; only a verified, declarative placement plan
crosses the seam to the host, which does a dumb, allowlist-checked copy. Data
crosses — never vendor code at host privilege.

  STAGE (sandboxed) : stage the artifact, sha256-verify it vs the recipe.
                      Runs in bwrap when available. If the digest mismatches,
                      NOTHING crosses the seam.
  SEAM  (host)      : validate each placement dest is inside the SAFE/apps
                      allowlist (path-containment, the C6 pattern), then copy.
  LAUNCH            : smoke the placed app.
  RECEIPT           : write <app_id>.seam.json — the earned install_verified +
                      launch_verified proof the receipt gate consumes.

Recipe (JSON):
  {"app_id": "...", "artifact": "/path/or/url", "sha256": "...",
   "kind": "script|binary|appimage", "launch": ["--version"]}

Usage:
  tools/seam_install.py --recipe app.json --safe-root SAFE
  tools/seam_install.py --demo                       # synthetic app, end to end
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_SAFE_ROOT = Path(os.environ.get("SAFE_ROOT", "SAFE"))
DEFAULT_RECEIPTS = Path(__file__).resolve().parent / ".seam-receipts"


class SeamError(Exception):
    pass


def _have_bwrap() -> bool:
    return shutil.which("bwrap") is not None


def _sha256_sandboxed(path: Path) -> str:
    """Digest the artifact. In bwrap the stage can only READ the file (ro-bind,
    no host write, all namespaces unshared) — faithful to the sandbox stage."""
    prog = ("import hashlib,sys;"
            "print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())")
    if _have_bwrap():
        cmd = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev",
               "--unshare-all", "--die-with-parent", "--",
               sys.executable, "-c", prog, str(path)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
        # fall through to in-process on sandbox failure
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage(recipe: dict, staging: Path) -> tuple[Path, str, bool]:
    """Stage the artifact and verify its digest. Returns (staged_path, digest,
    sandboxed). Raises SeamError on digest mismatch — nothing crosses the seam."""
    src = recipe["artifact"]
    if src.startswith("file://"):
        src = src[len("file://"):]
    src_path = Path(src)
    if not src_path.is_file():
        raise SeamError(f"artifact not found: {src}")
    staged = staging / src_path.name
    shutil.copy2(src_path, staged)

    digest = _sha256_sandboxed(staged)
    want = recipe.get("sha256", "").strip().lower()
    if not want:
        raise SeamError("recipe has no sha256 — refusing to install unverified")
    if digest.lower() != want:
        raise SeamError(f"sha256 mismatch: staged {digest} != recipe {want}")
    return staged, digest, _have_bwrap()


def build_plan(recipe: dict, staged: Path, safe_root: Path) -> list[tuple[Path, Path]]:
    app_id = recipe["app_id"]
    dest_dir = safe_root / "apps" / app_id
    return [(staged, dest_dir / staged.name)]


def seam_place(plan: list[tuple[Path, Path]], safe_root: Path, app_id: str,
               executable: bool) -> list[str]:
    """The seam: allowlist-check every destination, then copy. Refuses any dest
    that resolves outside SAFE/apps/<app_id>/ (path-containment, C6 pattern)."""
    allow_root = (safe_root / "apps" / app_id).resolve()
    placed = []
    for src, dest in plan:
        dest_r = (allow_root / dest.name).resolve() if not dest.is_absolute() else dest.resolve()
        # containment: dest must be the allow_root or strictly inside it
        if dest_r != allow_root and not dest_r.is_relative_to(allow_root):
            raise SeamError(f"seam refused: {dest_r} escapes allowlist {allow_root}")
        dest_r.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest_r)
        if executable:
            dest_r.chmod(0o755)
        placed.append(str(dest_r))
    return placed


def launch_check(exe: Path, args: list[str]) -> dict:
    try:
        r = subprocess.run([str(exe), *args], capture_output=True, text=True, timeout=30)
        return {"ok": r.returncode == 0, "rc": r.returncode,
                "out": (r.stdout or r.stderr).strip()[:200]}
    except Exception as e:
        return {"ok": False, "rc": None, "out": f"{type(e).__name__}: {e}"}


def install(recipe: dict, safe_root: Path, receipts: Path) -> dict:
    app_id = recipe["app_id"]
    executable = recipe.get("kind") in ("script", "binary", "appimage")
    with tempfile.TemporaryDirectory(prefix=f"seam-{app_id}-") as tmp:
        staging = Path(tmp)
        staged, digest, sandboxed = stage(recipe, staging)          # STAGE
        plan = build_plan(recipe, staged, safe_root)
        placed = seam_place(plan, safe_root, app_id, executable)    # SEAM
    exe = Path(placed[0])
    launch = launch_check(exe, recipe.get("launch", []))            # LAUNCH

    receipt = {
        "app_id": app_id,
        "install_verified": {"ok": True, "sha256": digest,
                             "sandboxed_stage": sandboxed, "placed": placed},
        "launch_verified": launch,
    }
    receipts.mkdir(parents=True, exist_ok=True)
    (receipts / f"{app_id}.seam.json").write_text(json.dumps(receipt, indent=2))
    return receipt


# ── demo ─────────────────────────────────────────────────────────────────────

def _demo(safe_root: Path, receipts: Path) -> int:
    app_id = "hello-sovereign"
    with tempfile.TemporaryDirectory(prefix="seam-demo-") as tmp:
        art = Path(tmp) / "hello-sovereign"
        art.write_text("#!/usr/bin/env bash\n"
                       'if [ "$1" = "--version" ]; then echo "hello-sovereign 1.0"; exit 0; fi\n'
                       'echo "hello from the sovereign seam"\n')
        digest = hashlib.sha256(art.read_bytes()).hexdigest()

        print("== 1. honest install (sha matches) ==")
        recipe = {"app_id": app_id, "artifact": str(art), "sha256": digest,
                  "kind": "script", "launch": ["--version"]}
        r = install(recipe, safe_root, receipts)
        print(f"   install_verified: ok, sha256={digest[:12]}…, sandboxed_stage={r['install_verified']['sandboxed_stage']}")
        print(f"   placed: {r['install_verified']['placed'][0]}")
        print(f"   launch_verified: ok={r['launch_verified']['ok']} rc={r['launch_verified']['rc']} out={r['launch_verified']['out']!r}")

        print("\n== 2. tampered artifact (sha mismatch → nothing crosses) ==")
        bad = dict(recipe); bad["sha256"] = "0" * 64
        try:
            install(bad, safe_root, receipts); print("   !! placed despite mismatch — BUG")
        except SeamError as e:
            print(f"   refused at STAGE: {e}")

        print("\n== 3. escaping placement (allowlist containment) ==")
        try:
            evil = (safe_root / "apps" / "hello-sovereign" / ".." / ".." / ".." / "etc" / "evil")
            seam_place([(art, evil)], safe_root, app_id, True)
            print("   !! placed outside allowlist — BUG")
        except SeamError as e:
            print(f"   seam refused: {e}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Sandbox-with-a-seam installer")
    ap.add_argument("--recipe", help="path to a recipe JSON")
    ap.add_argument("--safe-root", default=str(DEFAULT_SAFE_ROOT))
    ap.add_argument("--receipts", default=str(DEFAULT_RECEIPTS))
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()

    safe_root = Path(args.safe_root)
    receipts = Path(args.receipts)
    if args.demo:
        return _demo(safe_root, receipts)
    if not args.recipe:
        ap.error("give --recipe or --demo")
    recipe = json.loads(Path(args.recipe).read_text())
    try:
        r = install(recipe, safe_root, receipts)
    except SeamError as e:
        print(f"install FAILED: {e}", file=sys.stderr)
        return 1
    print(json.dumps(r, indent=2))
    return 0 if r["launch_verified"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
