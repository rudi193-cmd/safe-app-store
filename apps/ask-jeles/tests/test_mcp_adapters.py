"""MCP tool classification stubs."""

from __future__ import annotations

from askjeles.mcp_adapters import classify_tool, suggest_search_tools


def test_classify_search():
    assert classify_tool("kb_search", "Search knowledge base") == "search"
    assert classify_tool("willow_knowledge_ingest", "Ingest atom") == "write"
    assert classify_tool("read_file", "Read a resource") == "read"


def test_suggest_search_tools():
    tools = [
        {"name": "web_search", "description": "Search the web"},
        {"name": "read_doc", "description": "Read document"},
    ]
    out = suggest_search_tools(tools)
    assert len(out) == 1
    assert out[0]["name"] == "web_search"
