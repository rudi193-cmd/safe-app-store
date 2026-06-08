# askjeles/prism.py
"""
Entity verification engine for AskJeles.

Fetches unverified entities from Willow, checks them against public sources,
and writes back structured VerificationResult objects.
"""

import json
import os
import sys
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Callable, List, Optional

import requests

from askjeles.leaf import search_verified

WILLOW_URL = os.environ.get("WILLOW_URL", "http://localhost:8420")

VERIFIABLE_TYPES = {
    "organization", "institution", "place", "event", "publication",
    "technology", "concept", "company", "university", "country", "city",
}
SKIP_TYPES = {"person"}  # private by default


@dataclass
class VerificationResult:
    entity_id: int
    name: str
    verified: bool
    confidence: str        # "high" | "medium" | "low" | "conflicting"
    source_type: str       # "public_record" | "oral_history_consented"
    sources: list          # [{url, title, confidence, fetched_at}]
    skipped: bool = False
    skip_reason: str = ""


def classify_entity(name: str, entity_type: str) -> str:
    """
    Determine whether an entity should be verified, skipped as private,
    or skipped as a non-entity (e.g. a file path).

    Returns: "verifiable" | "private" | "skip"
    """
    etype = (entity_type or "").strip().lower()
    if etype in VERIFIABLE_TYPES:
        return "verifiable"
    if etype in SKIP_TYPES:
        return "private"
    # Looks like a file path — skip it
    if "/" in name or (name.count(".") >= 1 and " " not in name):
        return "skip"
    # Unknown type — try anyway
    return "verifiable"


def assess_match(entity_name: str, search_result: dict) -> tuple:
    """
    Map a search_verified() result to (confidence, source_type).

    confidence_hint from search_result:
      "high"   -> ("high",   "public_record")
      "medium" -> ("medium", "public_record")
      "low"    -> ("low",    "public_record")
    """
    hint = search_result.get("confidence_hint", "low")
    return (hint, "public_record")


def verify_entity(entity: dict, use_llm: bool = False) -> VerificationResult:
    """
    Verify a single entity dict {id, name, type, description, mentions}.

    Steps:
      1. Classify the entity.
      2. If private or file-path skip, return a skipped VerificationResult.
      3. Search verified sources.
      4. Build and return VerificationResult.

    use_llm is reserved for future LLM-assisted disambiguation (not implemented).
    """
    entity_id = entity.get("id", 0)
    name = entity.get("name", "")
    etype = entity.get("type", "")

    classification = classify_entity(name, etype)

    if classification == "private":
        return VerificationResult(
            entity_id=entity_id,
            name=name,
            verified=False,
            confidence="low",
            source_type="oral_history_consented",
            sources=[],
            skipped=True,
            skip_reason="entity type is private (person)",
        )

    if classification == "skip":
        return VerificationResult(
            entity_id=entity_id,
            name=name,
            verified=False,
            confidence="low",
            source_type="oral_history_consented",
            sources=[],
            skipped=True,
            skip_reason="looks like a file path or non-entity string",
        )

    # Attempt verification
    search_result = search_verified(name, etype)

    fetched_at = datetime.now(timezone.utc).isoformat()

    if search_result:
        confidence, source_type = assess_match(name, search_result)
        sources = [
            {
                "url": search_result.get("url", ""),
                "title": search_result.get("title", ""),
                "confidence": confidence,
                "fetched_at": fetched_at,
            }
        ]
        return VerificationResult(
            entity_id=entity_id,
            name=name,
            verified=True,
            confidence=confidence,
            source_type=source_type,
            sources=sources,
        )
    else:
        return VerificationResult(
            entity_id=entity_id,
            name=name,
            verified=False,
            confidence="low",
            source_type="oral_history_consented",
            sources=[],
        )


def verify_batch(
    willow_url: str = None,
    limit: int = None,
    dry_run: bool = False,
    throttle: float = 1.0,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """
    Fetch entities from Willow and verify them against public sources.

    Args:
        willow_url:         Base URL of the Willow server (default: WILLOW_URL env var).
        limit:              Max number of entities to process (default: all).
        dry_run:            If True, do not PATCH results back to Willow.
        throttle:           Seconds to sleep between requests (rate limiting).
        progress_callback:  Optional callable(i, total, result) called after each entity.

    Returns:
        {"total": N, "verified": N, "skipped": N, "unverifiable": N, "errors": N}
    """
    base = willow_url or WILLOW_URL
    effective_limit = limit if limit is not None else 9999

    # Fetch entity feed
    try:
        feed_url = f"{base}/api/knowledge/entities/verify-feed?limit={effective_limit}"
        resp = requests.get(feed_url, timeout=30)
        resp.raise_for_status()
        entities = resp.json()
        if not isinstance(entities, list):
            entities = entities.get("entities", [])
    except Exception as exc:
        print(f"[verifier] Failed to fetch entity feed: {exc}", file=sys.stderr)
        return {"total": 0, "verified": 0, "skipped": 0, "unverifiable": 0, "errors": 1}

    total = len(entities)
    counts = {"total": total, "verified": 0, "skipped": 0, "unverifiable": 0, "errors": 0}

    for i, entity in enumerate(entities):
        try:
            result = verify_entity(entity)
        except Exception as exc:
            print(f"[verifier] Error verifying {entity}: {exc}", file=sys.stderr)
            counts["errors"] += 1
            time.sleep(throttle)
            continue

        if result.skipped:
            counts["skipped"] += 1
        elif result.verified:
            counts["verified"] += 1
        else:
            counts["unverifiable"] += 1

        # Write back to Willow unless dry_run
        if not dry_run and not result.skipped:
            try:
                patch_url = f"{base}/api/knowledge/entities/{result.entity_id}/verify"
                requests.patch(patch_url, json=asdict(result), timeout=15)
            except Exception as exc:
                print(f"[verifier] PATCH failed for {result.name}: {exc}", file=sys.stderr)
                counts["errors"] += 1

        if progress_callback:
            progress_callback(i, total, result)

        time.sleep(throttle)

    return counts
