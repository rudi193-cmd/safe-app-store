"""
ecf_parser.py — CM/ECF Notification Parser for Law Gazelle
============================================================
Parses court electronic filing notifications (CM/ECF data quality notices,
deficiency notices, procedural notices) into structured action items.

Used by Law Gazelle to ingest legal documents from the Nest pipeline.
"""

import re
import json
import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core.db import get_connection

# ── Detection patterns ───────────────────────────────────────────────────────

ECF_PATTERNS = [
    re.compile(r"(?i)CM/?ECF"),
    re.compile(r"(?i)electronic\s+case\s+filing"),
    re.compile(r"(?i)data\s+quality"),
    re.compile(r"(?i)deficiency\s+notice"),
    re.compile(r"(?i)notice\s+of\s+(filing|hearing|motion|order|appearance|deadline)"),
    re.compile(r"(?i)bankruptcy\s+court"),
    re.compile(r"(?i)united\s+states\s+bankruptcy"),
    re.compile(r"(?i)case\s+(?:no\.?|number|#)\s*\d{2}-\d{4,6}"),
]

CASE_NUMBER_RE = re.compile(r"(?:case\s+(?:no\.?|number|#)\s*|#\s*)([\d]{2}-[\d]{4,6}(?:-\w+)?)", re.IGNORECASE)

DEADLINE_PATTERNS = [
    re.compile(r"(?i)(?:due|deadline|by|before|no\s+later\s+than|on\s+or\s+before)\s*:?\s*(\w+\s+\d{1,2},?\s+\d{4})"),
    re.compile(r"(?i)(?:due|deadline|by|before)\s*:?\s*(\d{1,2}/\d{1,2}/\d{2,4})"),
    re.compile(r"(?i)within\s+(\d+)\s+(?:calendar\s+)?days"),
]

# ── Classification ───────────────────────────────────────────────────────────

DATA_QUALITY_KEYWORDS = [
    "data quality", "incomplete", "missing information", "deficient",
    "correction needed", "update required", "discrepancy", "mismatch",
    "social security", "employer identification", "address verification",
]

PROCEDURAL_KEYWORDS = [
    "hearing", "appearance", "motion", "response due", "objection",
    "meeting of creditors", "341 meeting", "confirmation hearing",
    "plan confirmation", "trustee", "discharge",
]

PAYMENT_KEYWORDS = [
    "filing fee", "payment due", "installment", "fee waiver",
]


def _detect_classification(text: str) -> str:
    lower = text.lower()
    dq = sum(1 for kw in DATA_QUALITY_KEYWORDS if kw in lower)
    proc = sum(1 for kw in PROCEDURAL_KEYWORDS if kw in lower)
    pay = sum(1 for kw in PAYMENT_KEYWORDS if kw in lower)

    if dq >= proc and dq >= pay and dq > 0:
        return "data_quality"
    if proc >= dq and proc >= pay and proc > 0:
        return "procedural"
    if pay > 0:
        return "payment"
    return "informational"


def _detect_action_type(classification: str) -> str:
    return {
        "data_quality": "fix_data",
        "procedural": "respond",
        "payment": "pay",
        "informational": "informational",
    }.get(classification, "informational")


