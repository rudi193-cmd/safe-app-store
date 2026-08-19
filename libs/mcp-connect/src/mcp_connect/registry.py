"""Discover and normalize MCP server configs from .mcp.json files."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger("mcp_connect.registry")

_extra_search_paths: list[Path] = []


@dataclass(frozen=True)
class McpServerSpec:
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
        path = Path(self.config_path)
        return path.parent.name or "user"

    @property
    def display_name(self) -> str:
        return f"{self.name} ({self.origin_label})"

    def summary(self) -> str:
        cmd = self.command
        if self.args:
            cmd = f"{cmd} {' '.join(self.args[:2])}"
            if len(self.args) > 2:
                cmd += " …"
        return cmd[:80]


def add_search_paths(*paths: str | Path) -> None:
    """Register additional directories whose .mcp.json should be scanned."""
    for p in paths:
        resolved = Path(p).resolve()
        if resolved not in _extra_search_paths:
            _extra_search_paths.append(resolved)


def _stable_id(config_path: Path, name: str) -> str:
    raw = f"{config_path.resolve()}::{name}".encode()
    return hashlib.sha256(raw).hexdigest()[:12]


def _discovery_paths() -> list[Path]:
    paths: list[Path] = []
    candidates = [
        Path.cwd() / ".mcp.json",
        Path.home() / ".mcp.json",
        Path.home() / ".cursor" / "mcp.json",
    ]
    for extra in _extra_search_paths:
        mcp_file = extra / ".mcp.json" if extra.is_dir() else extra
        if mcp_file not in candidates:
            candidates.insert(0, mcp_file)
    for p in candidates:
        if p.is_file() and p not in paths:
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


def _load_config(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        log.debug("skip MCP config %s: %s", path, exc)
        return {}


def discover_servers() -> list[McpServerSpec]:
    seen_ids: set[str] = set()
    servers: list[McpServerSpec] = []
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
    return sorted(servers, key=lambda s: (s.display_name.lower(), s.config_path))


def get_server(server_id: str) -> McpServerSpec | None:
    for spec in discover_servers():
        if spec.server_id == server_id:
            return spec
    return None


def get_server_by_name(name: str) -> McpServerSpec | None:
    for spec in discover_servers():
        if spec.name == name:
            return spec
    return None


def load_server_env(spec: McpServerSpec) -> dict[str, str]:
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
