#!/usr/bin/env python3
"""
catalog_lint.py — catalog/directory consistency gate (store operating rules 4-8)

Checks that catalog.json and apps/ tell the same story:

  parse        — catalog.json is valid JSON with a top-level "apps" list.
  fields       — every entry has id, name, description, status; status is one
                 of stable | beta | coming_soon | archived; ids are unique.
  path         — if an entry has a path, the directory exists and its basename
                 equals the id (rule 8: app_id = directory name).
  presence     — an entry may omit path only when it is archived (rule 4:
                 archive, don't delete) or lives in an external repository.
  coverage     — every apps/<dir> has a catalog entry. Unregistered apps are
                 invisible to the store; register or archive them.
  manifest     — beta/stable local apps carry safe-app-manifest.json, and the
                 manifest's app_id matches the directory (rule 8 again).

Verdicts:
  ERROR — the catalog and the tree disagree; the store is lying to someone.
  WARN  — coming_soon app without a manifest, or similar rough edge.

Usage:
  tools/catalog_lint.py            # report
  tools/catalog_lint.py --strict   # exit 1 on any ERROR (CI gate)
  tools/catalog_lint.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VALID_STATUSES = {"stable", "beta", "coming_soon", "archived"}
REQUIRED_FIELDS = ("id", "name", "description", "status")


def lint() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    catalog_path = REPO / "catalog.json"
    try:
        catalog = json.loads(catalog_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return [f"catalog.json unreadable: {exc}"], warnings

    apps = catalog.get("apps")
    if not isinstance(apps, list):
        return ['catalog.json has no "apps" list'], warnings

    seen_ids: set[str] = set()
    for entry in apps:
        app_id = entry.get("id", "<missing id>")
        for field in REQUIRED_FIELDS:
            if not entry.get(field):
                errors.append(f"{app_id}: missing required field '{field}'")
        status = entry.get("status")
        if status not in VALID_STATUSES:
            errors.append(f"{app_id}: invalid status {status!r}")
        if app_id in seen_ids:
            errors.append(f"{app_id}: duplicate catalog entry")
        seen_ids.add(app_id)

        path = entry.get("path")
        if path:
            app_dir = REPO / path
            if not app_dir.is_dir():
                errors.append(f"{app_id}: path {path} does not exist")
            elif app_dir.name != app_id:
                errors.append(
                    f"{app_id}: path basename {app_dir.name!r} != id (rule 8)"
                )
        elif status != "archived" and not entry.get("repository"):
            errors.append(
                f"{app_id}: no path, not archived, no external repository"
            )

        if path and (REPO / path).is_dir():
            manifest_path = REPO / path / "safe-app-manifest.json"
            if manifest_path.is_file():
                try:
                    manifest = json.loads(manifest_path.read_text())
                except json.JSONDecodeError as exc:
                    errors.append(f"{app_id}: safe-app-manifest.json invalid: {exc}")
                else:
                    if manifest.get("app_id") != app_id:
                        errors.append(
                            f"{app_id}: manifest app_id "
                            f"{manifest.get('app_id')!r} != directory (rule 8)"
                        )
            elif status in ("beta", "stable"):
                errors.append(f"{app_id}: {status} app without safe-app-manifest.json")
            elif status == "coming_soon":
                warnings.append(f"{app_id}: no safe-app-manifest.json yet ({status})")

    cataloged_dirs = {
        Path(e["path"]).name for e in apps if e.get("path")
    }
    for app_dir in sorted((REPO / "apps").iterdir()):
        if app_dir.is_dir() and app_dir.name not in cataloged_dirs:
            errors.append(
                f"{app_dir.name}: directory apps/{app_dir.name} has no catalog entry"
            )

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="exit 1 on any ERROR")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    errors, warnings = lint()

    if args.json:
        print(json.dumps({"errors": errors, "warnings": warnings}, indent=2))
    else:
        for e in errors:
            print(f"❌ ERROR {e}")
        for w in warnings:
            print(f"⚠️  WARN  {w}")
        print(f"\ncatalog: {len(errors)} error(s) · {len(warnings)} warning(s)")

    return 1 if (args.strict and errors) else 0


if __name__ == "__main__":
    sys.exit(main())
