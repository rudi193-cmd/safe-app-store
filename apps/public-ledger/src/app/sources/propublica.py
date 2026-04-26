"""
ProPublica Nonprofit Explorer Client
=====================================
IRS Form 990 data for nonprofits. Free, no auth.
https://projects.propublica.org/nonprofits/api/v2
"""

import threading
import time
import requests
import sys

from ..cache import get as cache_get, put as cache_put

BASE_URL = "https://projects.propublica.org/nonprofits/api/v2"
_CACHE_NS = "propublica"
_CACHE_TTL = 3600  # 1 hour for search, 86400 for filings
_HEADERS = {"User-Agent": "PublicLedger/1.0 (SAFE App)"}
_TIMEOUT = 15
_RATE_LIMIT = 1.0  # seconds between requests
_last_request = 0.0
_throttle_lock = threading.Lock()


def _throttle():
    global _last_request
    with _throttle_lock:
        elapsed = time.time() - _last_request
        if elapsed < _RATE_LIMIT:
            time.sleep(_RATE_LIMIT - elapsed)
        _last_request = time.time()


def search_nonprofit(name):
    """Search nonprofits by name. Returns list of org summaries."""
    cached = cache_get(_CACHE_NS, f"search:{name}")
    if cached is not None:
        return cached
    _throttle()
    try:
        resp = requests.get(
            f"{BASE_URL}/search.json",
            params={"q": name},
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        if not resp.ok:
            print(f"[propublica] search failed: {resp.status_code}", file=sys.stderr)
            return []
        data = resp.json()
        orgs = data.get("organizations", [])
        results = [
            {
                "ein": org.get("ein"),
                "name": org.get("name"),
                "city": org.get("city"),
                "state": org.get("state"),
                "ntee_code": org.get("ntee_code"),
                "total_revenue": org.get("income_amount"),
                "total_assets": org.get("asset_amount"),
            }
            for org in orgs
        ]
        cache_put(_CACHE_NS, f"search:{name}", results, ttl=_CACHE_TTL)
        return results
    except requests.RequestException as e:
        print(f"[propublica] search error: {e}", file=sys.stderr)
        return []


def get_filing(ein):
    """Get full 990 filing data for an organization by EIN."""
    cached = cache_get(_CACHE_NS, f"filing:{ein}")
    if cached is not None:
        return cached
    _throttle()
    try:
        resp = requests.get(
            f"{BASE_URL}/organizations/{ein}.json",
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        if not resp.ok:
            print(f"[propublica] filing fetch failed: {resp.status_code}", file=sys.stderr)
            return None
        data = resp.json()
        org = data.get("organization", {})
        filings = data.get("filings_with_data", [])

        result = {
            "ein": ein,
            "name": org.get("name"),
            "city": org.get("city"),
            "state": org.get("state"),
            "total_revenue": org.get("income_amount"),
            "total_assets": org.get("asset_amount"),
            "filings": [
                {
                    "tax_period": f.get("tax_prd"),
                    "tax_year": f.get("tax_prd_yr"),
                    "total_revenue": f.get("totrevenue"),
                    "total_expenses": f.get("totfuncexpns"),
                    "total_assets_eoy": f.get("totassetsend"),
                    "total_liabilities_eoy": f.get("totliabend"),
                    "grants_paid": f.get("grntstogovt"),
                    "compensation": f.get("compnsatncurrofcrs"),
                    "pdf_url": f.get("pdf_url"),
                }
                for f in filings
            ],
        }
        cache_put(_CACHE_NS, f"filing:{ein}", result, ttl=86400)  # filings: 24h
        return result
    except requests.RequestException as e:
        print(f"[propublica] filing error: {e}", file=sys.stderr)
        return None


def get_recent_revenue(ein, years=5):
    """Get revenue trend for last N years. Returns list of (year, revenue) tuples."""
    filing_data = get_filing(ein)
    if not filing_data:
        return []
    results = []
    for f in filing_data["filings"][:years]:
        year = f.get("tax_year")
        rev = f.get("total_revenue")
        if year and rev is not None:
            results.append({"year": year, "revenue": rev})
    return results
