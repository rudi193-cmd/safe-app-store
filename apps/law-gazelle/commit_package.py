"""
commit_package.py — Write law_gazelle commit manifest to Nest.

Signals nest_watcher that a legal build session package is ready.
Callable from MCP (gazelle_commit), CLI (scripts/commit_package.py), or import.

b17: LGCP1  ΔΣ=42
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import case_store

NEST = case_store.DEFAULT_SOURCE

CASE_FILES = [
    "coparent.db",
    "bankruptcy.db",
    "workers_comp.db",
    "session_meta.db",
    "coparent_db_export.json",
]

LETTER_GLOBS = tuple(
    glob.strip()
    for glob in os.environ.get("LAW_GAZELLE_LETTER_GLOBS", "Case_Letter*.docx:*_Letter*.docx").split(":")
    if glob.strip()
)
COMMIT_GLOB = "legal_commit_*.json"
MANIFEST_NAME_TEMPLATE = "legal_commit_{date}.json"
DRAFT_SUFFIXES = (".md", ".txt", ".html")


def find_artifacts(nest: Path | None = None) -> list[str]:
    """List case files present in Nest for the manifest."""
    root = nest or NEST
    present: list[str] = []
    for name in CASE_FILES:
        if (root / name).exists():
            present.append(name)
    seen_letters: set[str] = set()
    for pattern in LETTER_GLOBS:
        for p in sorted(root.glob(pattern)):
            if p.name not in seen_letters:
                present.append(p.name)
                seen_letters.add(p.name)
    drafts_dir = root / "drafts"
    if drafts_dir.is_dir():
        for p in sorted(drafts_dir.iterdir()):
            if p.is_file() and p.suffix.lower() in DRAFT_SUFFIXES:
                present.append(f"drafts/{p.name}")
    return present


def build_manifest(
    summary: str,
    session_date: str,
    *,
    nest: Path | None = None,
) -> dict[str, Any]:
    """Build manifest dict without writing."""
    root = nest or NEST
    return {
        "kind": "law_gazelle_commit",
        "status": "prepared",
        "committed_at": datetime.now(timezone.utc).isoformat(),
        "session_date": session_date,
        "case_number": "D-000-DM-0000-00000",
        "files": find_artifacts(root),
        "summary": summary,
    }


def read_latest_manifest(nest: Path | str | None = None) -> dict[str, Any] | None:
    """Newest legal_commit_*.json in Nest, or None if none exist."""
    root = Path(nest) if nest is not None else NEST
    if not root.exists():
        return None
    matches = sorted(
        root.glob(COMMIT_GLOB),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not matches:
        return None
    path = matches[0]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "error": f"Invalid manifest JSON: {path.name}",
            "path": str(path),
            "name": path.name,
        }
    if not isinstance(data, dict):
        return {"error": f"Manifest root must be object: {path.name}", "path": str(path)}
    stat = path.stat()
    files = data.get("files") or []
    return {
        **data,
        "path": str(path),
        "name": path.name,
        "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).date().isoformat(),
        "file_count": len(files),
    }


def write_commit_manifest(
    *,
    summary: str = "",
    session_date: str = "",
    nest: Path | str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Write legal_commit_<date>.json to Nest.

    Returns dict with ok, path, manifest, file_count — or error.
    """
    root = Path(nest) if nest is not None else NEST
    if not root.exists():
        return {"ok": False, "error": f"Nest not found: {root}"}

    session_date = session_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    summary = summary or f"Law Gazelle session {session_date}"

    manifest = build_manifest(summary, session_date, nest=root)
    name = MANIFEST_NAME_TEMPLATE.format(date=session_date)
    dest = root / name

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "path": str(dest),
            "manifest": manifest,
            "file_count": len(manifest["files"]),
        }

    dest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    try:
        import gazelle_state

        gazelle_state.log_activity(
            "commit",
            f"Session commit: {summary} ({len(manifest['files'])} files)",
        )
    except Exception:
        pass
    return {
        "ok": True,
        "path": str(dest),
        "manifest": manifest,
        "file_count": len(manifest["files"]),
        "message": (
            f"Manifest written: {dest.name} ({len(manifest['files'])} files). "
            "nest_watcher should alert on new legal_commit_*.json."
        ),
    }
