"""
AskJeles FastAPI service — entity verification API.

Endpoints:
  GET  /             — Jeles persona intro
  POST /verify       — Verify a single entity by name
  POST /verify-graph — Batch-verify the Willow knowledge graph (background)
  GET  /status       — Current batch verification status

Launch: python -m askjeles.serve
"""

import dataclasses
import importlib
import os
import sys
import threading
from typing import Optional

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request

from askjeles.prism import VerificationResult, verify_batch, verify_entity
from askjeles.web_search import search_web

try:
    _personas = importlib.import_module("personas")
    get_persona = _personas.get_persona
except ImportError:
    def get_persona(name: str) -> str:
        return f"{name} — AI librarian. Verified sources only."

WILLOW_URL = os.environ.get("WILLOW_URL", "http://localhost:8420")

app = FastAPI(title="AskJeles", description="Jeles, your AI librarian.")

_batch_status: dict = {"running": False, "total": 0, "done": 0, "summary": None}
_batch_lock = threading.Lock()


@app.get("/")
def root() -> dict:
    description = get_persona("Jeles")[:200]
    return {
        "name": "Jeles",
        "role": "The Librarian",
        "description": description,
        "status": "ready",
    }


@app.post("/verify")
async def verify_single(request: Request) -> dict:
    body = await request.json()
    name = body.get("name")
    if not name or not isinstance(name, str):
        raise HTTPException(status_code=400, detail="'name' is required and must be a string")
    entity = {
        "id": 0,
        "name": name,
        "type": body.get("type", ""),
        "description": "",
        "mentions": 0,
    }
    result = verify_entity(entity)
    return dataclasses.asdict(result)


@app.post("/verify-graph")
async def verify_graph_endpoint(
    background_tasks: BackgroundTasks,
    limit: Optional[int] = None,
    dry_run: bool = False,
) -> dict:
    with _batch_lock:
        if _batch_status["running"]:
            return {"error": "batch already running"}
        _batch_status["summary"] = None

    background_tasks.add_task(_run_batch, limit, dry_run)
    return {"started": True, "dry_run": dry_run, "limit": limit}


def _run_batch(limit: int, dry_run: bool) -> None:
    with _batch_lock:
        _batch_status["running"] = True
        _batch_status["done"] = 0
        _batch_status["total"] = 0

    def progress(i: int, total: int, result: VerificationResult) -> None:
        with _batch_lock:
            _batch_status["total"] = total
            _batch_status["done"] = i + 1
        label = "skip" if result.skipped else result.source_type
        print(
            f"[{i + 1}/{total}] {result.name}: {result.confidence} ({label})",
            file=sys.stderr,
        )

    summary = verify_batch(
        WILLOW_URL,
        limit=limit,
        dry_run=dry_run,
        progress_callback=progress,
    )

    with _batch_lock:
        _batch_status["running"] = False
        _batch_status["summary"] = summary


@app.get("/status")
def status() -> dict:
    with _batch_lock:
        return dict(_batch_status)


@app.get("/api/safe/web")
@app.post("/api/safe/web")
async def safe_web(
    request: Request,
    q: Optional[str] = Query(None, description="Search query"),
    trusted_only: bool = Query(True, description="Filter to verified-domain suffixes"),
    limit: int = Query(8, ge=1, le=20),
) -> dict:
    """
    General web search for AskJeles.

    Default (trusted_only=true): DuckDuckGo results filtered to verified institutions.
    trusted_only=false: full web results plus optional navigational handoffs.
    """
    query = (q or "").strip()
    if not query:
        try:
            body = await request.json()
            query = (body.get("q") or body.get("query") or "").strip()
            if "trusted_only" in body:
                trusted_only = bool(body["trusted_only"])
            if "limit" in body:
                limit = int(body["limit"])
        except Exception:
            pass
    if not query:
        raise HTTPException(status_code=400, detail="'q' or 'query' is required")

    from askjeles.classify import classify

    qclass = classify(query).value
    include_handoffs = qclass == "navigational" and not trusted_only
    hits = search_web(
        query,
        max_results=limit,
        trusted_only=trusted_only,
        include_handoffs=include_handoffs,
    )
    for idx, hit in enumerate(hits, start=1):
        hit["n"] = idx
    return {
        "query": query,
        "query_class": qclass,
        "trusted_only": trusted_only,
        "total": len(hits),
        "hits": hits,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="AskJeles verification API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8421)
    parser.add_argument("--willow-url", metavar="URL", default=None)
    args = parser.parse_args()
    if args.willow_url:
        os.environ["WILLOW_URL"] = args.willow_url
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
