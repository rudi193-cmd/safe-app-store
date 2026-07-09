"""Best-effort forwarder from AskJeles' local corpus gaps to willow-mcp's
fleet-wide gap backlog (the gap_log/gap_list/gap_resolve/gap_promote tools).

AskJeles stays fully functional offline: askjeles/corpus.py's local gap log
(WILLOW_STORE_ROOT/ask_jeles_corpus_gaps) is always written first and is the
source of truth for AskJeles itself — that write is synchronous and never
depends on this module. forward_gap() only ever ADDS a copy into willow-mcp's
shared backlog when willow-mcp is installed, reachable, and this app_id is
authorized for gap_write there. It never blocks the caller and never raises
into it — a stalled or missing willow-mcp should be invisible to a user
asking Jeles a question.

Distinct from askjeles/mcp_client.py, which is a *different* built-in client
for willow-2.0's bespoke sap/unified_mcp.sh server (mem_jeles_*, kb_search).
willow-mcp is a separate, standalone, agent-neutral package — see
https://github.com/rudi193-cmd/willow-mcp — invoked here as an ordinary
external MCP server, the same way the generic MCP drawer (mcp_registry.py /
mcp_generic.py) would talk to any other discovered server.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import shutil
import sys
import threading
from typing import Any

log = logging.getLogger("jeles.willow_mcp")

APP_ID = "ask-jeles"
DEFAULT_TOPIC = "ask-jeles-corpus"

_mcp_session = None
_mcp_loop: asyncio.AbstractEventLoop | None = None
_mcp_stop_event: asyncio.Event | None = None
_mcp_ready = False
_mcp_error: str | None = None
_start_lock = threading.Lock()


def _use_willow_mcp() -> bool:
    return os.environ.get("ASK_JELES_USE_WILLOW_MCP", "1").strip().lower() not in ("0", "false", "no")


def _launch() -> tuple[str, list[str]] | None:
    """Resolve how to start willow-mcp, or None if it isn't available.

    Precedence: WILLOW_MCP_CMD (explicit override, shell-split) > a
    `willow-mcp` console script on PATH (the normal pip-installed case) >
    `python -m willow_mcp` against the current interpreter (installed into
    this same venv). No hardcoded personal paths — willow-mcp is a separate
    package that may or may not be installed anywhere in particular.
    """
    override = os.environ.get("WILLOW_MCP_CMD", "").strip()
    if override:
        parts = shlex.split(override)
        if parts:
            return parts[0], parts[1:]

    exe = shutil.which("willow-mcp")
    if exe:
        return exe, []

    try:
        import willow_mcp  # noqa: F401
    except ImportError:
        return None
    return sys.executable, ["-m", "willow_mcp"]


async def _lifecycle(ready: threading.Event) -> None:
    global _mcp_session, _mcp_stop_event, _mcp_ready, _mcp_error
    launch = _launch()
    if launch is None:
        _mcp_error = "willow-mcp not installed (set WILLOW_MCP_CMD, or `pip install willow-mcp`)"
        ready.set()
        return

    try:
        from mcp.client.stdio import StdioServerParameters, stdio_client
        from mcp import ClientSession
    except ImportError as exc:
        _mcp_error = f"mcp package missing: {exc}"
        ready.set()
        return

    command, args = launch
    params = StdioServerParameters(command=command, args=args, env=dict(os.environ))
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
        log.debug("willow-mcp session failed: %s", exc)
        ready.set()


def ensure_started(timeout: float = 5) -> bool:
    """Lazy-start a background willow-mcp session. Short default timeout —
    this is a best-effort forward, not a feature anything blocks on."""
    global _mcp_loop
    if not _use_willow_mcp():
        return False
    if _mcp_ready and _mcp_session is not None:
        return True

    with _start_lock:
        if _mcp_loop is None:
            loop = asyncio.new_event_loop()
            _mcp_loop = loop
            ready = threading.Event()
            threading.Thread(
                target=lambda: loop.run_until_complete(_lifecycle(ready)),
                daemon=True,
                name="ask-jeles-willow-mcp",
            ).start()
            if not ready.wait(timeout=timeout):
                return False
            return _mcp_ready

    return _mcp_ready


def _parse_tool_payload(result: Any) -> Any:
    if getattr(result, "isError", False):
        parts = [getattr(c, "text", str(c)) for c in (getattr(result, "content", None) or [])]
        raise RuntimeError("; ".join(parts) or "willow-mcp tool error")
    for block in getattr(result, "content", None) or []:
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


def call_tool(name: str, inputs: dict[str, Any], timeout: float = 10) -> Any:
    if not ensure_started():
        raise RuntimeError(_mcp_error or "willow-mcp unavailable")
    assert _mcp_loop is not None and _mcp_session is not None
    payload = {"app_id": APP_ID, **inputs}
    coro = _mcp_session.call_tool(name, payload)
    result = asyncio.run_coroutine_threadsafe(coro, _mcp_loop).result(timeout=timeout)
    return _parse_tool_payload(result)


def forward_gap(question: str, topic: str = DEFAULT_TOPIC) -> None:
    """Fire-and-forget: runs in a daemon thread, never blocks the caller,
    never raises. This is the one function the rest of AskJeles should call
    — everything above is plumbing for it."""
    if not _use_willow_mcp():
        return

    def _run() -> None:
        try:
            call_tool("gap_log", {"topic": topic, "question": question})
        except Exception as exc:
            log.debug("gap forward to willow-mcp failed: %s", exc)

    threading.Thread(target=_run, daemon=True, name="ask-jeles-gap-forward").start()


def shutdown() -> None:
    if _mcp_stop_event is not None and _mcp_loop is not None:
        _mcp_loop.call_soon_threadsafe(_mcp_stop_event.set)
