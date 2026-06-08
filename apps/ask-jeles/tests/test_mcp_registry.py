"""MCP registry discovery (no servers started)."""

from __future__ import annotations

from askjeles.mcp_registry import discover_servers, list_available_servers


def test_discover_returns_list():
    servers = discover_servers()
    assert isinstance(servers, list)


def test_list_available_servers_shape():
    rows = list_available_servers()
    for row in rows:
        assert "server_id" in row
        assert "name" in row
        assert "config_path" in row
        assert "command_summary" in row
        assert "env_keys" in row


def test_builtin_willow_first_when_present():
    rows = list_available_servers()
    if not rows:
        return
    first = rows[0]
    if first.get("display_name") == "Willow (built-in)":
        assert first["origin_label"] == "built-in"
