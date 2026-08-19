"""mcp-connect: thin MCP stdio client library.

Discover servers from .mcp.json, connect via stdio, call tools.
"""

from mcp_connect.registry import (
    McpServerSpec,
    add_search_paths,
    discover_servers,
    get_server,
    get_server_by_name,
    list_available_servers,
    load_server_env,
)
from mcp_connect.client import (
    ServerSession,
    call_tool,
    connect_server,
    connected_servers,
    disconnect_server,
    list_server_resources,
    list_server_tools,
    parse_tool_payload,
    shutdown_all,
)

__all__ = [
    "McpServerSpec",
    "ServerSession",
    "add_search_paths",
    "call_tool",
    "connect_server",
    "connected_servers",
    "disconnect_server",
    "discover_servers",
    "get_server",
    "get_server_by_name",
    "list_available_servers",
    "list_server_resources",
    "list_server_tools",
    "load_server_env",
    "parse_tool_payload",
    "shutdown_all",
]
