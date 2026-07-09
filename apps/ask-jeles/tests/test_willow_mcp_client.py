"""willow_mcp_client: launch resolution and the fire-and-forget gap forward.

No real willow-mcp process is spun up here — these tests exercise the pure
resolution logic and confirm forward_gap() is safe (non-blocking, never
raises) when willow-mcp isn't installed, which is the common case for
anyone running AskJeles without the wider fleet set up.
"""

from __future__ import annotations

import time

import pytest

from askjeles import willow_mcp_client as wmc


@pytest.fixture(autouse=True)
def _reset_client_state():
    """ensure_started/forward_gap mutate module-level session state — reset
    it around every test so retry/cooldown behavior isn't order-dependent."""

    def _clear():
        wmc._mcp_session = None
        wmc._mcp_loop = None
        wmc._mcp_stop_event = None
        wmc._mcp_ready = False
        wmc._mcp_error = None
        wmc._last_attempt_at = None

    _clear()
    yield
    _clear()


def test_use_willow_mcp_defaults_on(monkeypatch):
    monkeypatch.delenv("ASK_JELES_USE_WILLOW_MCP", raising=False)
    assert wmc._use_willow_mcp() is True


def test_use_willow_mcp_can_be_disabled(monkeypatch):
    monkeypatch.setenv("ASK_JELES_USE_WILLOW_MCP", "0")
    assert wmc._use_willow_mcp() is False


def test_launch_prefers_explicit_override(monkeypatch):
    monkeypatch.setenv("WILLOW_MCP_CMD", "/custom/venv/bin/python3 -m willow_mcp --serve")
    assert wmc._launch() == ("/custom/venv/bin/python3", ["-m", "willow_mcp", "--serve"])


def test_launch_falls_back_to_path_binary(monkeypatch):
    monkeypatch.delenv("WILLOW_MCP_CMD", raising=False)
    monkeypatch.setattr(wmc.shutil, "which", lambda name: "/usr/local/bin/willow-mcp" if name == "willow-mcp" else None)
    assert wmc._launch() == ("/usr/local/bin/willow-mcp", [])


def test_launch_returns_none_when_nothing_available(monkeypatch):
    monkeypatch.delenv("WILLOW_MCP_CMD", raising=False)
    monkeypatch.setattr(wmc.shutil, "which", lambda name: None)
    # willow_mcp package genuinely isn't installed in this test environment,
    # so the import-fallback branch naturally fails too.
    assert wmc._launch() is None


def test_forward_gap_disabled_is_a_true_noop(monkeypatch):
    monkeypatch.setenv("ASK_JELES_USE_WILLOW_MCP", "0")
    before = time.monotonic()
    wmc.forward_gap("What is the accent color in Nord?")
    assert time.monotonic() - before < 0.05  # no thread spawned at all


def test_forward_gap_does_not_raise_or_block_when_unavailable(monkeypatch):
    monkeypatch.delenv("ASK_JELES_USE_WILLOW_MCP", raising=False)
    monkeypatch.delenv("WILLOW_MCP_CMD", raising=False)
    monkeypatch.setattr(wmc.shutil, "which", lambda name: None)

    before = time.monotonic()
    wmc.forward_gap("What is the accent color in Nord?")
    elapsed = time.monotonic() - before

    # Fire-and-forget: returns near-instantly regardless of whether the
    # background thread has finished resolving "willow-mcp isn't installed".
    assert elapsed < 0.5


def test_ensure_started_retries_after_cooldown(monkeypatch):
    monkeypatch.delenv("WILLOW_MCP_CMD", raising=False)
    monkeypatch.setattr(wmc.shutil, "which", lambda name: None)
    monkeypatch.setattr(wmc, "RETRY_COOLDOWN", 0.05)

    assert wmc.ensure_started(timeout=1) is False
    first_loop = wmc._mcp_loop
    assert first_loop is not None

    # A second call inside the cooldown window must NOT spawn a fresh
    # attempt — a failed connect shouldn't cost a new subprocess/thread on
    # every single forward_gap() call while willow-mcp is still down.
    assert wmc.ensure_started(timeout=1) is False
    assert wmc._mcp_loop is first_loop

    time.sleep(0.1)

    # Past the cooldown, a stale failure must be retried, not cached forever
    # — this is the actual bug being guarded against: "best effort" must not
    # silently become "one effort" for the rest of a long-running session.
    assert wmc.ensure_started(timeout=1) is False
    assert wmc._mcp_loop is not first_loop
