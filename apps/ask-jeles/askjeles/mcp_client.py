"""MCP stdio client — AskJeles → Willow unified MCP (mem_jeles_* tools)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any

log = logging.getLogger("jeles.mcp")

APP_ID = "ask-jeles"
_mcp_session = None
_mcp_loop: asyncio.AbstractEventLoop | None = None
_mcp_stop_event: asyncio.Event | None = None
_mcp_ready = False
_mcp_error: str | None = None


def _use_mcp() -> bool:
    return os.environ.get("ASK_JELES_USE_MCP", "1").strip().lower() not in ("0", "false", "no")


def _willow_root() -> Path | None:
    env = os.environ.get("WILLOW_ROOT", "").strip()
    if env:
        p = Path(env).expanduser()
        if (p / "sap" / "unified_mcp.sh").is_file():
            return p
    for candidate in (
        Path.home() / "github" / "willow-2.0",
        Path.home() / "willow-2.0",
    ):
        if (candidate / "sap" / "unified_mcp.sh").is_file():
            return candidate
    return None


def _dev_safe_root() -> str:
    explicit = os.environ.get("WILLOW_DEV_SAFE_ROOT", "").strip()
    if explicit:
        return explicit
    # apps/ask-jeles → safe-app-store/apps
    apps_dir = Path(__file__).resolve().parents[1].parent
    return str(apps_dir)


def _safe_root_stub() -> str:
    """Empty SAFE root so gate falls through to WILLOW_DEV_SAFE_ROOT (no PGP)."""
    stub = Path(_dev_safe_root()) / ".willow-safe-stub"
    stub.mkdir(parents=True, exist_ok=True)
    return str(stub)


def _mcp_env() -> dict[str, str]:
    root = _willow_root()
    env = dict(os.environ)
    if root:
        env["WILLOW_ROOT"] = str(root)
        env.setdefault("PYTHONPATH", str(root))
    env["WILLOW_AGENT_NAME"] = "ask-jeles"
    env["WILLOW_DEV_SAFE_ROOT"] = _dev_safe_root()
    env["WILLOW_SAFE_ROOT"] = _safe_root_stub()
    env.setdefault("WILLOW_MCP_PROFILE", "standard")
    return env


def _mcp_launch() -> tuple[str, list[str]]:
    root = _willow_root()
    if root and (root / "sap" / "unified_mcp.sh").is_file():
        script = root / "sap" / "unified_mcp.sh"
        err_log = Path.home() / ".willow" / "jeles.log"
        err_log.parent.mkdir(parents=True, exist_ok=True)
        # MCP uses stdout for JSON-RPC; redirect only stderr so Willow logs do
        # not paint over the Textual screen while a search is running.
        return "bash", ["-lc", f'exec "{script}" 2>>"{err_log}"']
    # Fallback: python module (requires venv on PATH)
    py = sys.executable
    return py, ["-m", "sap.unified_mcp"]


def _mcp_call_sync(coro, timeout: float = 90):
    assert _mcp_loop is not None
    return asyncio.run_coroutine_threadsafe(coro, _mcp_loop).result(timeout=timeout)


async def _lifecycle(ready: threading.Event) -> None:
    global _mcp_session, _mcp_stop_event, _mcp_ready, _mcp_error
    try:
        from mcp.client.stdio import StdioServerParameters, stdio_client
        from mcp import ClientSession
    except ImportError as exc:
        _mcp_error = f"mcp package missing: {exc}"
        ready.set()
        return

    command, args = _mcp_launch()
    params = StdioServerParameters(command=command, args=args, env=_mcp_env())
    stop = asyncio.Event()
    _mcp_stop_event = stop

    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                _mcp_session = session
                _mcp_ready = True
                ready.set()
                await stop.wait()
    except Exception as exc:
        _mcp_error = str(exc)
        log.exception("MCP lifecycle failed")
        ready.set()


def ensure_started(timeout: float = 45) -> bool:
    """Lazy-start MCP session. Returns True when ready."""
    global _mcp_loop
    if not _use_mcp():
        return False
    if _mcp_ready and _mcp_session is not None:
        return True
    if _mcp_loop is not None:
        return _mcp_ready

    loop = asyncio.new_event_loop()
    _mcp_loop = loop
    ready = threading.Event()
    threading.Thread(
        target=lambda: loop.run_until_complete(_lifecycle(ready)),
        daemon=True,
        name="ask-jeles-mcp",
    ).start()
    if not ready.wait(timeout=timeout):
        _mcp_error = "MCP server did not initialize in time"
        return False
    return _mcp_ready


def available() -> bool:
    return _use_mcp() and ensure_started(timeout=5)


def last_error() -> str | None:
    return _mcp_error


def _parse_tool_payload(result: Any) -> Any:
    if result.isError:
        parts = [getattr(c, "text", str(c)) for c in (result.content or [])]
        raise RuntimeError("; ".join(parts) or "MCP tool error")
    for block in result.content or []:
        text = getattr(block, "text", None)
        if not text:
            continue
        text = text.strip()
        if text.startswith("{") or text.startswith("["):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        return text
    return {}


def call_tool(name: str, inputs: dict[str, Any], timeout: float = 120) -> Any:
    if not ensure_started():
        raise RuntimeError(_mcp_error or "MCP unavailable")
    assert _mcp_session is not None
    payload = {"app_id": APP_ID, **inputs}
    result = _mcp_call_sync(_mcp_session.call_tool(name, payload), timeout=timeout)
    return _parse_tool_payload(result)


def jeles_web_search(
    query: str,
    sources: list[str] | None = None,
    limit: int = 4,
) -> dict[str, Any]:
    src = list(sources or [])
    return call_tool(
        "mem_jeles_web_search",
        {"query": query, "sources": src, "limit": limit},
        timeout=120,
    )


def jeles_ask(
    question: str,
    sources: list[str] | None = None,
    limit: int = 2,
) -> dict[str, Any]:
    return call_tool(
        "mem_jeles_ask",
        {"question": question, "sources": list(sources or []), "limit": limit},
        timeout=120,
    )


def kb_search(
    query: str,
    limit: int = 8,
    *,
    semantic: bool = False,
    tier: str = "",
) -> dict[str, Any]:
    """Search Willow's own knowledge base through MCP."""
    return call_tool(
        "kb_search",
        {"query": query, "limit": limit, "semantic": semantic, "tier": tier},
        timeout=45,
    )


def shutdown() -> None:
    if _mcp_stop_event is not None and _mcp_loop is not None:
        _mcp_loop.call_soon_threadsafe(_mcp_stop_event.set)
