"""
document_store.py — LLM document drafting context and Nest output.

Reads case data via case_store; writes drafts to Nest (canonical artifacts).
The LLM (via MCP or Cursor) authors content; this module supplies context
and persistence — it does not call cloud LLMs directly.

b17: LGDOC1  ΔΣ=42
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import case_store

NEST = case_store.DEFAULT_SOURCE
DRAFT_DIR_NAME = "drafts"
DISCLOSURE = (
    "This document was prepared with AI assistance. "
    "Review carefully before sending. Not legal advice."
)

DOCUMENT_TYPES: dict[str, dict[str, Any]] = {
    "schedule_response": {
        "title": "Schedule Response Letter",
        "deadline_key": "schedule",
        "description": "Proposed schedule changes in response to a source letter.",
        "atom_domains": ("schedule",),
        "include_schedule_packet": True,
    },
    "letter_all_other": {
        "title": "Letter Response — All Other Items",
        "deadline_key": "all_other",
        "description": "Response to non-schedule items from a source letter.",
        "atom_domains": None,
        "exclude_domains": ("schedule",),
    },
    "general": {
        "title": "General Correspondence",
        "deadline_key": None,
        "description": "General co-parent correspondence grounded in case atoms.",
        "atom_domains": None,
    },
}


def _nest_drafts_dir() -> Path:
    d = NEST / DRAFT_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_filename(name: str) -> str:
    name = name.strip()
    if not name.lower().endswith((".md", ".txt", ".html")):
        name += ".md"
    name = re.sub(r"[^\w.\- ]+", "_", name)
    return name.replace(" ", "_")


def draft_context(doc_type: str, atom_ids: list[str] | None = None) -> dict:
    """Context packet for the LLM to author a document. Returns dict, not prose."""
    spec = DOCUMENT_TYPES.get(doc_type)
    if not spec:
        return {"error": f"Unknown doc_type: {doc_type}. Valid: {list(DOCUMENT_TYPES)}"}

    meta = case_store.load_coparent_meta()
    parties = meta.get("parties") or {}
    deadlines = meta.get("deadlines") or meta.get("response_deadlines") or {}

    atoms: list[dict] = []
    if atom_ids:
        for aid in atom_ids:
            d = case_store.get_atom_detail(aid)
            if d:
                atoms.append(d)
    elif spec.get("atom_domains"):
        for domain in spec["atom_domains"]:
            for row in case_store._query(  # noqa: SLF001 — internal query helper
                "coparent",
                """
                SELECT atom_id FROM atoms
                WHERE status = 'open' AND domain = ?
                ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 ELSE 2 END, id
                """,
                (domain,),
            ):
                d = case_store.get_atom_detail(row["atom_id"])
                if d:
                    atoms.append(d)
    elif spec.get("exclude_domains"):
        exclude = set(spec["exclude_domains"])
        for row in case_store.coparent_atoms(status="open", limit=100):
            if row.get("domain") not in exclude:
                d = case_store.get_atom_detail(row["atom_id"])
                if d:
                    atoms.append(d)
    else:
        for row in case_store.coparent_atoms(status="open", limit=50):
            d = case_store.get_atom_detail(row["atom_id"])
            if d:
                atoms.append(d)

    deadline_key = spec.get("deadline_key")
    due = deadlines.get(deadline_key) if deadline_key else None

    packet: dict[str, Any] = {
        "doc_type": doc_type,
        "title": spec["title"],
        "description": spec["description"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "disclosure": DISCLOSURE,
        "case_number": meta.get("case") or "D-000-DM-0000-00000",
        "jurisdiction": meta.get("jurisdiction"),
        "parties": parties,
        "governing_docs": meta.get("governing_docs") or [],
        "letter_sent": meta.get("letter_sent"),
        "deadline": {
            "key": deadline_key,
            "date": due,
            "days_until": case_store._days_until(due) if due else None,  # noqa: SLF001
        }
        if deadline_key
        else None,
        "atoms": atoms,
        "atom_ids": [a["atom"]["atom_id"] for a in atoms if a.get("atom")],
        "structure_template": structure_template(doc_type),
        "writing_instructions": _writing_instructions(doc_type),
    }

    if spec.get("include_schedule_packet"):
        packet["schedule_packet"] = case_store.schedule_response_packet()

    packet["chronology"] = chronology_builder("coparent")
    packet["prior_artifacts"] = case_store.list_artifacts()
    return packet


def structure_template(doc_type: str) -> str:
    """Markdown skeleton the LLM should fill in."""
    meta = case_store.load_coparent_meta()
    parties = meta.get("parties") or {}
    parent_a = parties.get("parent_a", "[Parent A]")
    parent_b = parties.get("parent_b", "[Parent B]")
    case_no = meta.get("case") or "D-000-DM-0000-00000"
    today = date.today().isoformat()

    if doc_type == "schedule_response":
        return f"""# Schedule Response — Draft

