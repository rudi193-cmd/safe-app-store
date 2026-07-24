"""search_local_kb routing (rule #1): the MCP path is authoritative when the
Willow server is reachable; the direct 80-DB SOIL scan runs ONLY when MCP is
unreachable, and can be disabled entirely.

We monkeypatch the two private backends so no MCP server or store.db is needed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from askjeles import kb_search  # noqa: E402


def _patch(monkeypatch, *, mcp_result, soil_calls):
    """mcp_result: what _from_mcp returns (list, [], or None). soil_calls: a list
    the fake _from_soil appends to when called (to prove it did / didn't run)."""
    monkeypatch.setattr(kb_search, "_from_mcp", lambda q, limit: mcp_result)

    def fake_soil(q, limit):
        soil_calls.append((q, limit))
        return [{"title": "from-soil", "snippet": "x"}]

    monkeypatch.setattr(kb_search, "_from_soil", fake_soil)


def test_reachable_with_hits_uses_mcp_no_scan(monkeypatch):
    calls = []
    hits = [{"title": "from-mcp", "snippet": "y"}]
    _patch(monkeypatch, mcp_result=hits, soil_calls=calls)
    out = kb_search.search_local_kb("medicare", limit=8)
    assert out == hits
    assert calls == []  # direct DB scan never touched


def test_reachable_but_empty_does_NOT_scan_db(monkeypatch):
    # The rule-#1 fix: MCP reachable + empty is authoritative -> no soil scan.
    calls = []
    _patch(monkeypatch, mcp_result=[], soil_calls=calls)
    monkeypatch.delenv("ASKJELES_NO_SOIL_SCAN", raising=False)
    out = kb_search.search_local_kb("nothing-here", limit=8)
    assert out == []
    assert calls == []  # <-- previously this silently scanned 80 store.db files


def test_unreachable_falls_back_to_soil(monkeypatch):
    calls = []
    _patch(monkeypatch, mcp_result=None, soil_calls=calls)  # None = unreachable
    monkeypatch.delenv("ASKJELES_NO_SOIL_SCAN", raising=False)
    out = kb_search.search_local_kb("medicare", limit=8)
    assert out == [{"title": "from-soil", "snippet": "x"}]
    assert calls == [("medicare", 8)]  # offline fallback ran


def test_unreachable_but_scan_disabled_returns_empty(monkeypatch):
    calls = []
    _patch(monkeypatch, mcp_result=None, soil_calls=calls)
    monkeypatch.setenv("ASKJELES_NO_SOIL_SCAN", "1")
    out = kb_search.search_local_kb("medicare", limit=8)
    assert out == []
    assert calls == []  # hard off-switch forbids any direct DB read


def test_blank_query_short_circuits(monkeypatch):
    calls = []
    _patch(monkeypatch, mcp_result=None, soil_calls=calls)
    assert kb_search.search_local_kb("   ", limit=8) == []
    assert calls == []
