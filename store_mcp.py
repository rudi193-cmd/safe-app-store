"""MCP stdio client — safe-app-store → Willow app management tools."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any

from mcp_connect import parse_tool_payload

log = logging.getLogger("store.mcp")

APP_ID = "safe-app-store"
_mcp_session = None
_mcp_loop: asyncio.AbstractEventLoop | None = None
_mcp_stop_event: asyncio.Event | None = None
_mcp_ready = False
_mcp_error: str | None = None

_REPO_ROOT = Path(__file__).resolve().parent


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


def _mcp_json_env() -> dict[str, str]:
    mcp_json = _REPO_ROOT / ".mcp.json"
    if not mcp_json.exists():
        return {}
    try:
        data = json.loads(mcp_json.read_text())
        env = data.get("mcpServers", {}).get("willow", {}).get("env", {})
        home = str(Path.home())
        user = os.environ.get("USER", os.environ.get("LOGNAME", ""))
        result: dict[str, str] = {}
        for k, v in env.items():
            if k == "WILLOW_AGENT_NAME":
                continue
            v = v.replace("${HOME}", home).replace("$HOME", home)
            v = v.replace("${USER}", user).replace("$USER", user)
            result[k] = v
        return result
    except Exception:
        return {}


def _mcp_env() -> dict[str, str]:
    root = _willow_root()
    env = dict(os.environ)
    if root:
        env["WILLOW_ROOT"] = str(root)
        env.setdefault("PYTHONPATH", str(root))
    for k, v in _mcp_json_env().items():
        env[k] = v
    env["WILLOW_AGENT_NAME"] = APP_ID
    env["WILLOW_DEV_SAFE_ROOT"] = str(Path.home() / "github")
    env["WILLOW_ALLOW_DEV_GATE"] = "1"
    for k, v in list(env.items()):
        if "$" in str(v):
            env[k] = os.path.expandvars(str(v))
    return env


def _mcp_launch() -> tuple[str, list[str]]:
    root = _willow_root()
    if root and (root / "sap" / "unified_mcp.sh").is_file():
        script = root / "sap" / "unified_mcp.sh"
        err_log = Path.home() / ".willow" / "store-tui.log"
        err_log.parent.mkdir(parents=True, exist_ok=True)
        return "bash", ["-lc", f'exec "{script}" 2>>"{err_log}"']
    py = sys.executable
    return py, ["-m", "sap.unified_mcp"]


def _mcp_call_sync(coro: Any, timeout: float = 90) -> Any:
    assert _mcp_loop is not None
    return asyncio.run_coroutine_threadsafe(coro, _mcp_loop).result(timeout)


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
    global _mcp_loop
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
        name="store-mcp",
    ).start()
    if not ready.wait(timeout=timeout):
        _mcp_error = "MCP server did not initialize in time"
        return False
    return _mcp_ready


def call_tool(name: str, inputs: dict[str, Any], timeout: float = 60) -> Any:
    if not ensure_started():
        raise RuntimeError(_mcp_error or "MCP unavailable")
    assert _mcp_session is not None
    payload = {"app_id": APP_ID, **inputs}
    result = _mcp_call_sync(_mcp_session.call_tool(name, payload), timeout)
    return parse_tool_payload(result)


def app_list() -> list[dict]:
    result = call_tool("app_list", {})
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return result.get("apps", [])
    return []


def app_install(target_app_id: str, source: str = "monorepo") -> Any:
    return call_tool(
        "app_install",
        {"target_app_id": target_app_id, "source": source},
        timeout=90,
    )


def app_uninstall(target_app_id: str) -> Any:
    return call_tool("app_uninstall", {"target_app_id": target_app_id}, timeout=30)


def app_status_check(target_app_id: str) -> Any:
    return call_tool("app_status", {"target_app_id": target_app_id}, timeout=30)


def shutdown() -> None:
    if _mcp_stop_event is not None and _mcp_loop is not None:
        _mcp_loop.call_soon_threadsafe(_mcp_stop_event.set)
