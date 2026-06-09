"""MCP stdio client — semantic-translator → Willow unified MCP (mem_jeles_* tools)."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any

log = logging.getLogger("semantic_translator.mcp")

APP_ID = "vishwakarma"
_mcp_session = None
_mcp_loop: asyncio.AbstractEventLoop | None = None
_mcp_stop_event: asyncio.Event | None = None
_mcp_ready = False
_mcp_error: str | None = None


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
        return str(Path(os.path.expandvars(explicit)).expanduser())
    # apps/semantic-translator → safe-app-store → ~/github
    return str(Path(__file__).resolve().parents[3])


def _safe_root_stub() -> str:
    stub = Path(_dev_safe_root()) / ".willow-safe-stub"
    stub.mkdir(parents=True, exist_ok=True)
    return str(stub)


def _mcp_json_env() -> dict[str, str]:
    """Load env vars from .mcp.json if present (written by app_install).
    Excludes WILLOW_AGENT_NAME — we always use APP_ID for that."""
    mcp_json = Path(__file__).resolve().parents[1] / ".mcp.json"
    if not mcp_json.exists():
        return {}
    try:
        import json as _json
        data = _json.loads(mcp_json.read_text())
        env = data.get("mcpServers", {}).get("willow", {}).get("env", {})
        # Expand $HOME / ${HOME} in values
        home = str(Path.home())
        return {
            k: v.replace("${HOME}", home).replace("$HOME", home)
            for k, v in env.items()
            if k != "WILLOW_AGENT_NAME"
        }
    except Exception:
        return {}


def _mcp_env() -> dict[str, str]:
    root = _willow_root()
    env = dict(os.environ)
    if root:
        env["WILLOW_ROOT"] = str(root)
        env.setdefault("PYTHONPATH", str(root))
    # Merge vars from .mcp.json (WILLOW_SAFE_ROOT, WILLOW_PG_DB, WILLOW_GROVE_ROOT)
    for k, v in _mcp_json_env().items():
        env[k] = v
    # These always win
    env["WILLOW_AGENT_NAME"] = APP_ID
    env["WILLOW_DEV_SAFE_ROOT"] = _dev_safe_root()
    env["WILLOW_ALLOW_DEV_GATE"] = "1"
    env.setdefault("WILLOW_SAFE_ROOT", _safe_root_stub())
    env.setdefault("WILLOW_MCP_PROFILE", "standard")
    # Expand any unexpanded shell vars (e.g. WILLOW_PG_USER="${USER}")
    for k, v in list(env.items()):
        if "$" in v:
            env[k] = os.path.expandvars(v)
    return env


def _mcp_launch() -> tuple[str, list[str]]:
    root = _willow_root()
    if root and (root / "sap" / "unified_mcp.sh").is_file():
        script = root / "sap" / "unified_mcp.sh"
        err_log = Path.home() / ".willow" / "semantic-translator.log"
        err_log.parent.mkdir(parents=True, exist_ok=True)
        return "bash", ["-lc", f'exec "{script}" 2>>"{err_log}"']
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
        name="semantic-translator-mcp",
    ).start()
    if not ready.wait(timeout=timeout):
        _mcp_error = "MCP server did not initialize in time"
        return False
    return _mcp_ready


def available() -> bool:
    return ensure_started(timeout=5)


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


def jeles_search(query: str, limit: int = 5) -> Any:
    return call_tool(
        "mem_jeles_search",
        {"query": query, "limit": limit},
        timeout=60,
    )


def jeles_register(jsonl_path: str, session_id: str, file_size: int = 0) -> Any:
    return call_tool(
        "mem_jeles_register",
        {
            "agent": APP_ID,
            "jsonl_path": jsonl_path,
            "session_id": session_id,
            "file_size": file_size,
        },
        timeout=30,
    )


def jeles_extract(
    jsonl_id: str,
    content: str,
    title: str = "",
    domain: str = "education",
    certainty: float = 0.95,
    depth: int = 1,
) -> Any:
    return call_tool(
        "mem_jeles_extract",
        {
            "agent": APP_ID,
            "jsonl_id": jsonl_id,
            "content": content,
            "title": title,
            "domain": domain,
            "certainty": certainty,
            "depth": depth,
        },
        timeout=300,
    )


def shutdown() -> None:
    if _mcp_stop_event is not None and _mcp_loop is not None:
        _mcp_loop.call_soon_threadsafe(_mcp_stop_event.set)
