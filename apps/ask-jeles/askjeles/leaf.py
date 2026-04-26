# askjeles/leaf.py
"""
Verified source search for AskJeles — Jeles, your AI librarian.
Only returns results from trusted, publicly accessible domains.
"""

import re
import urllib.parse
from typing import Optional

import requests

VERIFIED_SOURCES = [
    "si.edu", "loc.gov", "archive.org", "louvre.fr", "nasa.gov",
    "nih.gov", "unesco.org", "europeana.eu", "metmuseum.org",
    "vam.ac.uk", "britishmuseum.org", "nature.com", "jstor.org", "wikipedia.org"
]

_HEADERS = {"User-Agent": "AskJeles/1.0"}
_TIMEOUT = 10


def _confidence_hint(name: str, result_title: str) -> str:
    """Compare entity name to returned title to produce a confidence hint."""
    name_norm = name.strip().lower()
    title_norm = result_title.strip().lower()
    if name_norm == title_norm:
        return "high"
    # Medium: one is contained in the other, or they share most words
    name_words = set(re.split(r"\W+", name_norm))
    title_words = set(re.split(r"\W+", title_norm))
    overlap = name_words & title_words
    if overlap and len(overlap) / max(len(name_words), 1) >= 0.5:
        return "medium"
    return "low"


def search_wikipedia(name: str) -> Optional[dict]:
    """
    Search the Wikipedia REST API for an entity.

    Strategy:
      1. Try the page/summary endpoint directly (fast path).
      2. On 404, fall back to the opensearch/query API to find the closest title,
         then fetch its summary.

    Returns a dict with keys: title, summary, url, confidence_hint
    or None if nothing is found.
    """
    encoded = urllib.parse.quote(name, safe="")

    # --- Fast path: direct summary ---
    try:
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            title = data.get("title", "")
            return {
                "title": title,
                "summary": data.get("extract", ""),
                "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                "confidence_hint": _confidence_hint(name, title),
            }
    except requests.RequestException:
        pass

    # --- Fallback: search API ---
    try:
        search_url = (
            "https://en.wikipedia.org/w/api.php"
            f"?action=query&list=search&srsearch={encoded}&format=json&srlimit=1"
        )
        search_resp = requests.get(search_url, headers=_HEADERS, timeout=_TIMEOUT)
        if search_resp.status_code != 200:
            return None
        results = search_resp.json().get("query", {}).get("search", [])
        if not results:
            return None

        found_title = results[0]["title"]
        encoded_title = urllib.parse.quote(found_title, safe="")
        summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_title}"
        summary_resp = requests.get(summary_url, headers=_HEADERS, timeout=_TIMEOUT)
        if summary_resp.status_code == 200:
            data = summary_resp.json()
            title = data.get("title", found_title)
            return {
                "title": title,
                "summary": data.get("extract", ""),
                "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                "confidence_hint": _confidence_hint(name, title),
            }
    except requests.RequestException:
        pass

    return None


def search_verified(name: str, entity_type: str = "") -> Optional[dict]:
    """
    Search for an entity across verified sources.

    Currently delegates to Wikipedia (wikipedia.org is in VERIFIED_SOURCES).
    Future expansions can add Smithsonian, Library of Congress, etc.

    Returns a result dict or None if not found.
    """
    return search_wikipedia(name)
