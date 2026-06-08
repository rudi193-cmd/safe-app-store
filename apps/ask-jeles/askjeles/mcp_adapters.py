"""Advisory MCP tool classification stubs."""

from __future__ import annotations

import re
from typing import Any, Literal

ToolKind = Literal["search", "read", "write", "unknown"]

_SEARCH = re.compile(r"\b(search|query|find|lookup|lookup|kb_search|grep|discover)\b", re.I)
_READ = re.compile(r"\b(read|fetch|get|list|resources|load|retrieve|describe|inspect)\b", re.I)
_WRITE = re.compile(
    r"\b(write|create|update|delete|ingest|send|submit|post|put|patch|save|upload|publish|drop)\b",
    re.I,
)


def classify_tool(name: str, description: str = "") -> ToolKind:
    """Advisory classification only — not a security boundary."""
    blob = f"{name} {description}".lower()
    if _WRITE.search(blob):
        return "write"
    if _SEARCH.search(blob):
        return "search"
    if _READ.search(blob):
        return "read"
    return "unknown"


def tool_record(tool: dict[str, Any]) -> dict[str, Any]:
    name = str(tool.get("name") or "")
    desc = str(tool.get("description") or "")
    return {
        "name": name,
        "description": desc[:240],
        "kind": classify_tool(name, desc),
        "input_schema": tool.get("input_schema") or tool.get("inputSchema") or {},
    }


def suggest_search_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = [tool_record(t) for t in tools if classify_tool(str(t.get("name") or ""), str(t.get("description") or "")) == "search"]
    return out[:12]


def default_payload(tool: dict[str, Any], query: str = "") -> dict[str, Any]:
    """Best-effort default JSON payload from schema for confirmation preview."""
    schema = tool.get("input_schema") or tool.get("inputSchema") or {}
    if not isinstance(schema, dict):
        return {"query": query} if query else {}
    props = schema.get("properties") or {}
    if not isinstance(props, dict):
        return {"query": query} if query else {}
    payload: dict[str, Any] = {}
    for key, spec in props.items():
        if not isinstance(spec, dict):
            continue
        if query and key.lower() in {"query", "q", "question", "search", "text", "prompt"}:
            payload[key] = query
        elif spec.get("default") is not None:
            payload[key] = spec["default"]
        elif spec.get("type") == "string":
            payload[key] = query or ""
        elif spec.get("type") == "integer":
            payload[key] = 5
        elif spec.get("type") == "boolean":
            payload[key] = False
        elif spec.get("type") == "array":
            payload[key] = []
        elif spec.get("type") == "object":
            payload[key] = {}
    if query and not payload:
        payload = {"query": query}
    return payload
