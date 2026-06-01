"""Verify helpers for CLI/TUI paths."""

from __future__ import annotations

from dataclasses import dataclass

from askjeles.crown import _verify_candidate, _verify_result_message


def test_verify_candidate_prefers_selected_hit_title():
    candidate = _verify_candidate({"title": "Vespa", "url": "https://example.invalid"}, "ignored query")
    assert candidate["name"] == "Vespa"
    assert candidate["id"] == 0


def test_verify_candidate_falls_back_to_query():
    candidate = _verify_candidate(None, "Piaggio")
    assert candidate["name"] == "Piaggio"


@dataclass
class FakeResult:
    name: str
    verified: bool
    confidence: str = "high"
    sources: list[dict[str, str]] | None = None
    skipped: bool = False
    skip_reason: str = ""


def test_verify_result_message_verified():
    message, severity = _verify_result_message(
        FakeResult("Vespa", True, sources=[{"title": "Vespa", "url": "https://example.invalid"}])
    )
    assert severity == "information"
    assert "Verified Vespa" in message


def test_verify_result_message_skipped():
    message, severity = _verify_result_message(FakeResult("Ada", False, skipped=True, skip_reason="private"))
    assert severity == "warning"
    assert "private" in message
