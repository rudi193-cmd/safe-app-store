"""Topic trivia helpers reject website-centric leakage."""

from __future__ import annotations

from askjeles.trivia import _fallback_topic_brief, _scrub_search_surface


def test_scrub_removes_commercial_artifacts():
    raw = "Shop at vespa.com for used bikes and financing at dealer prices"
    cleaned = _scrub_search_surface(raw)
    assert "vespa.com" not in cleaned.lower()
    assert "dealer" not in cleaned.lower() or "financing" not in cleaned.lower()


def test_fallback_brief_topic_not_hostnames():
    hits = [
        {
            "title": "Vespa Official Store",
            "snippet": "Shop new Vespa scooters, find a dealer, view inventory, prices, financing.",
        },
        {
            "title": "Vespa Primavera",
            "snippet": (
                "Vespa is a classic Italian scooter brand by Piaggio, known for step-through "
                "design, enclosed engine bodywork, and urban mobility."
            ),
        },
    ]
    brief = _fallback_topic_brief("Vespa scooters", hits)
    assert "vespa.com" not in brief.lower()
    assert "dealer" not in brief.lower()
    assert "piaggio" in brief.lower() or "scooter" in brief.lower()
