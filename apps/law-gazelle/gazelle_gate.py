#!/usr/bin/env python3
"""
gazelle_gate.py — WillowGate enforcement inside the Law Gazelle MCP server.

Wires willow-gate's authorize_tool() as an inline pre-dispatch gate in
gazelle_mcp.py: a denied tools/call never reaches the tool. Identity travels
in-band — the client checks in over MCP with a signed 13-field WillowGate
header, and every subsequent call is authorized against that session.

Enforcement is OFF unless GAZELLE_GATE=1 (back-compat: the TUI and existing
.mcp.json clients are unaffected). When enabled but misconfigured, the server
refuses to start — the gate fails closed, never silently open.

Environment:
  GAZELLE_GATE=1              enable enforcement
  WILLOWGATE_DIR              gate state dir (default: <app_data>/willowgate)
  WILLOWGATE_REQUIRE_PGP=0    dev-only plaintext ledger (default: PGP required)
  WILLOWGATE_KEY_FPR          operator PGP key for the encrypted ledger
  WILLOWGATE_SRC              optional path to a willow-gate src/ checkout

Operator registration (out-of-band, never via an MCP tool):
  python3 gazelle_gate.py register <agent_id> <max_trust 0..4>

b17: LGGATE1  ΔΣ=42
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import gazelle_paths


def _import_willow_gate():
    try:
        import willow_gate
    except ImportError:
        src = os.environ.get("WILLOWGATE_SRC")
        if not src:
            raise
        sys.path.insert(0, src)
        import willow_gate
    return willow_gate


# Trust class each MCP tool needs, and whether it exports (writes cross the
# app boundary into canonical Nest). Unknown tools are DENIED — fail closed.
TOOL_CLASS: dict[str, tuple[str, bool]] = {
    "gazelle_sync":            ("read", False),
    "gazelle_briefing":        ("read", False),
    "gazelle_urgent":          ("read", False),
    "gazelle_detail":          ("read", False),
    "gazelle_schedule":        ("read", False),
    "gazelle_chronology":      ("read", False),
    "gazelle_draft":           ("read", False),
    "gazelle_llm_health":      ("read", False),
    "gazelle_ai_brief":        ("query", False),
    "gazelle_ai_draft":        ("query", False),
    "gazelle_ai_rank_today":   ("query", False),
    "gazelle_ai_inspect_fact": ("query", False),
    "gazelle_note":            ("write", False),
    "gazelle_resolve":         ("write", False),
    "gazelle_save":            ("write", True),
    "gazelle_commit":          ("write", True),
}

_HEADER_SCHEMA = {
    "type": "object",
    "properties": {
        "header": {
            "type": "object",
            "description": (
                "Signed 13-field WillowGate header: agent_id, agent_name, "
                "last_gate, pass_count, fail_count, drift, nonce (32 hex), "
                "trust_level (0-4), timestamp (ms), tools, state_hash, "
                "signature (HMAC-SHA256, 64 hex), reserved (0)."
            ),
        }
    },
    "required": ["header"],
}

GATE_TOOLS = [
    {
        "name": "gazelle_gate_checkin",
        "description": (
            "Check in through WillowGate with a signed 13-field header. "
            "Required before any other tool when the gate is enabled. "
            "One live session at a time."
        ),
        "inputSchema": _HEADER_SCHEMA,
    },
    {
        "name": "gazelle_gate_checkout",
        "description": (
            "Check out of the live WillowGate session with a signed exit "
            "header. The gate diffs entry vs exit as defense-in-depth."
        ),
        "inputSchema": _HEADER_SCHEMA,
    },
]


class GateKeeper:
    """Holds the WillowGate instance and the single live MCP session."""

    def __init__(self) -> None:
        self.enabled = os.environ.get("GAZELLE_GATE", "").lower() in ("1", "true")
        self._gate = None
        self._session: dict | None = None
        if self.enabled:
            wg = _import_willow_gate()
            base = Path(
                os.environ.get("WILLOWGATE_DIR", str(gazelle_paths.app_data() / "willowgate"))
            ).expanduser()
            require_pgp = os.environ.get("WILLOWGATE_REQUIRE_PGP", "1").lower() not in ("0", "false")
            # Misconfiguration (no gnupg, no operator key) raises GateError
            # here and stops the server: fail closed, loudly.
            self._gate = wg.WillowGate(base_dir=base, require_pgp=require_pgp)

    # ── MCP-facing session lifecycle ─────────────────────────────────────────

    def checkin(self, header: dict) -> dict:
        if self._session is not None:
            return {"ok": False, "error": "A session is already live — check out first."}
        try:
            ok, msg, session = self._gate.check_in(header)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        self._session = session
        return {
            "ok": ok,
            "message": msg,
            "trust_level": session["trust_level"],
            "writable": session["writable"],
            "granted_tools": sorted(session["granted_tools"]),
        }

    def checkout(self, header: dict) -> dict:
        if self._session is None:
            return {"ok": False, "error": "No live session."}
        try:
            ok, msg = self._gate.check_out(self._session, header)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        self._session = None
        return {"ok": ok, "message": msg}

    # ── The inline lock ──────────────────────────────────────────────────────

    def authorize(self, tool_name: str) -> tuple[bool, str]:
        """Call BEFORE dispatching any gazelle tool. Denied never runs."""
        if not self.enabled:
            return True, "gate disabled"
        if self._session is None:
            return False, "DENIED — no live gate session; call gazelle_gate_checkin first"
        cls = TOOL_CLASS.get(tool_name)
        if cls is None:
            return False, f"DENIED — {tool_name!r} has no gate classification"
        tool_class, export = cls
        try:
            return self._gate.authorize_tool(self._session, tool_class, export=export)
        except Exception as exc:
            return False, f"DENIED — {exc}"


# ── Operator CLI: out-of-band agent registration ─────────────────────────────

def _register(agent_id: str, max_trust: int) -> None:
    import secrets

    os.environ.setdefault("GAZELLE_GATE", "1")
    keeper = GateKeeper()
    secret = secrets.token_bytes(32)
    keeper._gate.register_agent(agent_id, secret=secret, max_trust=max_trust)
    print(f"registered {agent_id!r} max_trust={max_trust}")
    print(f"secret (hex, shown once — store it agent-side): {secret.hex()}")


def build_header(agent_id: str, secret_hex: str, trust: int, tools: list[str],
                 *, pass_count: int, fail_count: int = 0, drift: int = 10,
                 nonce: str | None = None, timestamp: int | None = None,
                 last_gate: str = "saps1", state_hash: str = "0" * 64) -> dict:
    """Client-side helper: build and HMAC-sign a 13-field header."""
    from auth_gate import build_signed_header
    return build_signed_header(
        agent_id=agent_id,
        agent_name=agent_id,
        last_gate=last_gate,
        trust_level=trust,
        tools=tools,
        secret=bytes.fromhex(secret_hex),
        pass_count=pass_count,
        fail_count=fail_count,
        drift=drift,
        nonce=nonce,
        timestamp=timestamp,
        state_hash=state_hash,
    )


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "register":
        _register(sys.argv[2], int(sys.argv[3]))
    else:
        raise SystemExit("usage: gazelle_gate.py register <agent_id> <max_trust 0..4>")
