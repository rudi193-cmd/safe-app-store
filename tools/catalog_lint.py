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

Also the store refit's P1 gate (docs/store_refit_plan.md), over the keeping
records at stores/{major}/stored/<app_id>.json:

  record-coverage — every apps/<dir> resolves to exactly one keeping record,
                 or is explicitly named in stores/pending.json with a reason
                 (absence is a value, not a gap — an unrecorded build with no
                 pending entry is just a gap).
  no-duplicates — no two records claim the same app_id.
  majors       — every major a record names is a real store (a
                 stores/<major>/ with both stored/ and promoted/).
  relation     — a record naming more than one major must name the relation;
                 differential-paired records must also name the anchor, and
                 the anchor must be one of the record's own majors.
  location     — a record's location resolves: a real apps/ path, or an
                 http(s) URL for work kept outside this tree.
  state        — state is one of the closed enum (seeded, building, gated,
                 stalled, archived) — never invented, same discipline as
                 status above.

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

# P1 — the keeping record (docs/store_refit_plan.md)
VALID_STATES = {"seeded", "building", "gated", "stalled", "archived"}
VALID_RELATIONS = {
    "differential-paired", "sidecar", "runtime-fallback",
    "alternate-deploy-targets", "unrelated-bundled",
}


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

    record_errors, record_warnings = lint_records()
    errors.extend(record_errors)
    warnings.extend(record_warnings)

    return errors, warnings


def _real_majors() -> set[str]:
    stores_dir = REPO / "stores"
    return {
        d.name for d in stores_dir.iterdir()
        if d.is_dir() and (d / "stored").is_dir() and (d / "promoted").is_dir()
    }


def lint_records() -> tuple[list[str], list[str]]:
    """P1's gate: stores/{major}/stored/<app_id>.json keeping records agree
    with apps/ and with each other. See module docstring."""
    errors: list[str] = []
    warnings: list[str] = []
    majors = _real_majors()

    pending_ids: set[str] = set()
    pending_path = REPO / "stores" / "pending.json"
    if pending_path.is_file():
        try:
            pending_data = json.loads(pending_path.read_text())
        except json.JSONDecodeError as exc:
            errors.append(f"stores/pending.json: invalid JSON: {exc}")
            pending_data = {}
        for entry in pending_data.get("pending", []):
            app_id = entry.get("app_id")
            if not app_id:
                errors.append("stores/pending.json: entry missing app_id")
                continue
            if not entry.get("reason") or not entry.get("blocked_on"):
                errors.append(
                    f"stores/pending.json: {app_id} is missing reason/blocked_on "
                    "— absence must be recorded, not just declared"
                )
            pending_ids.add(app_id)

    records_by_app_id: dict[str, Path] = {}
    for major in sorted(majors):
        stored_dir = REPO / "stores" / major / "stored"
        for record_path in sorted(stored_dir.glob("*.json")):
            rel = record_path.relative_to(REPO)
            try:
                record = json.loads(record_path.read_text())
            except json.JSONDecodeError as exc:
                errors.append(f"{rel}: invalid JSON: {exc}")
                continue

            app_id = record.get("app_id")
            if not app_id:
                errors.append(f"{rel}: missing app_id")
                continue
            if record_path.stem != app_id:
                errors.append(f"{rel}: filename {record_path.stem!r} != app_id {app_id!r}")

            if app_id in records_by_app_id:
                errors.append(
                    f"{app_id}: duplicate keeping record "
                    f"({records_by_app_id[app_id]} and {rel})"
                )
            records_by_app_id[app_id] = rel

            record_majors = record.get("majors")
            if not isinstance(record_majors, list) or not record_majors:
                errors.append(f"{app_id}: majors must be a non-empty list")
                record_majors = []
            for m in record_majors:
                if m not in majors:
                    errors.append(f"{app_id}: major {m!r} is not a real store")

            relation = record.get("relation")
            if len(record_majors) > 1 and not relation:
                errors.append(f"{app_id}: spans {record_majors} but names no relation")
            if relation is not None and relation not in VALID_RELATIONS:
                errors.append(f"{app_id}: invalid relation {relation!r}")

            anchor = record.get("anchor")
            if relation == "differential-paired" and not anchor:
                errors.append(f"{app_id}: differential-paired record needs an anchor")
            if anchor is not None and record_majors and anchor not in record_majors:
                errors.append(
                    f"{app_id}: anchor {anchor!r} not among its own majors {record_majors}"
                )

            location = record.get("location")
            if not location:
                errors.append(f"{app_id}: missing location")
            else:
                is_url = isinstance(location, str) and location.startswith(("http://", "https://"))
                if not is_url and not (REPO / location).exists():
                    errors.append(f"{app_id}: location {location!r} does not resolve")

            state = record.get("state")
            if state not in VALID_STATES:
                errors.append(f"{app_id}: invalid state {state!r}")

    apps_dir = REPO / "apps"
    if apps_dir.is_dir():
        app_dirs = {d.name for d in apps_dir.iterdir() if d.is_dir()}
        for app_id in sorted(app_dirs):
            if app_id in records_by_app_id or app_id in pending_ids:
                continue
            errors.append(
                f"{app_id}: no keeping record and not listed in stores/pending.json"
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
