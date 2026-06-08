"""MCP stdio client — story-timeline → Willow 2.0 unified MCP."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("story-timeline.mcp")

APP_ID = "story-timeline"
_mcp_session = None
_mcp_loop: asyncio.AbstractEventLoop | None = None
_mcp_stop_event: asyncio.Event | None = None
_mcp_ready = False
_mcp_error: str | None = None
_test_override: Callable[[str, dict[str, Any]], Any] | None = None


def _app_root() -> Path:
    return Path(__file__).resolve().parent


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


def _mcp_env() -> dict[str, str]:
    root = _willow_root()
    env = dict(os.environ)
    if root:
        env["WILLOW_ROOT"] = str(root)
        env.setdefault("PYTHONPATH", str(root))
    env["WILLOW_AGENT_NAME"] = APP_ID
    env.setdefault("WILLOW_MCP_PROFILE", "standard")
    env.setdefault("WILLOW_PG_DB", "willow_20")
    return env


def _mcp_launch() -> tuple[str, list[str]]:
    root = _willow_root()
    if root and (root / "sap" / "unified_mcp.sh").is_file():
        script = root / "sap" / "unified_mcp.sh"
        err_log = Path.home() / ".willow" / "story-timeline-mcp.log"
        err_log.parent.mkdir(parents=True, exist_ok=True)
        return "bash", ["-lc", f'exec "{script}" 2>>"{err_log}"']
    return sys.executable, ["-m", "sap.unified_mcp"]


def _mcp_call_sync(coro, timeout: float = 120):
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
    global _mcp_loop, _mcp_error
    if os.environ.get("STORY_TIMELINE_DISABLE_MCP", "").strip() == "1":
        _mcp_error = "MCP disabled by STORY_TIMELINE_DISABLE_MCP"
        return False
    if _test_override is not None:
        return True
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
        name="story-timeline-mcp",
    ).start()
    if not ready.wait(timeout=timeout):
        _mcp_error = "MCP server did not initialize in time"
        return False
    return _mcp_ready


def available() -> bool:
    if os.environ.get("STORY_TIMELINE_DISABLE_MCP", "").strip() == "1":
        return False
    if _test_override is not None:
        return True
    return ensure_started(timeout=5)


def last_error() -> str | None:
    return _mcp_error


def set_test_override(handler: Callable[[str, dict[str, Any]], Any] | None) -> None:
    global _test_override
    _test_override = handler


def reset_for_tests() -> None:
    global _mcp_session, _mcp_loop, _mcp_stop_event, _mcp_ready, _mcp_error, _test_override
    _mcp_session = None
    _mcp_loop = None
    _mcp_stop_event = None
    _mcp_ready = False
    _mcp_error = None
    _test_override = None


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
    if _test_override is not None:
        return _test_override(name, inputs)
    if not ensure_started():
        raise RuntimeError(_mcp_error or "MCP unavailable")
    assert _mcp_session is not None
    payload = {"app_id": APP_ID, **inputs}
    result = _mcp_call_sync(_mcp_session.call_tool(name, payload), timeout=timeout)
    return _parse_tool_payload(result)


def jeles_ask(question: str, *, sources: list[str] | None = None, limit: int = 2) -> dict:
    data = call_tool(
        "mem_jeles_ask",
        {"question": question, "sources": sources or [], "limit": limit},
        timeout=180,
    )
    return data if isinstance(data, dict) else {"answer": str(data)}


def jeles_web_search(query: str, *, limit: int = 3) -> dict:
    data = call_tool(
        "mem_jeles_web_search",
        {"query": query, "sources": [], "limit": limit},
        timeout=120,
    )
    return data if isinstance(data, dict) else {"results": data}


def kb_search(query: str, *, limit: int = 5) -> dict:
    data = call_tool(
        "kb_search",
        {"query": query, "limit": limit, "semantic": True},
        timeout=60,
    )
    return data if isinstance(data, dict) else {"knowledge": []}


def infer_7b(
    task_type: str,
    *,
    content: str = "",
    context: str = "",
    categories: list[str] | None = None,
) -> dict:
    payload: dict[str, Any] = {
        "task_type": task_type,
        "content": content,
        "context": context,
    }
    if categories:
        payload["categories"] = categories
    data = call_tool("infer_7b", payload, timeout=120)
    return data if isinstance(data, dict) else {"raw": data}


def shutdown() -> None:
    if _mcp_stop_event is not None and _mcp_loop is not None:
        _mcp_loop.call_soon_threadsafe(_mcp_stop_event.set)
