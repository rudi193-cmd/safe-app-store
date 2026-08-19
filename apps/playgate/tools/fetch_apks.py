"""Fetch seed APKs from F-Droid and verify against SOURCES.json.

Playgate never downloads at runtime. This script is for operators and CI prep:
it pulls the bytes recorded in data/apks/SOURCES.json, checks sha256, and
optionally copies them into the vault apk directory where serve() installs from.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "data" / "apks" / "SOURCES.json"
APK_DIR = ROOT / "data" / "apks"


def _digest(path: Path) -> str:
    import hashlib

    sha = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1 << 20):
            sha.update(block)
    return sha.hexdigest()


def _fetch(url: str, dest: Path) -> None:
    print(f"fetch {url}")
    with urllib.request.urlopen(url, timeout=300) as response:
        dest.write_bytes(response.read())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="fetch and verify playgate seed APKs")
    parser.add_argument(
        "--to-vault",
        action="store_true",
        help="copy verified APKs into the vault apk directory after fetch",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-download even when the on-disk digest already matches",
    )
    args = parser.parse_args(argv)

    raw = json.loads(SOURCES.read_text())
    entries = raw.get("apks", [])
    if not entries:
        print("SOURCES.json has no apks", file=sys.stderr)
        return 2

    APK_DIR.mkdir(parents=True, exist_ok=True)
    vault_apk_dir: Path | None = None
    if args.to_vault:
        try:
            from playgate import paths as paths_mod

            vault_apk_dir = paths_mod.apk_dir()
            vault_apk_dir.mkdir(parents=True, exist_ok=True)
        except ImportError as exc:
            print(f"cannot resolve vault apk dir: {exc}", file=sys.stderr)
            return 2

    if vault_apk_dir is not None:
        try:
            from playgate import catalog as catalog_mod
            from playgate import paths as paths_mod

            staged = paths_mod.stage_seed_apks(catalog_mod.load(), vault_apk_dir)
            if staged:
                print(f"staged {len(staged)} apk(s) into vault")
        except Exception as exc:
            print(f"warning: could not stage seed apks into vault: {exc}", file=sys.stderr)

    failed = 0
    for entry in entries:
        filename = entry["filename"]
        expected = entry["sha256"].lower()
        dest = APK_DIR / filename
        if dest.is_file() and not args.force:
            actual = _digest(dest)
            if actual == expected:
                print(f"ok   {filename} (cached)")
            else:
                print(f"stale {filename} — digest mismatch, re-fetching")
                _fetch(entry["url"], dest)
        else:
            _fetch(entry["url"], dest)

        actual = _digest(dest)
        if actual != expected:
            print(f"FAIL {filename}: expected {expected}, file is {actual}", file=sys.stderr)
            failed += 1
            continue

        print(f"ok   {filename} sha256 {actual}")
        if vault_apk_dir is not None:
            target = vault_apk_dir / filename
            shutil.copy2(dest, target)
            print(f"     -> {target}")

    if failed:
        return 1
    if vault_apk_dir is not None:
        print(f"vault apks: {vault_apk_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
