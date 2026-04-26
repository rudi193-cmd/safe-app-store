"""
Public Ledger — FastAPI Crown
==============================
Government budget auditor. Follows the money.
Port 8422.
"""

import argparse
import json
import sys
import threading
import uuid

from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .models import AuditClaim
from .engine import audit_claim, audit_batch
from .formatters import format_single_result, format_batch_summary
from .sources import propublica, usaspending, paperclip
from . import cache

from .personas import get_persona

app = FastAPI(
    title="Public Ledger",
    description="Public records financial auditor — follows the money.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Batch state
_batch_lock = threading.Lock()
_batch_status = {"running": False, "total": 0, "done": 0, "results": []}


# --- Pydantic models for request bodies ---

class AuditRequest(BaseModel):
    text: str
    claim_type: str
    entities: list[str] = []
    amount_claimed: float | None = None
    currency: str = "USD"
    time_period: str | None = None
    source_report: str = ""

class BatchAuditRequest(BaseModel):
    claims: list[AuditRequest]

class NonprofitSearchRequest(BaseModel):
    q: str

class SpendingSearchRequest(BaseModel):
    recipient: str
    start_year: int | None = None
    end_year: int | None = None

class PaperclipSearchRequest(BaseModel):
    name: str | None = None
    employer: str | None = None
    field: str | None = None
    generation: int | None = None


# --- Routes ---

@app.get("/")
def root():
    return {
        "service": "Public Ledger",
        "version": "1.0.0",
        "persona": "Ledger",
        "intro": get_persona("Ledger").strip()[:200] + "...",
        "endpoints": [
            "POST /audit", "POST /audit-batch", "GET /status",
            "GET /sources", "POST /search/nonprofit",
            "POST /search/spending", "POST /search/paperclip",
        ],
    }


@app.get("/sources")
def check_sources():
    """Reachability check for all data sources."""
    results = {}

    # ProPublica
    try:
        propublica.search_nonprofit("test")
        results["propublica"] = {"reachable": True, "note": "ProPublica Nonprofit Explorer (IRS 990s)"}
    except Exception:
        results["propublica"] = {"reachable": False}

    # USAspending
    try:
        usaspending.search_awards("test", limit=1)
        results["usaspending"] = {"reachable": True, "note": "USAspending.gov (federal contracts)"}
    except Exception:
        results["usaspending"] = {"reachable": False}

    # Paperclip DB
    try:
        with paperclip.PaperclipReader() as reader:
            stats = reader.stats()
            results["paperclip_cube"] = {
                "reachable": True,
                "note": "Operation Paperclip genealogy DB (read-only)",
                "stats": stats,
            }
    except Exception:
        results["paperclip_cube"] = {"reachable": False}

    # ONS (static)
    results["ons_uk"] = {
        "reachable": True,
        "note": "UK ONS wealth data (static citations, no live API)",
    }

    results["cache"] = cache.stats()

    return results


@app.post("/audit")
def audit_single(req: AuditRequest):
    """Audit a single claim against public records."""
    claim = AuditClaim(
        claim_id=str(uuid.uuid4())[:8],
        text=req.text,
        claim_type=req.claim_type,
        entities=tuple(req.entities),
        amount_claimed=req.amount_claimed,
        currency=req.currency,
        time_period=req.time_period,
        source_report=req.source_report,
    )
    result = audit_claim(claim)
    return format_single_result(result)


@app.post("/audit-batch")
def audit_batch_endpoint(req: BatchAuditRequest, background_tasks: BackgroundTasks):
    """Batch audit — runs in background."""
    global _batch_status
    with _batch_lock:
        if _batch_status["running"]:
            return {"error": "Batch already running", "status": _batch_status}
        _batch_status = {"running": True, "total": len(req.claims), "done": 0, "results": []}

    claims = [
        AuditClaim(
            claim_id=str(uuid.uuid4())[:8],
            text=c.text,
            claim_type=c.claim_type,
            entities=tuple(c.entities),
            amount_claimed=c.amount_claimed,
            currency=c.currency,
            time_period=c.time_period,
            source_report=c.source_report,
        )
        for c in req.claims
    ]

    def _run():
        global _batch_status
        def progress(done, total, result):
            with _batch_lock:
                _batch_status["done"] = done
                _batch_status["results"].append(format_single_result(result))

        results = audit_batch(claims, progress_callback=progress)
        with _batch_lock:
            _batch_status["running"] = False

    background_tasks.add_task(_run)
    return {"started": True, "count": len(claims)}


@app.get("/status")
def batch_status():
    """Check batch audit progress."""
    with _batch_lock:
        return dict(_batch_status)


@app.post("/search/nonprofit")
def search_nonprofit(req: NonprofitSearchRequest):
    """Direct ProPublica search passthrough."""
    results = propublica.search_nonprofit(req.q)
    return {"query": req.q, "count": len(results), "results": results}


@app.post("/search/spending")
def search_spending(req: SpendingSearchRequest):
    """Direct USAspending search passthrough."""
    results = usaspending.search_awards(
        req.recipient,
        start_year=req.start_year,
        end_year=req.end_year,
    )
    return {"recipient": req.recipient, "count": len(results), "results": results}


@app.delete("/cache")
def clear_cache():
    """Clear the response cache."""
    count = cache.clear()
    return {"cleared": count}


@app.get("/cache")
def cache_stats():
    """Cache stats."""
    return cache.stats()


@app.post("/search/paperclip")
def search_paperclip(req: PaperclipSearchRequest):
    """Direct Paperclip DB search passthrough."""
    try:
        with paperclip.PaperclipReader() as reader:
            results = reader.search_persons(
                name=req.name,
                employer=req.employer,
                field=req.field,
                generation=req.generation,
            )
            return {"count": len(results), "results": results}
    except Exception as e:
        print(f"[paperclip] search error: {e}", file=sys.stderr)
        return {"error": "Paperclip database unavailable", "count": 0, "results": []}


# --- CLI + Entry Point ---

def run():
    """Entry point matching safe-app-manifest.json."""
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8422)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Public Ledger — financial auditor")
    parser.add_argument("--serve", action="store_true", help="Start FastAPI server")
    parser.add_argument("--audit", metavar="TEXT", help="Audit a single claim")
    parser.add_argument("--type", default="nonprofit_funding", help="Claim type")
    parser.add_argument("--entities", nargs="+", default=[], help="Entities to search")
    parser.add_argument("--amount", type=float, default=None, help="Claimed amount")
    args = parser.parse_args()

    if args.audit:
        claim = AuditClaim(
            claim_id="cli-1",
            text=args.audit,
            claim_type=args.type,
            entities=tuple(args.entities),
            amount_claimed=args.amount,
        )
        result = audit_claim(claim)
        print(result.ledger_narrative)
    else:
        run()
