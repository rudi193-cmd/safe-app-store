"""auth-gate: AuthGate Protocol + shared WillowGate header signing.

Provides:
  - AuthGate Protocol: check_in / authorize_tool / check_out / register_agent
  - build_signed_header(): canonical 13-field header construction + HMAC-SHA256
  - set_gate() / get_gate(): dependency injection with no-op degradation

Apps program against the Protocol; the concrete WillowGate class satisfies it
structurally. No dependency on willow-gate at import time.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Optional, Protocol, runtime_checkable

log = logging.getLogger("auth_gate")

__all__ = [
    "AuthGate",
    "SIGNED_FIELDS",
    "build_signed_header",
    "set_gate",
    "get_gate",
    "available",
]

SIGNED_FIELDS = sorted([
    "agent_id", "agent_name", "last_gate", "pass_count", "fail_count",
    "drift", "nonce", "trust_level", "timestamp", "tools", "state_hash",
    "reserved",
])


@runtime_checkable
class AuthGate(Protocol):
    """Anything that can check-in/out agents and authorize tool use."""

    def check_in(self, header: dict) -> tuple[bool, str, Optional[dict]]: ...

    def authorize_tool(
        self, session: dict, tool: str, *, export: bool = False,
    ) -> tuple[bool, str]: ...

    def check_out(self, session: dict, header: dict) -> tuple[bool, str]: ...

    def register_agent(
        self, agent_id: str, secret: bytes, *, max_trust: int = 0,
    ) -> None: ...


_gate: Optional[AuthGate] = None


def set_gate(gate: Optional[AuthGate]) -> None:
    global _gate
    _gate = gate


def get_gate() -> Optional[AuthGate]:
    return _gate


def available() -> bool:
    return _gate is not None


def build_signed_header(
    *,
    agent_id: str,
    agent_name: str,
    last_gate: str,
    trust_level: int,
    tools: list[str],
    secret: bytes,
    pass_count: int = 0,
    fail_count: int = 0,
    drift: int = 0,
    nonce: Optional[str] = None,
    timestamp: Optional[int] = None,
    state_hash: Optional[str] = None,
) -> dict:
    """Build and HMAC-SHA256-sign a 13-field WillowGate header.

    This is the single canonical implementation — replaces the 3 copies
    in sap/core/gate.py, gatefirst/identity.py, and gazelle_gate.py.
    """
    header = {
        "agent_id": agent_id,
        "agent_name": agent_name,
        "last_gate": last_gate,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "drift": drift,
        "nonce": nonce or secrets.token_hex(16),
        "trust_level": trust_level,
        "timestamp": timestamp if timestamp is not None else int(time.time() * 1000),
        "tools": tools,
        "state_hash": state_hash or hashlib.sha256(
            f"{last_gate}:{agent_name}".encode()
        ).hexdigest(),
        "reserved": 0,
    }
    canonical = json.dumps(
        {k: header[k] for k in SIGNED_FIELDS},
        sort_keys=True, separators=(",", ":"),
    ).encode()
    header["signature"] = hmac.new(secret, canonical, hashlib.sha256).hexdigest()
    return header
