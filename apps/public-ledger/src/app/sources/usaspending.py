"""
USAspending.gov Client
======================
Federal contracts, grants, and awards. Free, no auth.
https://api.usaspending.gov/api/v2
"""

import threading
import time
from datetime import datetime
import requests
import sys

from ..cache import get as cache_get, put as cache_put

BASE_URL = "https://api.usaspending.gov/api/v2"
_CACHE_NS = "usaspending"
_CACHE_TTL = 7200  # 2 hours — federal data updates slowly
_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "PublicLedger/1.0 (SAFE App)",
}
_TIMEOUT = 30
_RATE_LIMIT = 1.0
_last_request = 0.0
_throttle_lock = threading.Lock()


def _throttle():
    global _last_request
    with _throttle_lock:
        elapsed = time.time() - _last_request
        if elapsed < _RATE_LIMIT:
            time.sleep(_RATE_LIMIT - elapsed)
        _last_request = time.time()


def search_awards(recipient_name, start_year=None, end_year=None, award_types=None, limit=10):
    """Search federal awards by recipient name.

    award_types: list of codes. Contracts: ["A","B","C","D"]. Grants: ["02","03","04","05"].
    """
    cache_key = f"awards:{recipient_name}:{start_year}:{end_year}:{award_types}:{limit}"
    cached = cache_get(_CACHE_NS, cache_key)
    if cached is not None:
        return cached
    _throttle()
    filters = {
        "recipient_search_text": [recipient_name],
        "award_type_codes": award_types or ["A", "B", "C", "D"],
    }
    if start_year or end_year:
        filters["time_period"] = [{
            "start_date": f"{start_year or 2000}-10-01",
            "end_date": f"{end_year or datetime.now().year}-09-30",
        }]

    body = {
        "subawards": False,
        "limit": limit,
        "page": 1,
        "filters": filters,
        "fields": [
            "Award ID",
            "Recipient Name",
            "Award Amount",
            "Total Outlays",
            "Awarding Agency",
            "Awarding Sub Agency",
            "Start Date",
            "End Date",
            "Description",
        ],
    }

    try:
        resp = requests.post(
            f"{BASE_URL}/search/spending_by_award/",
            json=body,
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        if not resp.ok:
            print(f"[usaspending] search failed: {resp.status_code}", file=sys.stderr)
            return []
        data = resp.json()
        results = data.get("results", [])
        awards = [
            {
                "award_id": r.get("Award ID"),
                "recipient": r.get("Recipient Name"),
                "amount": r.get("Award Amount"),
                "outlays": r.get("Total Outlays"),
                "agency": r.get("Awarding Agency"),
                "sub_agency": r.get("Awarding Sub Agency"),
                "start_date": r.get("Start Date"),
                "end_date": r.get("End Date"),
                "description": r.get("Description"),
            }
            for r in results
        ]
        cache_put(_CACHE_NS, cache_key, awards, ttl=_CACHE_TTL)
        return awards
    except requests.RequestException as e:
        print(f"[usaspending] search error: {e}", file=sys.stderr)
        return []


def total_awarded(recipient_name, start_year=None, end_year=None):
    """Get total federal dollars awarded to a recipient. Returns (total, count, awards)."""
    awards = search_awards(recipient_name, start_year, end_year, limit=50)
    total = sum(a["amount"] for a in awards if a.get("amount"))
    return {"total": total, "count": len(awards), "awards": awards}
