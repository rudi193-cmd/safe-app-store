# askjeles/crown.py
"""
AskJeles — FastAPI service + CLI for Jeles, your AI librarian.

Endpoints:
  GET  /             — Jeles persona intro
  POST /verify       — Verify a single entity by name
  POST /verify-graph — Batch-verify the Willow knowledge graph (background)
  GET  /status       — Current batch status

CLI:
  python -m askjeles.crown --batch [--limit N] [--dry-run]
  python -m askjeles.crown --verify NAME [--type TYPE]
  python -m askjeles.crown --serve
"""

import argparse
import dataclasses
import importlib
import os
import sys
import threading
import time
from typing import Optional

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from askjeles.leaf import search_verified
from askjeles.prism import VerificationResult, verify_batch, verify_entity

# Persona import — graceful fallback if not installed alongside
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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
def root() -> dict:
    """Jeles introduction and service status."""
    description = get_persona("Jeles")[:200]
    return {
        "name": "Jeles",
        "role": "The Librarian",
        "description": description,
        "status": "ready",
    }


@app.post("/verify")
async def verify_single(request: Request) -> dict:
    """
    Verify a single entity by name.

    Body: {"name": "...", "type": "..."}  (type is optional)
    Returns a VerificationResult as a dict.
    """
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
    """
    Start a background batch verification of the Willow knowledge graph.

    Query params:
      limit    — max entities to process
      dry_run  — if true, skip writing results back to Willow
    """
    with _batch_lock:
        if _batch_status["running"]:
            return {"error": "batch already running"}
        _batch_status["summary"] = None

    background_tasks.add_task(_run_batch, limit, dry_run)
    return {"started": True, "dry_run": dry_run, "limit": limit}


def _run_batch(limit: int, dry_run: bool) -> None:
    """Background worker that calls verify_batch and updates _batch_status."""
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
    """Return current batch verification status."""
    with _batch_lock:
        return dict(_batch_status)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AskJeles — Jeles AI librarian CLI"
    )
    parser.add_argument("--batch", action="store_true", help="Run batch entity verification")
    parser.add_argument("--verify", metavar="NAME", help="Verify a single entity by name")
    parser.add_argument("--type", metavar="TYPE", default="", help="Entity type for --verify")
    parser.add_argument("--limit", metavar="N", type=int, default=None, help="Limit for batch verification")
    parser.add_argument("--dry-run", action="store_true", help="Dry run (do not write results to Willow)")
    parser.add_argument("--willow-url", metavar="URL", default=None, help="Override WILLOW_URL")
    parser.add_argument("--serve", action="store_true", help="Start the FastAPI server on port 8421")
    args = parser.parse_args()

    if args.willow_url:
        os.environ["WILLOW_URL"] = args.willow_url

    if args.batch:
        willow = os.environ.get("WILLOW_URL", "http://localhost:8420")
        summary = verify_batch(willow, limit=args.limit, dry_run=args.dry_run)
        print(summary)
        sys.exit(0)

    if args.verify:
        entity = {
            "id": 0,
            "name": args.verify,
            "type": args.type,
            "description": "",
            "mentions": 0,
        }
        result = verify_entity(entity)
        print(dataclasses.asdict(result))
        sys.exit(0)

    # Default: serve
    uvicorn.run(app, host="127.0.0.1", port=8421)
