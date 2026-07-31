"""plan.py — the seam's plan schema (D3).

A plan is the only thing that crosses from a build's sandbox to the store
side (docs/design/the-forge.md D3). It is data, never code — this module
represents one and checks it's well-formed and in-scope. It does NOT decide
whether a plan is *allowed*: D4's signature check, D5's per-server
allowlist, and D3's pre-crossing AST scan are separate, later stages that
run against a plan that already passed the checks here. A malformed or
out-of-scope plan should never even reach them.

Two plan-entry kinds, matching D3's diagram:
  FileWrite  — stage a file for a path inside the builder's own apps/ tree.
  McpCall    — stage a tool call against a registered MCP server. Staging a
               call is not executing it; D5's allowlist decides that later.

Path-containment here follows the same shape as `tools/seam_install.py`'s
`seam_place` (the C6 pattern): resolve the destination, refuse anything that
isn't the allow root or strictly inside it.

`builder_id` is deliberately NOT a field on `Plan` — see `validate_plan`.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path, PurePosixPath
from typing import Any


class PlanError(Exception):
    """A plan (or one entry in it) is malformed or out of scope — refused
    before it's ever handed to a gate."""


@dataclasses.dataclass(frozen=True)
class FileWrite:
    """Write `content` to `dest_path`, relative to this builder's own
    apps/<builder_id>/<app_name>/ root."""

    dest_path: str  # POSIX-relative, e.g. "src/app.py"
    content: str
    executable: bool = False
    kind: str = dataclasses.field(default="file_write", init=False)


@dataclasses.dataclass(frozen=True)
class McpCall:
    """A staged request to call `tool` on `server`. Recorded, not executed —
    D5's connector decides later whether `tool` is on `server`'s allowlist."""

    server: str
    tool: str
    args: dict[str, Any] = dataclasses.field(default_factory=dict)
    kind: str = dataclasses.field(default="mcp_call", init=False)


PlanEntry = FileWrite | McpCall


@dataclasses.dataclass(frozen=True)
class Plan:
    """Everything one seam decision covers, submitted together.

    No `builder_id` field on purpose. A plan originates inside the sandbox
    — untrusted input — and the seam already knows, from its own trusted
    session/build context, which builder's Kart task produced it. Reading a
    claimed identity back out of the plan and trusting it would be exactly
    the mistake D11 spent a whole fix closing: one indirection from letting
    a compromised build claim to be someone else. `builder_id` is always a
    caller-supplied argument to `validate_plan`, never a field read off
    `plan` — there is nowhere on this dataclass to accidentally trust it
    from.
    """

    app_name: str
    entries: tuple[PlanEntry, ...]

    def __post_init__(self) -> None:
        if not self.app_name or not self.app_name.strip():
            raise PlanError("plan has no app_name")
        if not self.entries:
            raise PlanError("plan has no entries")


# ── (de)serialization — the wire format a plan actually crosses the seam as ──

def entry_from_dict(d: dict[str, Any]) -> PlanEntry:
    kind = d.get("kind")
    if kind == "file_write":
        try:
            return FileWrite(
                dest_path=d["dest_path"],
                content=d["content"],
                executable=bool(d.get("executable", False)),
            )
        except KeyError as e:
            raise PlanError(f"file_write entry missing {e}") from None
    if kind == "mcp_call":
        try:
            return McpCall(server=d["server"], tool=d["tool"], args=dict(d.get("args", {})))
        except KeyError as e:
            raise PlanError(f"mcp_call entry missing {e}") from None
    raise PlanError(f"unknown plan entry kind: {kind!r}")


def plan_from_dict(d: dict[str, Any]) -> Plan:
    if "builder_id" in d:
        # A plan asserting its own builder_id is exactly the shape of input
        # this schema refuses to trust — see Plan's docstring. Reject
        # outright rather than silently dropping the key, so a client
        # sending it finds out immediately, not after a scope check that
        # quietly ignored what it sent.
        raise PlanError(
            "plan payload contains builder_id — a plan may not assert its own "
            "identity; the seam supplies builder_id from its own trusted "
            "session context (see validate_plan)"
        )
    try:
        app_name = d["app_name"]
        raw_entries = d["entries"]
    except KeyError as e:
        raise PlanError(f"plan missing {e}") from None
    entries = tuple(entry_from_dict(e) for e in raw_entries)
    return Plan(app_name=app_name, entries=entries)


def entry_to_dict(entry: PlanEntry) -> dict[str, Any]:
    return dataclasses.asdict(entry)


def plan_to_dict(plan: Plan) -> dict[str, Any]:
    return {"app_name": plan.app_name, "entries": [entry_to_dict(e) for e in plan.entries]}


# ── scope validation — the containment check itself ─────────────────────────

def _contain_file_write(entry: FileWrite, *, builder_id: str, app_name: str, apps_root: Path) -> Path:
    """Resolve `entry.dest_path` against apps/<builder_id>/<app_name>/ and
    refuse anything that would escape it — same shape as
    `tools/seam_install.py`'s `seam_place` containment check, applied to a
    generated file instead of an installer artifact."""
    allow_root = (apps_root / builder_id / app_name).resolve()
    rel = PurePosixPath(entry.dest_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise PlanError(f"seam refused: {entry.dest_path!r} is absolute or escapes its own tree")
    dest = (allow_root / Path(*rel.parts)).resolve()
    if dest != allow_root and not dest.is_relative_to(allow_root):
        raise PlanError(f"seam refused: {dest} escapes allowlist {allow_root}")
    return dest


def validate_plan(plan: Plan, *, builder_id: str, apps_root: Path) -> list[Path]:
    """Structural + scope validation only — NOT the gate (D4) and NOT the
    allowlist (D5). `builder_id` is supplied by the caller (the seam), never
    read from `plan` (see Plan's docstring). Returns the resolved
    destination path for every FileWrite entry; raises PlanError on the
    first entry that's malformed or out of scope."""
    if not builder_id or not builder_id.strip():
        raise PlanError("validate_plan called with no builder_id")
    resolved: list[Path] = []
    for entry in plan.entries:
        if isinstance(entry, FileWrite):
            resolved.append(_contain_file_write(entry, builder_id=builder_id, app_name=plan.app_name, apps_root=apps_root))
        elif isinstance(entry, McpCall):
            if not entry.server.strip() or not entry.tool.strip():
                raise PlanError(f"mcp_call entry missing server/tool: {entry!r}")
        else:
            raise PlanError(f"unknown plan entry type: {type(entry)!r}")
    return resolved
