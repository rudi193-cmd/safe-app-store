"""
case_store.py — Law Gazelle case database sync and queries.

Copies Nest SQLite databases into ~/.willow/apps/law-gazelle/cases/ on startup.
Reads coparent, bankruptcy, and workers_comp databases as-is (no schema migration).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
from ast import literal_eval
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import gazelle_state

APP_ID = "law-gazelle"
APP_DATA = Path(os.environ.get("APP_DATA", Path.home() / ".willow" / "apps" / APP_ID))
CASES_DIR = APP_DATA / "cases"
DEFAULT_SOURCE = Path(os.environ.get("NEST_SOURCE", Path.home() / "Desktop" / "Nest"))

CASE_DBS = {
    "coparent": "coparent.db",
    "bankruptcy": "bankruptcy.db",
    "workers_comp": "workers_comp.db",
}

# Alternate filenames to try when syncing workers comp.
WORKERS_COMP_ALIASES = (
    "workers_comp.db",
    "workcomp.db",
    "wca.db",
    "workers_compensation.db",
)

SYNC_EXTRAS = ("coparent_db_export.json",)
SESSION_META_DB = "session_meta.db"
LETTER_GLOB = "Campbell_Letter*.docx"

MILESTONES = (
    {"date": "2026-05-30", "label": "Schedule response (letter)"},
    {"date": "2026-06-06", "label": "All other letter items"},
    {"date": "2026-07-01", "label": "City job / Ch7 filing / support modification"},
)


def _parse_evidence_ids(raw: str | None) -> list[str]:
    if not raw:
        return []
    raw = raw.strip()
    try:
        parsed = literal_eval(raw)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except (ValueError, SyntaxError):
        pass
    return re.findall(r"EVD-\d{4}-\d{3}", raw)


def _days_until(deadline: str | None) -> int | None:
    if not deadline:
        return None
    dl = deadline[:10]
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%B %d %Y"):
        try:
            d = datetime.strptime(dl.strip().rstrip(","), fmt).date()
            return (d - date.today()).days
        except ValueError:
            continue
    return None


def _item_key(item: dict) -> tuple[str, str, str]:
    return (
        item.get("source_db") or item.get("case") or "",
        item.get("item_type") or item.get("kind") or "",
        item.get("item_id") or item.get("flag_id") or item.get("atom_id") or item.get("deadline_key") or "",
    )


def _merge_overlay(item: dict) -> dict:
    source_db, item_type, item_id = _item_key(item)
    if not item_id:
        return item
    status = gazelle_state.get_status(source_db, item_type, item_id)
    if status:
        item["overlay_status"] = status["status"]
        item["overlay_notes"] = status.get("notes")
    item["snoozed"] = gazelle_state.is_snoozed(source_db, item_type, item_id)
    item["user_notes"] = gazelle_state.list_notes(source_db, item_type, item_id)
    src_status = item.get("status")
    item["effective_resolved"] = gazelle_state.effective_resolved(
        source_db, item_type, item_id, src_status
    )
    return item


def milestones() -> list[dict]:
    today = date.today()
    out = []
    for m in MILESTONES:
        d = date.fromisoformat(m["date"])
        days = (d - today).days
        out.append({
            **m,
            "days_until": days,
            "overdue": days < 0,
        })
    return out


def milestone_banner() -> str:
    parts = []
    for m in milestones():
        tag = "OVERDUE" if m["overdue"] else f"{m['days_until']}d"
        parts.append(f"{m['date']} ({tag}): {m['label']}")
    return "  |  ".join(parts)

def _copy_if_updated(src: Path, dest: Path, copied: list[str], skipped: list[str]) -> bool:
    """Copy src to dest when missing or source is newer. Returns True if copied."""
    if dest.exists() and src.stat().st_mtime <= dest.stat().st_mtime:
        if dest.stat().st_size == src.stat().st_size:
            skipped.append(dest.name)
            return False
    shutil.copy2(src, dest)
    copied.append(dest.name)
    return True


def sync_cases(source: Path | str = DEFAULT_SOURCE) -> dict:
    """Copy case databases from Nest into the app data directory."""
    source = Path(source)
    CASES_DIR.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    missing: list[str] = []
    skipped: list[str] = []
    optional_missing: list[str] = []

    for case_key, filename in CASE_DBS.items():
        if case_key == "workers_comp":
            src = _find_workers_comp_source(source)
            if src is None:
                missing.append(filename)
                continue
            dest = CASES_DIR / filename
        else:
            src = source / filename
            dest = CASES_DIR / filename
            if not src.exists():
                missing.append(filename)
                continue

        _copy_if_updated(src, dest, copied, skipped)

    for extra in SYNC_EXTRAS:
        src = source / extra
        if not src.exists():
            optional_missing.append(extra)
            continue
        dest = CASES_DIR / extra
        _copy_if_updated(src, dest, copied, skipped)

    session_src = source / SESSION_META_DB
    if session_src.exists():
        _copy_if_updated(session_src, CASES_DIR / SESSION_META_DB, copied, skipped)
    else:
        optional_missing.append(SESSION_META_DB)

    letter_found = False
    for letter_src in sorted(source.glob(LETTER_GLOB)):
        letter_found = True
        _copy_if_updated(letter_src, CASES_DIR / letter_src.name, copied, skipped)
    if not letter_found:
        optional_missing.append(LETTER_GLOB)

    return {
        "source": str(source),
        "dest": str(CASES_DIR),
        "copied": copied,
        "skipped": skipped,
        "missing": missing,
        "optional_missing": optional_missing,
        "artifacts": [a["name"] for a in list_artifacts()],
    }


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _row_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None


def _query_path(path: Path, sql: str, params: tuple = ()) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def session_meta_path() -> Path:
    return CASES_DIR / SESSION_META_DB


def list_artifacts() -> list[dict]:
    """Synced letter/docx artifacts from Nest."""
    artifacts: list[dict] = []
    for path in sorted(CASES_DIR.glob("Campbell_Letter*.docx")):
        stat = path.stat()
        artifacts.append({
            "name": path.name,
            "path": str(path),
            "size_kb": round(stat.st_size / 1024, 1),
            "modified": date.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return artifacts


def session_overview() -> dict:
    """Session provenance from session_meta.db."""
    path = session_meta_path()
    if not path.exists():
        return {"present": False}

    meta_rows = _query_path(path, "SELECT key, value, category FROM session_meta ORDER BY id")
    meta = {row["key"]: row["value"] for row in meta_rows}
    decisions = _query_path(
        path,
        "SELECT id, decision, rationale, outcome, would_change FROM architecture_decisions ORDER BY id",
    )
    return {
        "present": True,
        "meta": meta,
        "decisions": decisions,
        "artifacts": list_artifacts(),
    }


def _find_workers_comp_source(source: Path) -> Path | None:
    for name in WORKERS_COMP_ALIASES:
        path = source / name
        if path.exists():
            return path
    return None


def db_path(case_key: str) -> Path:
    return CASES_DIR / CASE_DBS[case_key]


def db_exists(case_key: str) -> bool:
    return db_path(case_key).exists()


def _query(case_key: str, sql: str, params: tuple = ()) -> list[dict]:
    path = db_path(case_key)
    if not path.exists():
        return []
    with _connect(path) as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def load_coparent_meta() -> dict:
    """Load _meta from the JSON export if present."""
    export_path = CASES_DIR / "coparent_db_export.json"
    if not export_path.exists():
        return {}
    try:
        data = json.loads(export_path.read_text(encoding="utf-8"))
        return data.get("_meta") or {}
    except (OSError, json.JSONDecodeError):
        return {}


def list_cases() -> list[dict]:
    """Summary of all case databases on disk."""
    cases: list[dict] = []

    if db_exists("coparent"):
        meta = load_coparent_meta()
        open_atoms = _query(
            "coparent",
            "SELECT COUNT(*) AS n FROM atoms WHERE status = 'open'",
        )
        cases.append({
            "key": "coparent",
            "title": "Co-Parent / Family Law",
            "case_number": meta.get("case") or "D-000-DM-0000-00000",
            "jurisdiction": meta.get("jurisdiction") or "Example County, ST",
            "status": "active",
            "open_items": open_atoms[0]["n"] if open_atoms else 0,
        })

    if db_exists("bankruptcy"):
        rows = _query(
            "bankruptcy",
            "SELECT case_id, chapter, status FROM case_registry ORDER BY id",
        )
        open_flags = _query(
            "bankruptcy",
            "SELECT COUNT(*) AS n FROM critical_flags WHERE resolved = 0",
        )
        active = next((r for r in rows if r.get("status") != "DISMISSED"), rows[0] if rows else {})
        cases.append({
            "key": "bankruptcy",
            "title": "Bankruptcy",
            "case_number": active.get("case_id", "—"),
            "jurisdiction": "District of New Mexico",
            "status": active.get("status", "unknown"),
            "open_items": open_flags[0]["n"] if open_flags else 0,
            "chapter": active.get("chapter"),
        })

    if db_exists("workers_comp"):
        cases.append({
            "key": "workers_comp",
            "title": "Workers' Compensation",
            "case_number": "WCA 00-00000",
            "jurisdiction": "New Mexico WCA",
            "status": "active",
            "open_items": 0,
        })
    else:
        cases.append({
            "key": "workers_comp",
            "title": "Workers' Compensation",
            "case_number": "WCA 00-00000",
            "jurisdiction": "New Mexico WCA",
            "status": "missing_db",
            "open_items": 0,
        })

    return cases


def urgent_flags() -> list[dict]:
    """Unresolved critical flags from bankruptcy.db."""
    rows = _query(
        "bankruptcy",
        """
        SELECT flag_id, severity, title, description, action_required, deadline
        FROM critical_flags
        WHERE resolved = 0
        ORDER BY
            CASE severity
                WHEN 'URGENT' THEN 0
                WHEN 'HIGH' THEN 1
                WHEN 'MEDIUM' THEN 2
                ELSE 3
            END,
            deadline
        """,
    )
    for row in rows:
        row["case"] = "bankruptcy"
        row["source_db"] = "bankruptcy"
        row["kind"] = "flag"
        row["item_type"] = "flag"
        row["item_id"] = row["flag_id"]
    return rows


def urgent_atoms(limit: int = 50) -> list[dict]:
    """Open urgent/high atoms from coparent.db."""
    rows = _query(
        "coparent",
        """
        SELECT atom_id, type, priority, domain, title, action_required, status
        FROM atoms
        WHERE status = 'open' AND priority IN ('urgent', 'high')
        ORDER BY
            CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 ELSE 2 END,
            id
        LIMIT ?
        """,
        (limit,),
    )
    for row in rows:
        row["case"] = "coparent"
        row["source_db"] = "coparent"
        row["kind"] = "atom"
        row["item_type"] = "atom"
        row["item_id"] = row["atom_id"]
    return rows


def response_deadlines() -> list[dict]:
    """Hard deadlines from coparent export _meta."""
    meta = load_coparent_meta()
    deadlines = meta.get("response_deadlines") or {}
    items: list[dict] = []
    today = date.today().isoformat()

    labels = {
        "schedule": "Schedule proposals (letter response)",
        "all_other": "All other letter items",
    }
    for key, due in deadlines.items():
        days = _days_until(due)
        items.append({
            "case": "coparent",
            "source_db": "coparent",
            "kind": "deadline",
            "item_type": "deadline",
            "item_id": f"deadline:{key}",
            "deadline_key": key,
            "title": labels.get(key, key.replace("_", " ").title()),
            "deadline": due,
            "days_until": days,
            "overdue": due < today if due else False,
            "severity": "URGENT" if due and due < today else "HIGH",
        })
    return items


def urgent_queue(show_resolved: bool = False) -> list[dict]:
    """Combined urgent items across all cases, sorted for display."""
    items: list[dict] = []
    items.extend(response_deadlines())
    items.extend(urgent_flags())
    items.extend(urgent_atoms())

    merged: list[dict] = []
    for item in items:
        item = _merge_overlay(item)
        if item.get("snoozed") and not show_resolved:
            continue
        if item.get("effective_resolved") and not show_resolved:
            continue
        dl = item.get("deadline")
        if item.get("days_until") is None and dl:
            item["days_until"] = _days_until(str(dl))
        if item.get("overdue") is None and item.get("days_until") is not None:
            item["overdue"] = item["days_until"] < 0
        merged.append(item)

    def sort_key(item: dict) -> tuple:
        overdue = 0 if item.get("overdue") else 1
        days = item.get("days_until")
        days_sort = days if days is not None else 9999
        sev = item.get("severity") or item.get("priority") or "normal"
        rank = {"URGENT": 0, "urgent": 0, "HIGH": 1, "high": 1, "MEDIUM": 2, "normal": 3}.get(sev, 4)
        return (overdue, days_sort, rank)

    return sorted(merged, key=sort_key)


def get_atom_detail(atom_id: str, source_db: str = "coparent") -> dict | None:
    if source_db not in CASE_DBS:
        source_db = "coparent"
    rows = _query(source_db, "SELECT * FROM atoms WHERE atom_id = ?", (atom_id,))
    if not rows and source_db == "coparent" and db_exists("workers_comp"):
        rows = _query("workers_comp", "SELECT * FROM atoms WHERE atom_id = ?", (atom_id,))
        if rows:
            source_db = "workers_comp"
    if not rows:
        return None
    atom = rows[0]
    issue = None
    if atom.get("related_issue_id") and source_db == "coparent":
        iss = _query("coparent", "SELECT * FROM issues WHERE id = ?", (atom["related_issue_id"],))
        issue = iss[0] if iss else None
    evidence = []
    if source_db == "coparent":
        for eid in _parse_evidence_ids(atom.get("related_evidence")):
            ev = get_evidence_detail(eid)
            if ev:
                evidence.append(ev)
    legal_ref = atom.get("legal_ref") or ""
    plan_citations = []
    state_laws = []
    if legal_ref and source_db == "coparent":
        plan_citations = _query(
            "coparent",
            """
            SELECT * FROM plan_citations
            WHERE section LIKE ? OR clause LIKE ? OR verbatim_text LIKE ?
            LIMIT 10
            """,
            (f"%{legal_ref[:20]}%", f"%{legal_ref[:20]}%", f"%{legal_ref[:20]}%"),
        )
        for word in re.findall(r"§[\w\.]+|NMSA[^,\s]+|40-4-[\d\.]+", legal_ref):
            state_laws.extend(_query(
                "coparent",
                "SELECT * FROM state_law WHERE statute LIKE ? OR summary LIKE ? LIMIT 5",
                (f"%{word}%", f"%{word}%"),
            ))
    detail = {
        "type": "atom",
        "source_db": source_db,
        "item_type": "atom",
        "item_id": atom_id,
        "atom": atom,
        "issue": issue,
        "evidence": evidence,
        "plan_citations": plan_citations,
        "state_law": _dedupe_rows(state_laws, "law_id"),
        "intersections": _related_intersections(atom.get("title", "") + " " + atom.get("body", "")),
    }
    detail["overlay"] = gazelle_state.get_status(source_db, "atom", atom_id)
    detail["notes"] = gazelle_state.list_notes(source_db, "atom", atom_id)
    return detail


def get_flag_detail(flag_id: str) -> dict | None:
    rows = _query("bankruptcy", "SELECT * FROM critical_flags WHERE flag_id = ?", (flag_id,))
    if not rows:
        return None
    flag = rows[0]
    text = " ".join(str(flag.get(k) or "") for k in ("title", "description", "action_required"))
    detail = {
        "type": "flag",
        "source_db": "bankruptcy",
        "item_type": "flag",
        "item_id": flag_id,
        "flag": flag,
        "intersections": _related_intersections(text),
    }
    detail["overlay"] = gazelle_state.get_status("bankruptcy", "flag", flag_id)
    detail["notes"] = gazelle_state.list_notes("bankruptcy", "flag", flag_id)
    return detail


def get_issue_detail(issue_id: int) -> dict | None:
    rows = _query("coparent", "SELECT * FROM issues WHERE id = ?", (issue_id,))
    if not rows:
        return None
    issue = rows[0]
    atoms = _query("coparent", "SELECT * FROM atoms WHERE related_issue_id = ?", (issue_id,))
    evidence = _query(
        "coparent",
        "SELECT * FROM evidence_ledger WHERE related_issue_id = ?",
        (issue_id,),
    )
    return {
        "type": "issue",
        "source_db": "coparent",
        "item_type": "issue",
        "item_id": str(issue_id),
        "issue": issue,
        "atoms": atoms,
        "evidence": evidence,
        "notes": gazelle_state.list_notes("coparent", "issue", str(issue_id)),
    }


def get_evidence_detail(evidence_id: str) -> dict | None:
    rows = _query(
        "coparent",
        "SELECT * FROM evidence_ledger WHERE evidence_id = ?",
        (evidence_id,),
    )
    if not rows:
        return None
    ev = rows[0]
    issue = None
    if ev.get("related_issue_id"):
        iss = _query("coparent", "SELECT * FROM issues WHERE id = ?", (ev["related_issue_id"],))
        issue = iss[0] if iss else None
    return {
        "type": "evidence",
        "source_db": "coparent",
        "item_type": "evidence",
        "item_id": evidence_id,
        "evidence": ev,
        "issue": issue,
        "notes": gazelle_state.list_notes("coparent", "evidence", evidence_id),
    }


def get_deadline_detail(deadline_key: str) -> dict:
    meta = load_coparent_meta()
    deadlines = meta.get("response_deadlines") or {}
    due = deadlines.get(deadline_key, "")
    labels = {
        "schedule": "Schedule proposals (letter response)",
        "all_other": "All other letter items",
    }
    return {
        "type": "deadline",
        "source_db": "coparent",
        "item_type": "deadline",
        "item_id": f"deadline:{deadline_key}",
        "title": labels.get(deadline_key, deadline_key),
        "deadline": due,
        "days_until": _days_until(due),
        "notes": gazelle_state.list_notes("coparent", "deadline", f"deadline:{deadline_key}"),
    }


def get_case_detail(case_key: str) -> dict | None:
    """Summary drill-down for a case row on the Cases tab."""
    cases = {c["key"]: c for c in list_cases()}
    case = cases.get(case_key)
    if not case:
        return None
    detail: dict = {
        "type": "case",
        "source_db": case_key if case_key in CASE_DBS else "session",
        "item_type": "case",
        "item_id": case_key,
        "case": case,
    }
    if case_key == "coparent":
        detail["meta"] = load_coparent_meta()
        detail["open_atoms"] = coparent_atoms(status="open", limit=25)
        detail["issues"] = coparent_issues(limit=15)
    elif case_key == "bankruptcy":
        detail["overview"] = bankruptcy_overview()
    elif case_key == "workers_comp":
        detail["overview"] = workers_comp_overview()
    return detail


def get_creditor_detail(creditor_id: str) -> dict | None:
    rows = _query(
        "bankruptcy",
        "SELECT * FROM creditors WHERE creditor_id = ? OR CAST(id AS TEXT) = ?",
        (creditor_id, creditor_id),
    )
    if not rows:
        return None
    creditor = rows[0]
    return {
        "type": "creditor",
        "source_db": "bankruptcy",
        "item_type": "creditor",
        "item_id": creditor.get("creditor_id") or str(creditor.get("id", "")),
        "creditor": creditor,
        "intersections": _related_intersections(
            " ".join(str(creditor.get(k) or "") for k in ("name", "debt_type", "notes"))
        ),
    }


def get_context_event_detail(event_id: str) -> dict | None:
    rows = _query("coparent", "SELECT * FROM context_events WHERE id = ?", (int(event_id),))
    if not rows:
        return None
    event = rows[0]
    return {
        "type": "context_event",
        "source_db": "coparent",
        "item_type": "context_event",
        "item_id": str(event_id),
        "event": event,
        "intersections": _related_intersections(
            " ".join(str(event.get(k) or "") for k in ("event_type", "description", "impact_notes"))
        ),
    }


def get_session_meta_detail(key: str) -> dict | None:
    path = session_meta_path()
    if not path.exists():
        return None
    rows = _query_path(path, "SELECT * FROM session_meta WHERE key = ?", (key,))
    if not rows:
        return None
    row = rows[0]
    return {
        "type": "session_meta",
        "source_db": "session",
        "item_type": "session_meta",
        "item_id": key,
        "meta": row,
    }


def get_session_decision_detail(decision_id: str) -> dict | None:
    path = session_meta_path()
    if not path.exists():
        return None
    rows = _query_path(
        path,
        "SELECT * FROM architecture_decisions WHERE id = ?",
        (int(decision_id),),
    )
    if not rows:
        return None
    return {
        "type": "session_decision",
        "source_db": "session",
        "item_type": "session_decision",
        "item_id": str(decision_id),
        "decision": rows[0],
    }


def get_artifact_detail(name: str) -> dict | None:
    for art in list_artifacts():
        if art.get("name") == name:
            return {
                "type": "artifact",
                "source_db": "session",
                "item_type": "artifact",
                "item_id": name,
                "artifact": art,
            }
    return None


def get_item_detail(source_db: str, item_type: str, item_id: str) -> dict | None:
    if item_type == "atom":
        return get_atom_detail(item_id, source_db=source_db)
    if item_type == "flag":
        return get_flag_detail(item_id)
    if item_type == "issue":
        return get_issue_detail(int(item_id))
    if item_type == "evidence":
        return get_evidence_detail(item_id)
    if item_type == "deadline" and item_id.startswith("deadline:"):
        return get_deadline_detail(item_id.split(":", 1)[1])
    if item_type == "deadline":
        return get_deadline_detail(item_id)
    if item_type == "intersection":
        rows = _query(
            "bankruptcy",
            "SELECT * FROM coparent_intersections WHERE issue = ?",
            (item_id,),
        )
        if not rows:
            return None
        return {
            "type": "intersection",
            "source_db": "bankruptcy",
            "item_type": "intersection",
            "item_id": item_id,
            "intersection": rows[0],
        }
    if item_type == "case":
        return get_case_detail(item_id)
    if item_type == "creditor":
        return get_creditor_detail(item_id)
    if item_type == "context_event":
        return get_context_event_detail(item_id)
    if item_type == "session_meta":
        return get_session_meta_detail(item_id)
    if item_type == "session_decision":
        return get_session_decision_detail(item_id)
    if item_type == "artifact":
        return get_artifact_detail(item_id)
    return None


def format_detail_text(detail: dict | None) -> str:
    if not detail:
        return "Item not found."
    lines: list[str] = []
    t = detail.get("type")

    if t == "atom":
        a = detail["atom"]
        lines.extend([
            f"# {a.get('atom_id')}: {a.get('title')}",
            "",
            f"**Priority:** {a.get('priority')} | **Domain:** {a.get('domain')} | **Status:** {a.get('status')}",
            "",
            "## Summary",
            a.get("body") or "",
            "",
            "## Action Required",
            a.get("action_required") or "(none)",
            "",
            f"**Legal ref:** {a.get('legal_ref') or '—'}",
            f"**Flag:** {a.get('flag') or '—'}",
        ])
        if detail.get("issue"):
            i = detail["issue"]
            lines.extend(["", f"## Linked Issue: {i.get('title')}", i.get("description") or ""])
        if detail.get("evidence"):
            lines.append("\n## Evidence")
            for ev in detail["evidence"]:
                e = ev.get("evidence") or ev
                lines.append(f"- **{e.get('evidence_id')}** ({e.get('category')}): {e.get('description', '')[:200]}")
        if detail.get("plan_citations"):
            lines.append("\n## Plan Citations")
            for pc in detail["plan_citations"]:
                lines.append(f"- {pc.get('section')} {pc.get('clause') or ''}: {(pc.get('verbatim_text') or '')[:150]}")
        if detail.get("state_law"):
            lines.append("\n## State Law")
            for sl in detail["state_law"]:
                lines.append(f"- **{sl.get('statute')}** — {sl.get('title')}: {(sl.get('summary') or '')[:150]}")
    elif t == "flag":
        f = detail["flag"]
        lines.extend([
            f"# {f.get('flag_id')}: {f.get('title')}",
            "",
            f"**Severity:** {f.get('severity')} | **Deadline:** {f.get('deadline') or '—'}",
            "",
            f.get("description") or "",
            "",
            "## Action Required",
            f.get("action_required") or "(none)",
        ])
    elif t == "deadline":
        lines.extend([
            f"# {detail.get('title')}",
            "",
            f"**Due:** {detail.get('deadline')} ({detail.get('days_until')} days)",
        ])
    elif t == "intersection":
        x = detail.get("intersection") or {}
        lines.extend([
            f"# Cross-Case: {x.get('issue')}",
            "",
            "## Bankruptcy Impact",
            x.get("bankruptcy_impact") or "",
            "",
            "## Coparent Impact",
            x.get("coparent_impact") or "",
            "",
            "## Action",
            x.get("action") or "",
        ])
    elif t == "issue":
        i = detail["issue"]
        lines.extend([f"# Issue {i.get('id')}: {i.get('title')}", "", i.get("description") or ""])
        if detail.get("atoms"):
            lines.append("\n## Atoms")
            for a in detail["atoms"]:
                lines.append(f"- {a.get('atom_id')}: {a.get('title')}")
    elif t == "evidence":
        e = detail["evidence"]
        lines.extend([
            f"# {e.get('evidence_id')}",
            "",
            f"**Category:** {e.get('category')} | **Date:** {e.get('event_date') or '—'}",
            "",
            e.get("description") or "",
            "",
            "## Verbatim",
            e.get("verbatim_quote") or "(none)",
            "",
            f"**Legal ref:** {e.get('legal_ref') or '—'}",
            f"**Hash:** {e.get('content_hash') or '—'}",
        ])
    elif t == "case":
        c = detail["case"]
        lines.extend([
            f"# {c.get('title')}",
            "",
            f"**Case number:** {c.get('case_number') or '—'}",
            f"**Status:** {c.get('status') or '—'}",
            f"**Jurisdiction:** {c.get('jurisdiction') or '—'}",
            f"**Open items:** {c.get('open_items', 0)}",
        ])
        if c.get("chapter"):
            lines.append(f"**Chapter:** {c['chapter']}")
        if detail.get("meta"):
            meta = detail["meta"]
            for key in ("case", "jurisdiction", "letter_sent", "response_deadline_1"):
                if meta.get(key):
                    lines.append(f"**{key.replace('_', ' ').title()}:** {meta[key]}")
        if detail.get("open_atoms"):
            lines.append("\n## Open Atoms")
            for a in detail["open_atoms"]:
                lines.append(f"- **{a.get('atom_id')}** ({a.get('priority')}): {a.get('title')}")
        if detail.get("issues"):
            lines.append("\n## Issues")
            for i in detail["issues"]:
                lines.append(f"- **{i.get('id')}** ({i.get('priority')}): {i.get('title')}")
        overview = detail.get("overview") or {}
        if overview.get("flags"):
            lines.append("\n## Open Flags")
            for f in overview["flags"]:
                lines.append(f"- **{f.get('flag_id')}** ({f.get('severity')}): {f.get('title')}")
        if overview.get("atoms"):
            lines.append("\n## Open Atoms")
            for a in overview["atoms"]:
                lines.append(f"- **{a.get('atom_id')}** ({a.get('priority')}): {a.get('title')}")
    elif t == "creditor":
        c = detail["creditor"]
        lines.extend([
            f"# {c.get('name')}",
            "",
            f"**ID:** {c.get('creditor_id') or '—'} | **Relationship:** {c.get('relationship') or '—'}",
            f"**Amount owed:** ${c.get('amount_owed') or '—'} | **Dischargeable:** {c.get('dischargeable', '—')}",
            "",
            f"**Debt type:** {c.get('debt_type') or '—'}",
            "",
            c.get("notes") or "",
        ])
    elif t == "context_event":
        ev = detail["event"]
        lines.extend([
            f"# {ev.get('event_type', 'Context Event')}",
            "",
            f"**Effective date:** {ev.get('effective_date') or '—'}",
            "",
            ev.get("description") or "",
            "",
            "## Impact Notes",
            ev.get("impact_notes") or "(none)",
        ])
    elif t == "session_meta":
        m = detail["meta"]
        lines.extend([
            f"# {m.get('key')}",
            "",
            f"**Category:** {m.get('category') or '—'}",
            "",
            m.get("value") or "",
            "",
            m.get("notes") or "",
        ])
    elif t == "session_decision":
        d = detail["decision"]
        lines.extend([
            f"# {d.get('decision')}",
            "",
            "## Rationale",
            d.get("rationale") or "",
            "",
            "## Outcome",
            d.get("outcome") or "",
            "",
            "## Would Change",
            d.get("would_change") or "(none)",
        ])
    elif t == "artifact":
        a = detail["artifact"]
        lines.extend([
            f"# {a.get('name')}",
            "",
            f"**Path:** {a.get('path') or '—'}",
            f"**Size:** {a.get('size_kb', '?')} KB | **Modified:** {a.get('modified') or '—'}",
            "",
            "Press **o** on the Session tab to open this file.",
        ])

    if detail.get("intersections"):
        lines.append("\n## Cross-Case Impact")
        for x in detail["intersections"]:
            lines.append(f"- **{x.get('issue')}**")
            lines.append(f"  Bankruptcy: {(x.get('bankruptcy_impact') or '')[:120]}")
            lines.append(f"  Coparent: {(x.get('coparent_impact') or '')[:120]}")

    if detail.get("overlay"):
        o = detail["overlay"]
        lines.extend(["", f"## Gazelle Status: {o.get('status')}", o.get("notes") or ""])
    if detail.get("notes"):
        lines.append("\n## Your Notes")
        for n in detail["notes"]:
            lines.append(f"- [{n.get('created_at')}] {n.get('body')}")

    return "\n".join(lines)


def _dedupe_rows(rows: list[dict], key: str) -> list[dict]:
    seen: set[str] = set()
    out = []
    for r in rows:
        k = r.get(key) or str(r)
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def _related_intersections(text: str) -> list[dict]:
    if not text:
        return []
    rows = _query("bankruptcy", "SELECT * FROM coparent_intersections")
    text_l = text.lower()
    hits = []
    for row in rows:
        blob = " ".join(str(row.get(k) or "") for k in row).lower()
        issue = (row.get("issue") or "").lower()
        if issue and issue in text_l:
            hits.append(row)
            continue
        for token in ("july 1", "cssd", "housing", "garnish", "child support", "jessi"):
            if token in text_l and token in blob:
                hits.append(row)
                break
    return _dedupe_rows(hits, "issue")


def cross_case_overview() -> dict:
    intersections = _query("bankruptcy", "SELECT * FROM coparent_intersections")
    creditors = _query("bankruptcy", "SELECT * FROM creditors")
    context = _query("coparent", "SELECT * FROM context_events ORDER BY effective_date")
    related_atoms = _query(
        "coparent",
        """
        SELECT atom_id, title, priority, domain FROM atoms
        WHERE body LIKE '%bankruptcy%' OR body LIKE '%Chapter%' OR body LIKE '%CSSD%'
           OR body LIKE '%July 1%' OR title LIKE '%support%' OR title LIKE '%arrear%'
        ORDER BY priority, id
        LIMIT 20
        """,
    )
    return {
        "intersections": intersections,
        "creditors": creditors,
        "context_events": context,
        "related_atoms": related_atoms,
        "milestones": milestones(),
    }


def coparent_issues(limit: int = 50) -> list[dict]:
    return _query(
        "coparent",
        """
        SELECT id, title, category, priority, status
        FROM issues
        ORDER BY
            CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 ELSE 2 END,
            id
        LIMIT ?
        """,
        (limit,),
    )


def coparent_atoms(status: str = "open", limit: int = 50) -> list[dict]:
    return _query(
        "coparent",
        """
        SELECT atom_id, type, priority, domain, title, action_required, status
        FROM atoms
        WHERE status = ?
        ORDER BY
            CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 ELSE 2 END,
            id
        LIMIT ?
        """,
        (status, limit),
    )


def bankruptcy_overview() -> dict:
    registry = _query("bankruptcy", "SELECT * FROM case_registry ORDER BY id")
    flags = _query(
        "bankruptcy",
        "SELECT * FROM critical_flags WHERE resolved = 0 ORDER BY severity, deadline",
    )
    checklist = _query(
        "bankruptcy",
        """
        SELECT doc_type, status, priority, description
        FROM document_checklist
        ORDER BY
            CASE priority
                WHEN 'FIRST - URGENT' THEN 0
                WHEN 'URGENT' THEN 1
                WHEN 'HIGH' THEN 2
                ELSE 3
            END
        """,
    )
    intersections = _query("bankruptcy", "SELECT * FROM coparent_intersections")
    return {
        "cases": registry,
        "flags": flags,
        "checklist": checklist,
        "intersections": intersections,
    }


def workers_comp_overview() -> dict | None:
    path = db_path("workers_comp")
    if not path.exists():
        return None
    with _connect(path) as conn:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
    overview: dict = {"tables": tables}
    if "atoms" in tables:
        overview["atoms"] = _query(
            "workers_comp",
            """
            SELECT atom_id, type, priority, domain, title, action_required, status
            FROM atoms WHERE status = 'open'
            ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 ELSE 2 END
            LIMIT 50
            """,
        )
    for table in tables:
        if table.startswith("sqlite_") or table == "atoms":
            continue
        rows = _query("workers_comp", f"SELECT * FROM {table} LIMIT 25")
        overview[table] = rows
    return overview


def briefing_packet(include_session: bool = False) -> dict:
    """Single-call LLM briefing: urgent queue + milestones + cross-case overview.

    Returns a compact dict suitable for passing directly to an agent context.
    Does NOT call format_detail_text — returns raw dicts for the agent to reason over.
    For item drill-down use get_item_detail(source_db, item_type, item_id).
    """
    queue = urgent_queue(show_resolved=False)
    banner = milestone_banner()
    ms = milestones()
    cross = cross_case_overview()

    packet: dict = {
        "generated_at": datetime.now().isoformat(),
        "milestone_banner": banner,
        "milestones": ms,
        "urgent_count": len(queue),
        "urgent": queue,
        "cross_case": {
            "intersections": cross.get("intersections", []),
            "related_atoms": cross.get("related_atoms", []),
        },
    }

    if include_session:
        packet["session"] = session_overview()

    return packet


def workers_comp_atoms(status: str = "open", limit: int = 50) -> list[dict]:
    if not db_exists("workers_comp"):
        return []
    with _connect(db_path("workers_comp")) as conn:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='atoms'"
        ).fetchone():
            return []
    return _query(
        "workers_comp",
        """
        SELECT atom_id, type, priority, domain, title, action_required, status
        FROM atoms WHERE status = ?
        ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 ELSE 2 END, id
        LIMIT ?
        """,
        (status, limit),
    )

