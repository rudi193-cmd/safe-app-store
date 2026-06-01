"""General web search — DuckDuckGo HTML + navigational map handoffs."""

from __future__ import annotations

import html
import logging
import re
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests

log = logging.getLogger("jeles.web")

_USER_AGENT = "Mozilla/5.0 (compatible; AskJeles/0.1; +https://github.com/rudi193-cmd/safe-app-ask-jeles)"
_DDG_URL = "https://html.duckduckgo.com/html/"
_LINK_RE = re.compile(
    r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_SNIP_RE = re.compile(
    r'class="result__snippet"[^>]*>(.*?)</(?:a|td|span|div)>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")

# Subset of safe_integration.VERIFIED_SOURCES — hostname suffixes
_TRUSTED_SUFFIXES = (
    "si.edu", "loc.gov", "archive.org", "louvre.fr", "nasa.gov", "nih.gov",
    "unesco.org", "europeana.eu", "metmuseum.org", "vam.ac.uk", "britishmuseum.org",
    "nature.com", "jstor.org", "wikipedia.org", "stanford.edu", "britannica.com",
    "gov", "edu", "museum",
)


def _hostname(url: str) -> str:
    try:
        return urlparse(url).netloc or "web"
    except Exception:
        return "web"


def _strip_tags(text: str) -> str:
    return html.unescape(_TAG_RE.sub("", text or "")).strip()


def _unwrap_ddg(href: str) -> str:
    href = (href or "").strip()
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    if "uddg=" in href:
        try:
            qs = parse_qs(urlparse(href).query)
            if qs.get("uddg"):
                return unquote(qs["uddg"][0])
        except Exception:
            pass
    return href


def _trusted_host(hostname: str) -> bool:
    host = (hostname or "").lower().lstrip("www.")
    if not host:
        return False
    for suffix in _TRUSTED_SUFFIXES:
        if host == suffix or host.endswith("." + suffix) or host.endswith(suffix):
            return True
    return False


def navigational_handoffs(query: str) -> list[dict[str, Any]]:
    """Synthetic map/search URLs for local/navigational queries."""
    q = query.strip()
    if not q:
        return []
    enc = quote_plus(q)
    return [
        {
            "title": f"OpenStreetMap: {q}",
            "url": f"https://www.openstreetmap.org/search?query={enc}",
            "snippet": "Search OpenStreetMap for places matching your query.",
            "source": "OpenStreetMap",
            "source_id": "maps_osm",
            "date": "",
            "hostname": "openstreetmap.org",
        },
        {
            "title": f"Google Maps: {q}",
            "url": f"https://www.google.com/maps/search/{enc}",
            "snippet": "Open Google Maps with this search.",
            "source": "Google Maps",
            "source_id": "maps_google",
            "date": "",
            "hostname": "google.com",
        },
        {
            "title": f"Web search: {q}",
            "url": f"https://duckduckgo.com/?q={enc}",
            "snippet": "Full DuckDuckGo results in your browser.",
            "source": "DuckDuckGo",
            "source_id": "web_ddg",
            "date": "",
            "hostname": "duckduckgo.com",
        },
    ]


def ddg_html_search(query: str, max_results: int = 8) -> list[dict[str, Any]]:
    """Fetch DuckDuckGo HTML results (no API key)."""
    q = query.strip()
    if not q:
        return []
    try:
        resp = requests.post(
            _DDG_URL,
            data={"q": q, "b": "", "kl": "us-en"},
            headers={"User-Agent": _USER_AGENT},
            timeout=12,
        )
        resp.raise_for_status()
    except Exception as exc:
        log.warning("ddg search failed: %s", exc)
        return []

    links = _LINK_RE.findall(resp.text)
    snippets = _SNIP_RE.findall(resp.text)
    hits: list[dict[str, Any]] = []
    for idx, (href, title_html) in enumerate(links[: max_results + 4]):
        url = _unwrap_ddg(href)
        if not url or "duckduckgo.com" in url:
            continue
        title = _strip_tags(title_html) or url
        snippet = _strip_tags(snippets[idx]) if idx < len(snippets) else ""
        host = _hostname(url)
        hits.append(
            {
                "title": title[:200],
                "url": url,
                "snippet": snippet[:400],
                "source": host,
                "source_id": "web",
                "date": "",
                "hostname": host,
            }
        )
        if len(hits) >= max_results:
            break
    return hits


def search_web(
    query: str,
    *,
    max_results: int = 8,
    trusted_only: bool = False,
    include_handoffs: bool = False,
) -> list[dict[str, Any]]:
    """
    General web layer for AskJeles.

    trusted_only: filter to verified-domain suffixes (/api/safe/web mode).
    include_handoffs: prepend map/search URLs (navigational queries).
    """
    hits: list[dict[str, Any]] = []
    if include_handoffs:
        hits.extend(navigational_handoffs(query))

    raw = ddg_html_search(query, max_results=max_results)
    if trusted_only:
        raw = [h for h in raw if _trusted_host(h.get("hostname", ""))]

    seen = {h["url"] for h in hits if h.get("url")}
    for hit in raw:
        url = hit.get("url") or ""
        if url and url not in seen:
            seen.add(url)
            hits.append(hit)
    return hits[: max_results + (3 if include_handoffs else 0)]
