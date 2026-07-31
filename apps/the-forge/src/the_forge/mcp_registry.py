"""mcp_registry.py — D5's capability contract: one explicit allowlist per
registered MCP server.

Default-deny, not shape-classification (the design's own correction,
2026-07-31): a tool is allowed because its name is on a specific server's
allowlist, reviewed at registration time — never inferred at call time from
what a tool's name or schema suggests it does. `nestor.serve.Server`'s
closed tool list (its own `WITHHELD` set refusing seal/unseal/reject/
override/import/edit-ledger by name) is the reference this module copies
the *shape* of, not a dependency — `the_forge` stays import-pure (D13).

A server registered with no allowlist is refused at registration, closing
the exact gap the design doc's Open/next names: "nothing yet stops a server
from being registered without one." There is no such thing as an
empty-allowlist registration here — it's refused outright, not silently
accepted as "allow nothing until told otherwise."

This module is the DECISION only — is `(server, tool)` allowed. The
connector that actually launches a registered server (generalizing
`store_mcp.py`'s stdio pattern) and the code that executes an allowed call
are both later work; `McpRegistry` doesn't do either, on purpose, so the
allowlist decision is testable without any real subprocess or stdio
machinery.
"""
from __future__ import annotations

import dataclasses
from typing import Iterable


class RegistryError(Exception):
    """Registration refused — no allowlist, empty allowlist, or a server
    already registered. Re-registration is not an update; register once."""


@dataclasses.dataclass(frozen=True)
class ServerRegistration:
    name: str
    launch_command: tuple[str, ...]  # argv — generalizes store_mcp.py's stdio launch
    allowed_tools: frozenset[str]


class McpRegistry:
    """In-memory registry of `(server -> allowed tool names)`. Exact-match
    only — no wildcards, no prefix matching, nothing that could be widened
    by a cleverly-named tool. `is_allowed` is the only thing a caller
    outside this module should trust for a decision; `deny_reason` is for
    an error message, not a decision — it's called *after* `is_allowed`
    already said no."""

    def __init__(self) -> None:
        self._servers: dict[str, ServerRegistration] = {}

    def register(self, name: str, *, launch_command: Iterable[str], allowed_tools: Iterable[str]) -> None:
        if name in self._servers:
            raise RegistryError(f"server {name!r} is already registered — re-registration is not an update")
        allowed = frozenset(allowed_tools)
        if not allowed:
            raise RegistryError(
                f"refusing to register server {name!r} with an empty allowlist — "
                f"a server with no allowed tools isn't a registration, it's a no-op "
                f"that looks like one; don't register it at all instead"
            )
        self._servers[name] = ServerRegistration(
            name=name, launch_command=tuple(launch_command), allowed_tools=allowed
        )

    def is_registered(self, server: str) -> bool:
        return server in self._servers

    def is_allowed(self, server: str, tool: str) -> bool:
        reg = self._servers.get(server)
        return reg is not None and tool in reg.allowed_tools

    def deny_reason(self, server: str, tool: str) -> str:
        if server not in self._servers:
            return f"server {server!r} is not registered"
        return f"tool {tool!r} is not on server {server!r}'s allowlist"

    def allowed_tools(self, server: str) -> frozenset[str]:
        reg = self._servers.get(server)
        if reg is None:
            raise RegistryError(f"server {server!r} is not registered")
        return reg.allowed_tools


# `nestor.serve.Server`'s actual closed tool list (docs/design/the-forge.md,
# "Nestor inventory" — code-backed against Nestor's own master, not
# invented). Provided as a constant for convenience; registering it is
# still an explicit caller act, not a module-level side effect.
NESTOR_ALLOWED_TOOLS: frozenset[str] = frozenset({
    "nestor_ask",
    "nestor_resolve",
    "nestor_check",
    "nestor_match",
    "nestor_provenance",
    "nestor_ledger_verify",
    "nestor_propose",
})
