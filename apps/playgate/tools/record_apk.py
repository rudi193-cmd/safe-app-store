"""Record an operator-supplied APK for a catalog entry.

Use for apps not on F-Droid (e.g. Toca Boca World). Playgate never downloads
from third-party APK sites — you place the bytes, this script hashes them and
copies into data/apks/ for staging into the vault on serve().
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APK_DIR = ROOT / "data" / "apks"
SOURCES = APK_DIR / "SOURCES.json"


def _digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1 << 20):
            sha.update(block)
    return sha.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="record an operator-supplied APK")
    parser.add_argument("catalog_id", help="catalog entry id, e.g. toca-boca-world")
    parser.add_argument("apk", type=Path, help="path to the APK file you already have")
    parser.add_argument("--filename", help="destination name under data/apks/ (default: <id>.apk)")
    parser.add_argument(
        "--to-vault",
        action="store_true",
        help="also copy into the vault apk directory",
    )
    args = parser.parse_args(argv)

    src = args.apk.expanduser().resolve()
    if not src.is_file():
        print(f"not found: {src}", file=sys.stderr)
        return 2

    filename = args.filename or f"{args.catalog_id}.apk"
    APK_DIR.mkdir(parents=True, exist_ok=True)
    dest = APK_DIR / filename
    shutil.copy2(src, dest)
    digest = _digest(dest)
    print(f"copied -> {dest}")
    print(f"sha256: {digest}")
    print()
    print("Add to data/catalog.json (apk_path and sha256 must both be set):")
    print(json.dumps({"apk_path": filename, "sha256": digest}, indent=2))

    if args.to_vault:
        try:
            from playgate import paths as paths_mod

            vault = paths_mod.apk_dir()
            vault.mkdir(parents=True, exist_ok=True)
            target = vault / filename
            shutil.copy2(dest, target)
            print(f"vault:  {target}")
        except ImportError as exc:
            print(f"warning: could not copy to vault: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
