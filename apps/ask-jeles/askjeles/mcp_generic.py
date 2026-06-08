"""Generic per-server MCP stdio sessions (opt-in, session-scoped)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any

from askjeles.mcp_registry import McpServerSpec, get_server, load_server_env

log = logging.getLogger("jeles.mcp.generic")


@dataclass
class ServerSession:
    spec: McpServerSpec
    loop: asyncio.AbstractEventLoop
    thread: threading.Thread
    session: Any = None
    stop_event: asyncio.Event | None = None
    ready: bool = False
    error: str = ""
    tools: list[dict[str, Any]] = field(default_factory=list)
    resources: list[dict[str, Any]] = field(default_factory=list)


_sessions: dict[str, ServerSession] = {}


def _parse_tool_payload(result: Any) -> Any:
    if getattr(result, "isError", False):
        parts = [getattr(c, "text", str(c)) for c in (getattr(result, "content", None) or [])]
        raise RuntimeError("; ".join(parts) or "MCP tool error")
    content = getattr(result, "content", None) or []
    for block in content:
        text = getattr(block, "text", None)
        if not text:
            continue
        text = str(text).strip()
        if text.startswith("{") or text.startswith("["):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        return text
    return {}


def _tool_to_dict(tool: Any) -> dict[str, Any]:
    return {
        "name": getattr(tool, "name", ""),
        "description": getattr(tool, "description", "") or "",
        "input_schema": getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None) or {},
    }


def _resource_to_dict(res: Any) -> dict[str, Any]:
    return {
        "uri": getattr(res, "uri", ""),
        "name": getattr(res, "name", "") or "",
        "description": getattr(res, "description", "") or "",
        "mimeType": getattr(res, "mimeType", "") or getattr(res, "mime_type", "") or "",
    }


async def _lifecycle(spec: McpServerSpec, ready: threading.Event, holder: ServerSession) -> None:
    try:
        from mcp.client.stdio import StdioServerParameters, stdio_client
        from mcp import ClientSession
    except ImportError as exc:
        holder.error = f"mcp package missing: {exc}"
        ready.set()
        return

    env = dict(os.environ)
    env.update(load_server_env(spec))
    params = StdioServerParameters(
        command=spec.command,
        args=list(spec.args),
        env=env,
        cwd=spec.cwd or None,
    )
    stop = asyncio.Event()
    holder.stop_event = stop
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                holder.session = session
                tools_result = await session.list_tools()
                holder.tools = [_tool_to_dict(t) for t in getattr(tools_result, "tools", []) or []]
                try:
                    resources_result = await session.list_resources()
                    holder.resources = [
                        _resource_to_dict(r) for r in getattr(resources_result, "resources", []) or []
                    ]
                except Exception as exc:
                    log.debug("list_resources unavailable for %s: %s", spec.name, exc)
                    holder.resources = []
                holder.ready = True
                ready.set()
                await stop.wait()
    except Exception as exc:
        holder.error = str(exc)
        log.exception("MCP session failed for %s", spec.name)
        ready.set()


def _call_sync(session: ServerSession, coro, timeout: float = 60) -> Any:
    return asyncio.run_coroutine_threadsafe(coro, session.loop).result(timeout=timeout)


def connect_server(server_id: str, timeout: float = 45) -> dict[str, Any]:
    """Opt-in: start a server for the current Jeles session."""
    if server_id in _sessions and _sessions[server_id].ready:
        s = _sessions[server_id]
        return {
            "ok": True,
            "server_id": server_id,
            "name": s.spec.name,
            "tools": len(s.tools),
            "resources": len(s.resources),
        }
    spec = get_server(server_id)
    if spec is None:
        return {"ok": False, "error": "server not found"}
    if spec.transport not in ("stdio", ""):
        return {"ok": False, "error": f"unsupported transport: {spec.transport}"}

    loop = asyncio.new_event_loop()
    holder = ServerSession(spec=spec, loop=loop, thread=threading.Thread(daemon=True))
    ready = threading.Event()
    holder.thread = threading.Thread(
        target=lambda: loop.run_until_complete(_lifecycle(spec, ready, holder)),
        daemon=True,
        name=f"jeles-mcp-{spec.name}",
    )
    holder.thread.start()
    if not ready.wait(timeout=timeout):
        holder.error = "MCP server did not initialize in time"
        return {"ok": False, "error": holder.error}
    if not holder.ready:
        return {"ok": False, "error": holder.error or "MCP initialization failed"}
    _sessions[server_id] = holder
    return {
        "ok": True,
        "server_id": server_id,
        "name": spec.name,
        "tools": len(holder.tools),
        "resources": len(holder.resources),
    }


def disconnect_server(server_id: str) -> None:
    session = _sessions.pop(server_id, None)
    if session and session.stop_event is not None:
        session.loop.call_soon_threadsafe(session.stop_event.set)


def connected_servers() -> list[dict[str, Any]]:
    out = []
    for sid, s in _sessions.items():
        if s.ready:
            out.append(
                {
                    "server_id": sid,
                    "name": s.spec.name,
                    "tools": len(s.tools),
                    "resources": len(s.resources),
                }
            )
    return out


def list_server_tools(server_id: str) -> list[dict[str, Any]]:
    session = _sessions.get(server_id)
    if not session or not session.ready:
        return []
    return list(session.tools)


def list_server_resources(server_id: str) -> list[dict[str, Any]]:
    session = _sessions.get(server_id)
    if not session or not session.ready:
        return []
    return list(session.resources)


def call_tool(server_id: str, tool_name: str, payload: dict[str, Any], timeout: float = 120) -> Any:
    session = _sessions.get(server_id)
    if not session or not session.ready or session.session is None:
        raise RuntimeError("MCP server not connected")
    result = _call_sync(
        session,
        session.session.call_tool(tool_name, payload),
        timeout=timeout,
    )
    return _parse_tool_payload(result)


def call_tool_confirmed(
    server_id: str,
    tool_name: str,
    payload: dict[str, Any],
    *,
    confirmed: bool,
    timeout: float = 120,
) -> dict[str, Any]:
    if not confirmed:
        return {"ok": False, "cancelled": True, "error": "tool call not confirmed"}
    try:
        result = call_tool(server_id, tool_name, payload, timeout=timeout)
        return {"ok": True, "result": result}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def shutdown_all() -> None:
    for sid in list(_sessions.keys()):
        disconnect_server(sid)
