"""
sap.core.gate — SAFE App Permission Gate, backed by WillowGate.
b17: NNA92
ΔΣ=42

PII access gate for client_only data streams. Every PII read/write in
db.persons / db.fragments / db.events / db.media calls authorized() first;
this module is the single chokepoint between the app and the family tree.

v2 (2026-07-15): the stub env-var gate is replaced by willow-gate
(https://github.com/rudi193-cmd/willow-gate) — HMAC-bound identities, a
trust ladder, inline authorize_tool() enforcement, and a flat-file ledger
that announces louder the less an actor is trusted.

Actors (registered at first use, secrets minted per process):

  journal — the user's own hands: @squirrel: commands, web views, saves.
            Trust: Steady (2). read + write + export.
  jeles   — the LLM: chat mode, active listening, story interviews.
            Trust: Rookie (1). read-only, loud, may NEVER export.

The trust table — not app code — is what stops the LLM from writing to the
tree or carrying PII out. "Elder is not a text field anyone can type."

Usage:
  Entry points declare who is acting:
      with sap.core.gate.actor("journal"):
          ... db calls ...
  PII functions keep calling authorized("read"|"write"|"export") as before.
  Scripts keep the explicit block-level override:
      with sap.core.gate.bypass("backfill from memorial 273702757"):
          ...

Authorization changes from v1:
  - SAP_AUTHORIZED=1 no longer grants anything. Self-authorization is gone.
  - No actor context and no bypass → PermissionDenied, every time.
  - willow-gate not installed → PermissionDenied (the gate fails closed).

Ledger: ~/.squirrel/willowgate/ (override: SQUIRREL_GATE_DIR). Set
WILLOWGATE_KEY_FPR to a PGP fingerprint in your keyring to encrypt ledger
records to it; unset, records are plaintext JSON (still a record).
"""

import atexit
import hashlib
import hmac
import json
import os
import secrets as _pysecrets
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from threading import Lock, local

_state = local()
_lock = Lock()
_backend = None  # {"gate": WillowGate, "secrets": {role: bytes}, "sessions": {role: dict}}


class PermissionDenied(PermissionError):
    """Raised when the SAP gate rejects a PII operation."""


# role -> willow-gate identity. Trust ceilings are the policy:
# Steady (2) may read/write/export; Rookie (1) is read-only and export-denied.
# pass_floor seeds the check-in history at the level's minimum pass_count.
ROLES = {
    "journal": {"agent_id": "squirrel-journal", "trust": 2,
                "tools": ("read", "write"), "pass_floor": 3},
    "jeles":   {"agent_id": "squirrel-jeles", "trust": 1,
                "tools": ("read",), "pass_floor": 0},
}

# operation name used by callers -> (willow-gate tool, export flag)
_OPERATIONS = {
    "read":   ("read", False),
    "write":  ("write", False),
    "export": ("read", True),   # PII leaving the box: read + exfiltration flag
}

_FIELD_NAMES = sorted({
    "agent_id", "agent_name", "last_gate", "pass_count", "fail_count", "drift",
    "nonce", "trust_level", "timestamp", "tools", "state_hash", "reserved",
})


def _gate_dir() -> Path:
    return Path(os.environ.get(
        "SQUIRREL_GATE_DIR", str(Path.home() / ".squirrel" / "willowgate")))


def _signed_header(role: str, secret: bytes, *, nonce: str = None,
                   timestamp: int = None, tools=None) -> dict:
    spec = ROLES[role]
    header = {
        "agent_id": spec["agent_id"],
        "agent_name": role,
        "last_gate": "the-squirrel",
        "pass_count": spec["pass_floor"],
        "fail_count": 0,
        "drift": 0,
        "nonce": nonce or _pysecrets.token_hex(16),
        "trust_level": spec["trust"],
        "timestamp": timestamp if timestamp is not None else int(time.time() * 1000),
        "tools": list(spec["tools"] if tools is None else tools),
        "state_hash": hashlib.sha256(f"the-squirrel:{role}".encode()).hexdigest(),
        "reserved": 0,
    }
    canonical = json.dumps({k: header[k] for k in _FIELD_NAMES},
                           sort_keys=True, separators=(",", ":")).encode()
    header["signature"] = hmac.new(secret, canonical, hashlib.sha256).hexdigest()
    return header


