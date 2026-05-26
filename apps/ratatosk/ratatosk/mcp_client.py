"""
mcp_client.py — MCP stdio client for connecting to sap_mcp.py.
b17: 76353  ΔΣ=42
"""
import asyncio
import os
import sys
import threading
from pathlib import Path

_DEFAULT_SAP_MCP = str(
    Path(os.environ.get("RATATOSK_MCP_PATH",
         str(Path.home() / "willow-2.0" / "sap" / "sap_mcp.py")))
)

_mcp_session = None
_mcp_loop: asyncio.AbstractEventLoop | None = None
_mcp_stop_event: asyncio.Event | None = None


def _mcp_call_sync(coro):
    assert _mcp_loop is not None
    return asyncio.run_coroutine_threadsafe(coro, _mcp_loop).result(timeout=30)


async def _lifecycle(sap_mcp: str, ready: threading.Event) -> None:
    global _mcp_session, _mcp_stop_event
    from mcp.client.stdio import stdio_client, StdioServerParameters
    from mcp import ClientSession

    params = StdioServerParameters(command=sys.executable, args=[sap_mcp])
    stop = asyncio.Event()
    _mcp_stop_event = stop

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            _mcp_session = session
            ready.set()
            await stop.wait()


def start(sap_mcp: str = _DEFAULT_SAP_MCP) -> tuple[list[dict], set[str]]:
    """Connect to sap_mcp.py, return (anthropic_tool_defs, tool_name_set)."""
    global _mcp_loop

    loop = asyncio.new_event_loop()
    _mcp_loop = loop
    ready = threading.Event()

    threading.Thread(
        target=lambda: loop.run_until_complete(_lifecycle(sap_mcp, ready)),
        daemon=True,
        name="ratatosk-mcp",
    ).start()

    if not ready.wait(timeout=30):
        raise RuntimeError("MCP server did not initialize within 30s")

    tools_result = _mcp_call_sync(_mcp_session.list_tools())
    anthropic_tools, names = [], set()
    for t in tools_result.tools:
        anthropic_tools.append({
            "name": t.name,
            "description": t.description or "",
            "input_schema": t.inputSchema,
        })
        names.add(t.name)
    return anthropic_tools, names


def call(name: str, inputs: dict) -> str:
    try:
        result = _mcp_call_sync(_mcp_session.call_tool(name, inputs))
        if result.isError:
            return f"[mcp-error] {result.content}"
        parts = [c.text for c in result.content if hasattr(c, "text")]
        return "\n".join(parts) if parts else str(result.content)
    except Exception as e:
        return f"[mcp-error] {e}"


def shutdown() -> None:
    if _mcp_stop_event is not None and _mcp_loop is not None:
        asyncio.run_coroutine_threadsafe(_mcp_stop_event.set(), _mcp_loop)