**{DISCLOSURE}**

---

{parent_a}
[FACT NEEDED: current mailing address]

{today}

{parent_b}
[FACT NEEDED: {parent_b}'s current mailing address]

**Re:** Case No. {case_no} — Schedule Proposals (Response to Source Letter)

Dear {parent_b},

Thank you for acknowledging my letter. This responds to the schedule items due by the case response deadline.

## Thursday Exchange
[FACT NEEDED: current order's Thursday exchange time] [VERIFY: §V.Q governs weekday exchanges]
Proposed: [FACT NEEDED: specific proposed time, e.g. 3:30pm] — see ATM-001.

## Friday Summer Coverage
[FACT NEEDED: which summer Fridays are at issue] [VERIFY: ATM-002 scope]
Proposed: [UNCERTAIN: coverage plan — confirm with case data before committing]

## Friday School-Day Logistics
Morning drop-off: [FACT NEEDED: current arrangement per order]
Afternoon pickup: [FACT NEEDED: current arrangement per order]
See ATM-003, ATM-004. [VERIFY: school schedule for current year]

## Alternating Tuesdays
[VERIFY: ATM-005, ATM-023 — confirm current Tuesday status before proposing change]
Proposed: [FACT NEEDED: specific ask]

## Summer Vacation
[VERIFY: ATM-019 — summer vacation clause in parenting plan]
Proposed: [FACT NEEDED: dates and logistics]

## Agreement in Writing
All proposed changes subject to written agreement per §VIII and joint legal custody framework.
[VERIFY: §VIII is the correct section for modification process]

Respectfully,

{parent_a}
"""

    if doc_type == "letter_all_other":
        return f"""# Letter Response — All Other Items — Draft

**{DISCLOSURE}**

---

{parent_a}
[FACT NEEDED: current mailing address]

{today}

{parent_b}
[FACT NEEDED: {parent_b}'s current mailing address]

**Re:** Case No. {case_no} — Response to Letter (Non-Schedule Items)

Dear {parent_b},

This letter addresses the non-schedule items from my source letter, due by the case response deadline.

## [FACT NEEDED: section title from atom/issue]
[VERIFY: confirm which atoms fall in non-schedule domain before drafting each section]
[Body — use atom facts only; do not invent amounts, dates, or events]
[UNCERTAIN: flag any claims that cannot be verified against case data]

Respectfully,

{parent_a}
"""

    return f"""# Correspondence — Draft

**{DISCLOSURE}**

---

**Re:** Case No. {case_no}

[FACT NEEDED: subject and purpose of this letter]
[VERIFY: cite only facts present in case atoms or documents]
[UNCERTAIN: mark any assertion you cannot confirm before sending]

{parent_a}
{today}
"""


def _writing_instructions(doc_type: str) -> str:
    base = (
        "Write in plain, professional English. Cite parenting plan sections where relevant. "
        "Use verified facts from the atoms only — do not invent dates, amounts, or events. "
        "Propose specific, actionable schedule language. "
        "End with request for written agreement where appropriate."
    )
    if doc_type == "schedule_response":
        return (
            base
            + " Focus ONLY on schedule/custody logistics for the case response deadline. "
            "Include concrete times (e.g. Thursday exchange 3:30pm). "
            "Reference ATM IDs internally while drafting but do not put atom IDs in the final letter."
        )
    if doc_type == "letter_all_other":
        return base + " Cover financial, compliance, and non-schedule items using the case response deadline."
    return base


def format_draft_context_markdown(ctx: dict) -> str:
    """Human/LLM-readable briefing from draft_context dict."""
    if ctx.get("error"):
        return ctx["error"]

    lines = [
        f"# Draft Context: {ctx.get('title')}",
        "",
        ctx.get("description") or "",
        "",
        f"**Case:** {ctx.get('case_number')} | **Deadline:** {(ctx.get('deadline') or {}).get('date', '—')}",
        "",
    ]

    chrono = ctx.get("chronology")
    if chrono and not chrono.get("error"):
        lines.extend([
            "## Case Chronology (orient before drafting)",
            format_chronology_markdown(chrono),
            "",
        ])

    lines.extend([
        "## Writing Instructions",
        ctx.get("writing_instructions") or "",
        "",
        "## Structure Template",
        ctx.get("structure_template") or "",
        "",
    ])

    if ctx.get("schedule_packet"):
        lines.extend([
            "## Schedule Case Data",
            case_store.format_schedule_response_text(ctx["schedule_packet"]),
            "",
        ])

    atom_ids = ctx.get("atom_ids") or []
    if atom_ids and not ctx.get("schedule_packet"):
        lines.append("## Referenced Atoms")
        for aid in atom_ids[:20]:
            d = case_store.get_atom_detail(aid)
            lines.append(case_store.format_detail_text(d))
            lines.append("\n---\n")

    lines.extend([
        "## After Drafting",
        "Call gazelle_save with the final markdown body. "
        f"Suggested filename: CaseDraft_{ctx.get('doc_type', 'draft')}_{date.today().isoformat()}.md",
    ])
    return "\n".join(lines)


def save_document(
    filename: str,
    body: str,
    *,
    dest: str = "nest",
    subdir: str = DRAFT_DIR_NAME,
) -> dict:
    """Save LLM-produced document. Default: ~/Desktop/Nest/drafts/."""
    body = body.strip()
    if not body:
        return {"error": "Empty document body"}

    fname = _safe_filename(filename)
    if dest == "nest":
        out_dir = NEST / subdir if subdir else NEST
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / fname
    elif dest == "cases":
        out_dir = case_store.CASES_DIR / subdir if subdir else case_store.CASES_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / fname
    else:
        return {"error": f"Unknown dest: {dest}. Use 'nest' or 'cases'."}

    if not body.startswith("#") and "DISCLOSURE" not in body:
        body = f"<!-- {DISCLOSURE} -->\n\n{body}"

    path.write_text(body, encoding="utf-8")
    stat = path.stat()
    return {
        "ok": True,
        "path": str(path),
        "name": fname,
        "size_kb": round(stat.st_size / 1024, 1),
        "modified": date.fromtimestamp(stat.st_mtime).isoformat(),
    }


def list_drafts() -> list[dict]:
    """Generated drafts in Nest drafts/ folder."""
    drafts: list[dict] = []
    for folder in (NEST / DRAFT_DIR_NAME, case_store.CASES_DIR / DRAFT_DIR_NAME):
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*")):
            if path.suffix.lower() not in (".md", ".txt", ".html"):
                continue
            stat = path.stat()
            drafts.append({
                "name": path.name,
                "path": str(path),
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": date.fromtimestamp(stat.st_mtime).isoformat(),
            })
    return drafts


def chronology_builder(case: str = "coparent") -> dict:
    """
    Build a dated event timeline from case data.

    Pulls context_events from the DB plus key meta dates (letter sent, deadlines).
    Significance: 🔴 critical/deadline, 🟡 notable, ⚪ background.
    Gaps are explicitly reported rather than silently omitted.
    """
    events: list[dict] = []
    gaps: list[str] = []

    # ── Context events from DB ────────────────────────────────────────────────
    if case_store.db_exists(case):
        try:
            rows = case_store._query(  # noqa: SLF001
                case,
                "SELECT id, effective_date, event_type, description FROM context_events ORDER BY effective_date",
            )
        except Exception:
            rows = []
            gaps.append(f"{case}.db: context_events table unreadable — DB may need sync")

        if not rows:
            gaps.append(f"{case}.db: context_events is empty — run sync or check Nest")

        _critical_types = {"filing", "order", "violation", "hearing", "judgment"}
        for row in rows:
            sig = "🔴" if row.get("event_type", "").lower() in _critical_types else "🟡"
            events.append({
                "date": row.get("effective_date") or "[VERIFY date]",
                "type": row.get("event_type", "event"),
                "description": row.get("description", ""),
                "source": f"context_events id={row.get('id')}",
                "significance": sig,
                "flags": [] if row.get("effective_date") else ["[VERIFY: date missing in DB]"],
            })
    else:
        gaps.append(f"{case}.db not found — run sync from Nest")

    # ── Key meta dates ────────────────────────────────────────────────────────
    try:
        meta = case_store.load_coparent_meta()
    except Exception:
        meta = {}
        gaps.append("coparent_db_export.json unreadable — meta dates unavailable")

    if meta.get("letter_sent"):
        events.append({
            "date": meta["letter_sent"],
            "type": "letter_sent",
            "description": "Source letter sent to opposing party",
            "source": "coparent_db_export.json _meta.letter_sent",
            "significance": "🔴",
            "flags": [],
        })
    else:
        gaps.append("letter_sent date not in meta — add to coparent_db_export.json _meta")

    deadlines = meta.get("deadlines") or meta.get("response_deadlines") or {}
    for key, dl_date in deadlines.items():
        if dl_date:
            events.append({
                "date": dl_date,
                "type": "deadline",
                "description": f"Response deadline: {key}",
                "source": "coparent_db_export.json _meta.response_deadlines",
                "significance": "🔴",
                "flags": ["[VERIFY: confirm date against letter]"],
            })

    # ── Sort by date (None/missing sorts last) ────────────────────────────────
    events.sort(key=lambda e: (e["date"] or "9999-99-99"))

    return {
        "case": case,
        "generated_at": date.today().isoformat(),
        "event_count": len(events),
        "events": events,
        "gaps": gaps,
        "note": (
            "Entries marked [VERIFY] must be confirmed against source documents "
            "before use in filings. Entries marked [UNCERTAIN] reflect model inference, "
            "not verified facts. Gaps list sources that could not be read."
        ),
    }


def format_chronology_markdown(chrono: dict) -> str:
    """Render chronology_builder output as a markdown table with gap report."""
    if chrono.get("error"):
        return chrono["error"]

    lines = [
        f"# Case Chronology — {chrono.get('case', '').title()}",
        "",
        f"Generated: {chrono.get('generated_at', '—')} · {chrono.get('event_count', 0)} events",
        "",
        "| Date | Sig | Type | Description | Source | Flags |",
        "|------|-----|------|-------------|--------|-------|",
    ]
    for ev in chrono.get("events", []):
        flags = " ".join(ev.get("flags") or [])
        lines.append(
            f"| {ev['date']} | {ev['significance']} | {ev['type']} "
            f"| {ev['description'][:80]} | {ev['source']} | {flags} |"
        )

    gaps = chrono.get("gaps", [])
    if gaps:
        lines.extend(["", "## Gaps (sources not read)", ""])
        for g in gaps:
            lines.append(f"- {g}")

    lines.extend(["", f"> {chrono.get('note', '')}", ""])
    return "\n".join(lines)