def _build_backend() -> dict:
    try:
        from willow_gate import WillowGate
    except ImportError as e:
        raise PermissionDenied(
            "SAP gate: willow-gate is not installed — PII access is closed. "
            "Install it (see requirements.txt) or use "
            "`with sap.core.gate.bypass(reason):` for trusted scripts."
        ) from e

    base = _gate_dir()
    base.mkdir(parents=True, exist_ok=True)
    os.chmod(base, 0o700)

    key_fpr = os.environ.get("WILLOWGATE_KEY_FPR", "")
    gate = WillowGate(operator_key_fpr=key_fpr or None,
                      base_dir=base, require_pgp=bool(key_fpr))

    secrets_map = {}
    for role, spec in ROLES.items():
        secret = _pysecrets.token_bytes(32)
        gate.register_agent(spec["agent_id"], secret, max_trust=spec["trust"])
        secrets_map[role] = secret
    registry = base / "registry.json"
    if registry.exists():
        os.chmod(registry, 0o600)

    return {"gate": gate, "secrets": secrets_map, "sessions": {}}


def _session_for(role: str):
    global _backend
    with _lock:
        if _backend is None:
            _backend = _build_backend()
        backend = _backend
        session = backend["sessions"].get(role)
        if session is None or session["nonce"] not in backend["gate"].sessions:
            header = _signed_header(role, backend["secrets"][role])
            ok, msg, session = backend["gate"].check_in(header)
            if not ok or session is None:
                raise PermissionDenied(f"SAP gate: check-in refused for '{role}': {msg}")
            backend["sessions"][role] = session
        return backend["gate"], session


@contextmanager
def actor(role: str):
    """Declare who is acting for the duration of the block.

    "journal" is the user's own hands; "jeles" is the LLM. Nest freely —
    the previous actor is restored on exit. Thread-local.
    """
    if role not in ROLES:
        raise ValueError(f"unknown gate actor {role!r} — one of {sorted(ROLES)}")
    previous = getattr(_state, "actor_role", None)
    _state.actor_role = role
    try:
        yield
    finally:
        _state.actor_role = previous


def authorized(operation: str = "write", scope: str = "family_history") -> None:
    """
    Assert that the current actor is authorized for a PII operation.

    Raises PermissionDenied if not. Every allow/deny is announced to the
    willow-gate ledger — louder for less-trusted actors.

    Args:
        operation: "read", "write", or "export" (export = PII leaving the box).
        scope:     Data scope label — used in the error message only.
    """
    if getattr(_state, "bypass_active", False):
        return
    role = getattr(_state, "actor_role", None)
    if role is None:
        raise PermissionDenied(
            f"SAP gate: PII {operation} on '{scope}' has no actor. Wrap the "
            f"entry point in `with sap.core.gate.actor(\"journal\"):` (user) or "
            f"`actor(\"jeles\")` (LLM), or use `bypass(reason)` in a trusted script."
        )
    tool, export = _OPERATIONS.get(operation, (operation, False))
    gate, session = _session_for(role)
    ok, why = gate.authorize_tool(session, tool, export=export)
    if not ok:
        raise PermissionDenied(
            f"SAP gate: PII {operation} on '{scope}' denied for actor '{role}' — {why}")


@contextmanager
def bypass(reason: str):
    """
    Explicitly bypass the SAP gate for a block of PII operations.

    Requires a non-empty reason string — the reason is the paper trail.
    For migration/backfill scripts and other operator-driven work only.
    """
    if not reason or not reason.strip():
        raise ValueError("sap.core.gate.bypass() requires a non-empty reason.")
    _state.bypass_active = True
    try:
        yield
    finally:
        _state.bypass_active = False


def close() -> None:
    """Check out all live sessions (writes the exit diff to the ledger) and
    drop the backend. Safe to call repeatedly; registered atexit."""
    global _backend
    with _lock:
        backend, _backend = _backend, None
    if backend is None:
        return
    gate = backend["gate"]
    for role, session in list(backend["sessions"].items()):
        if session["nonce"] not in gate.sessions:
            continue
        try:
            exit_header = _signed_header(
                role, backend["secrets"][role],
                nonce=session["nonce"],
                timestamp=max(int(time.time() * 1000), session["entry_ms"] + 1),
                tools=sorted(session["tools_used"]),
            )
            gate.check_out(session, exit_header)
        except Exception as e:  # shutdown bookkeeping must not crash the app
            print(f"sap.core.gate: check-out failed for '{role}': {e}", file=sys.stderr)


atexit.register(close)
