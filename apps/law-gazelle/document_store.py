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
        "description": "Proposed schedule changes in response to Campbell letter (May 30 deadline).",
        "atom_domains": ("schedule",),
        "include_schedule_packet": True,
    },
    "letter_all_other": {
        "title": "Letter Response — All Other Items",
        "deadline_key": "all_other",
        "description": "Response to non-schedule items from Campbell letter (June 6 deadline).",
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
[Your address]

{today}

{parent_b}
[Her address]

**Re:** Case No. {case_no} — Schedule Proposals (Response to Letter of May 23, 2026)

Dear Example Parent B,

Thank you for acknowledging my letter. This responds to the schedule items due **May 30, 2026**.

## Thursday Exchange
[Propose new exchange time — see ATM-001. Reference §V.Q, stipulated order.]

## Friday Summer Coverage
[Address immediate summer Fridays — see ATM-002. Propose concrete coverage plan.]

## Friday School-Day Logistics
[Morning drop-off and afternoon pickup — ATM-003, ATM-004.]

## Alternating Tuesdays
[Clarify status of Tuesday visits/calls — ATM-005, ATM-023.]

## Summer Vacation
[Propose vacation scheduling conversation — ATM-019.]

## Agreement in Writing
[All changes per §VIII / joint legal custody framework.]

Respectfully,

{parent_a}
"""

    if doc_type == "letter_all_other":
        return f"""# Letter Response — All Other Items — Draft

**{DISCLOSURE}**

---

{parent_a}
[Your address]

{today}

{parent_b}

**Re:** Case No. {case_no} — Response to Letter (Non-Schedule Items)

Dear Example Parent B,

This letter addresses the non-schedule items from my letter of May 23, 2026, due **June 6, 2026**.

## [Section per atom/issue]
[Body]

Respectfully,

{parent_a}
"""

    return f"""# Correspondence — Draft

**{DISCLOSURE}**

---

**Re:** Case No. {case_no}

[Body]

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
            + " Focus ONLY on schedule/custody logistics for the May 30 deadline. "
            "Include concrete times (e.g. Thursday exchange 3:30pm). "
            "Reference ATM IDs internally while drafting but do not put atom IDs in the final letter."
        )
    if doc_type == "letter_all_other":
        return base + " Cover financial, compliance, and non-schedule items. Due June 6."
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
        "## Writing Instructions",
        ctx.get("writing_instructions") or "",
        "",
        "## Structure Template",
        ctx.get("structure_template") or "",
        "",
    ]

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
        f"Suggested filename: Campbell_{ctx.get('doc_type', 'draft')}_{date.today().isoformat()}.md",
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
