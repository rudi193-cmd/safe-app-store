"""willow_mcp_client: launch resolution and the fire-and-forget gap forward.

No real willow-mcp process is spun up here — these tests exercise the pure
resolution logic and confirm forward_gap() is safe (non-blocking, never
raises) when willow-mcp isn't installed, which is the common case for
anyone running AskJeles without the wider fleet set up.
"""

from __future__ import annotations

import time

from askjeles import willow_mcp_client as wmc


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