def _extract_deadline(text: str) -> str | None:
    for pattern in DEADLINE_PATTERNS:
        m = pattern.search(text)
        if m:
            raw = m.group(1)
            # Try to parse as a date
            for fmt in ("%B %d, %Y", "%B %d %Y", "%m/%d/%Y", "%m/%d/%y"):
                try:
                    dt = datetime.strptime(raw.strip().rstrip(","), fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue
            # "within N days" pattern
            if raw.isdigit():
                from datetime import timedelta
                dt = datetime.now() + timedelta(days=int(raw))
                return dt.strftime("%Y-%m-%d")
    return None


def _extract_case_number(text: str) -> str | None:
    m = CASE_NUMBER_RE.search(text)
    return m.group(1) if m else None


def _summarize_with_fleet(text: str) -> str:
    """Use fleet LLM to generate a plain-language summary of the notification."""
    try:
        _willow_core = str(Path(__file__).resolve().parent.parent.parent / "Willow" / "core")
        if _willow_core not in sys.path:
            sys.path.insert(0, _willow_core)
        import llm_router
        llm_router.load_keys_from_json()
        resp = llm_router.ask(
            "You are a legal assistant. Summarize this court notification in 2-3 plain sentences. "
            "Focus on: what does the court want, is there a deadline, what action is needed.\n\n"
            + text[:2000],
            preferred_tier="free",
            task_type="text_summarization"
        )
        if resp and resp.content:
            return resp.content.strip()[:500]
    except Exception:
        pass
    return ""


# ── Public API ───────────────────────────────────────────────────────────────

def parse_ecf_notification(text: str, filename: str = "") -> dict:
    """Parse raw text to detect and classify a CM/ECF notification.

    Returns:
        {is_ecf, case_number, notification_type, action_required,
         deadline, summary, classification, action_type}
    """
    # Detection: does this look like a court filing notification?
    matches = sum(1 for p in ECF_PATTERNS if p.search(text))
    is_ecf = matches >= 2 or (matches >= 1 and "ecf" in filename.lower())

    if not is_ecf:
        return {"is_ecf": False}

    case_number = _extract_case_number(text)
    classification = _detect_classification(text)
    action_type = _detect_action_type(classification)
    deadline = _extract_deadline(text)
    action_required = classification != "informational"

    # Generate summary — try fleet, fall back to first 200 chars
    summary = _summarize_with_fleet(text)
    if not summary:
        summary = text[:200].strip().replace("\n", " ")

    return {
        "is_ecf": True,
        "case_number": case_number,
        "notification_type": classification,
        "action_required": action_required,
        "action_type": action_type,
        "deadline": deadline,
        "summary": summary,
        "classification": classification,
    }


def ingest_ecf_document(username: str, case_id: int, text: str,
                         filename: str = "", nest_queue_id: int = None) -> dict:
    """Parse a CM/ECF notification and create case document + deadline entries.

    Returns: {document_id, deadline_id, parsed}
    """
    parsed = parse_ecf_notification(text, filename)
    now = datetime.now().isoformat()
    conn = get_connection()

    # Create case document
    cur = conn.execute(
        "INSERT INTO sweet_pea_rudi19.gazelle_case_documents "
        "(case_id, username, doc_type, title, source, source_file, content_text, "
        "parsed_summary, action_required, action_type, deadline, status, "
        "nest_queue_id, created_at, updated_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (case_id, username,
         "ecf_notification" if parsed.get("is_ecf") else "legal_document",
         filename or f"Document ingested {now[:10]}",
         "nest_intake", filename, text[:10000],
         parsed.get("summary", ""),
         1 if parsed.get("action_required") else 0,
         parsed.get("action_type", "informational"),
         parsed.get("deadline"),
         "unreviewed",
         nest_queue_id,
         now, now)
    )
    doc_row = cur.fetchone()
    doc_id = doc_row[0] if doc_row else None
    conn.commit()

    # Create deadline if one was extracted
    deadline_id = None
    if parsed.get("deadline") and doc_id:
        cur2 = conn.execute(
            "INSERT INTO sweet_pea_rudi19.gazelle_deadlines "
            "(case_id, document_id, username, title, deadline_date, status, priority, "
            "notes, created_at, updated_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (case_id, doc_id, username,
             f"Respond to: {filename or 'court notification'}",
             parsed["deadline"], "pending",
             "urgent" if parsed.get("action_type") in ("respond", "pay") else "normal",
             parsed.get("summary", "")[:200],
             now, now)
        )
        dl_row = cur2.fetchone()
        deadline_id = dl_row[0] if dl_row else None
        conn.commit()

    conn.close()
    return {"document_id": doc_id, "deadline_id": deadline_id, "parsed": parsed}
