"""Discover and normalize MCP server configs from .mcp.json files."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger("jeles.mcp.registry")

_APP_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _APP_ROOT.parents[1]
_BUILTIN_WILLOW_ID = "builtin-willow"
_BUILTIN_WILLOW_PATH = "__builtin__:willow"


@dataclass(frozen=True)
class McpServerSpec:
    """Metadata for a discovered MCP server (no session started)."""

    server_id: str
    name: str
    config_path: str
    transport: str
    command: str
    args: tuple[str, ...] = ()
    env_keys: tuple[str, ...] = ()
    cwd: str = ""

    @property
    def origin_label(self) -> str:
        if self.config_path == _BUILTIN_WILLOW_PATH:
            return "built-in"
        path = Path(self.config_path)
        if path == _APP_ROOT / ".mcp.json":
            return "ask-jeles"
        if path == _REPO_ROOT / ".mcp.json":
            return "repo"
        try:
            rel = path.relative_to(_REPO_ROOT / "apps")
            return rel.parts[0] if rel.parts else path.parent.name
        except ValueError:
            return path.parent.name or "user"

    @property
    def display_name(self) -> str:
        if self.config_path == _BUILTIN_WILLOW_PATH:
            return "Willow (built-in)"
        return f"{self.name} ({self.origin_label})"

    def summary(self) -> str:
        if self.config_path == _BUILTIN_WILLOW_PATH:
            return "Jeles built-in Willow MCP launcher"
        cmd = self.command
        if self.args:
            cmd = f"{cmd} {' '.join(self.args[:2])}"
            if len(self.args) > 2:
                cmd += " …"
        return cmd[:80]


def _stable_id(config_path: Path, name: str) -> str:
    raw = f"{config_path.resolve()}::{name}".encode()
    return hashlib.sha256(raw).hexdigest()[:12]


def _discovery_paths() -> list[Path]:
    paths: list[Path] = []
    candidates = [
        _APP_ROOT / ".mcp.json",
        _REPO_ROOT / ".mcp.json",
        Path.home() / ".mcp.json",
        Path.home() / ".cursor" / "mcp.json",
    ]
    for p in candidates:
        if p.is_file() and p not in paths:
            paths.append(p)
    apps_dir = _REPO_ROOT / "apps"
    if apps_dir.is_dir():
        for p in sorted(apps_dir.glob("*/.mcp.json")):
            if p not in paths:
                paths.append(p)
    return paths


def _normalize_server(
    name: str,
    raw: dict[str, Any],
    config_path: Path,
) -> McpServerSpec | None:
    if not isinstance(raw, dict):
        return None
    command = str(raw.get("command") or "").strip()
    if not command:
        return None
    args_raw = raw.get("args") or []
    args = tuple(str(a) for a in args_raw) if isinstance(args_raw, list) else ()
    env_raw = raw.get("env") or {}
    env_keys = tuple(sorted(str(k) for k in env_raw.keys())) if isinstance(env_raw, dict) else ()
    transport = str(raw.get("type") or raw.get("transport") or "stdio").strip().lower()
    cwd = str(raw.get("cwd") or "").strip()
    server_id = _stable_id(config_path, name)
    return McpServerSpec(
        server_id=server_id,
        name=name,
        config_path=str(config_path),
        transport=transport,
        command=command,
        args=args,
        env_keys=env_keys,
        cwd=cwd,
    )


def _builtin_willow() -> McpServerSpec | None:
    """Expose the same Willow MCP launcher used by Jeles' built-in client."""
    try:
        from askjeles import mcp_client

        if not mcp_client._use_mcp():
            return None
        command, args = mcp_client._mcp_launch()
        env = mcp_client._mcp_env()
        return McpServerSpec(
            server_id=_BUILTIN_WILLOW_ID,
            name="willow",
            config_path=_BUILTIN_WILLOW_PATH,
            transport="stdio",
            command=command,
            args=tuple(args),
            env_keys=tuple(sorted(env.keys())),
        )
    except Exception as exc:
        log.debug("built-in Willow MCP unavailable: %s", exc)
        return None


def _load_config(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        log.debug("skip MCP config %s: %s", path, exc)
        return {}


def discover_servers() -> list[McpServerSpec]:
    """Return all discovered MCP servers without starting them."""
    seen_ids: set[str] = set()
    servers: list[McpServerSpec] = []
    builtin = _builtin_willow()
    if builtin is not None:
        servers.append(builtin)
        seen_ids.add(builtin.server_id)
    for config_path in _discovery_paths():
        data = _load_config(config_path)
        block = data.get("mcpServers") or data.get("servers") or {}
        if not isinstance(block, dict):
            continue
        for name, raw in block.items():
            spec = _normalize_server(str(name), raw, config_path)
            if spec is None or spec.server_id in seen_ids:
                continue
            seen_ids.add(spec.server_id)
            servers.append(spec)
    def sort_key(spec: McpServerSpec) -> tuple[int, str, str]:
        if spec.config_path == _BUILTIN_WILLOW_PATH:
            return (0, spec.name.lower(), spec.config_path)
        if Path(spec.config_path) == _APP_ROOT / ".mcp.json":
            return (1, spec.name.lower(), spec.config_path)
        if Path(spec.config_path) == _REPO_ROOT / ".mcp.json":
            return (2, spec.name.lower(), spec.config_path)
        return (3, spec.display_name.lower(), spec.config_path)

    return sorted(servers, key=sort_key)


def get_server(server_id: str) -> McpServerSpec | None:
    for spec in discover_servers():
        if spec.server_id == server_id:
            return spec
    return None


def load_server_env(spec: McpServerSpec) -> dict[str, str]:
    """Load env dict for launching a server (internal use only)."""
    if spec.config_path == _BUILTIN_WILLOW_PATH:
        try:
            from askjeles import mcp_client

            return mcp_client._mcp_env()
        except Exception:
            return dict(os.environ)
    data = _load_config(Path(spec.config_path))
    block = data.get("mcpServers") or data.get("servers") or {}
    raw = block.get(spec.name) if isinstance(block, dict) else None
    if not isinstance(raw, dict):
        return {}
    env_raw = raw.get("env") or {}
    if not isinstance(env_raw, dict):
        return {}
    return {str(k): str(v) for k, v in env_raw.items()}


def list_available_servers() -> list[dict[str, Any]]:
    """Public metadata for TUI/API (no env values)."""
    return [
        {
            "server_id": s.server_id,
            "name": s.name,
            "display_name": s.display_name,
            "origin_label": s.origin_label,
            "config_path": s.config_path,
            "transport": s.transport,
            "command_summary": s.summary(),
            "env_keys": list(s.env_keys),
        }
        for s in discover_servers()
    ]
