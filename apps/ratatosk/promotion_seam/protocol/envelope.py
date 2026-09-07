"""Versioned Ratatosk envelope protocol."""
from __future__ import annotations

import json
import re
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


PROTOCOL_VERSION = 1
DEFAULT_TTL_SECONDS = 300
_SEEN_NONCES: set[str] = set()
_MAX_SEEN = 10_000


class Intent(str, Enum):
    CHAT = "chat"
    RUN_TASK = "run_task"
    OPEN_STATUS = "open_status"
    SUMMARIZE = "summarize"
    REPLY = "reply"
    REQUEST_CONFIRM = "request_confirm"
    SHELL = "shell"


class Capability(str, Enum):
    CHAT = "chat"
    RUN_TASK = "run_task"
    OPEN_STATUS = "open_status"
    SUMMARIZE = "summarize"
    REPLY = "reply"
    SHELL = "shell"


HIGH_RISK_INTENTS = frozenset({Intent.RUN_TASK, Intent.SHELL})
HIGH_RISK_CAPABILITIES = frozenset({Capability.RUN_TASK, Capability.SHELL})


@dataclass
class Envelope:
    v: int
    to: str
    from_agent: str
    intent: str
    prompt: str
    reply_channel: str
    mode: str
    capabilities: list[str]
    nonce: str
    trace_id: str
    expires_at: str
    requires_confirm: bool
    sender: str = ""
    raw: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "v": self.v,
            "to": self.to,
            "from": self.from_agent,
            "intent": self.intent,
            "prompt": self.prompt,
            "reply_channel": self.reply_channel,
            "mode": self.mode,
            "capabilities": self.capabilities,
            "nonce": self.nonce,
            "trace_id": self.trace_id,
            "expires_at": self.expires_at,
            "requires_confirm": self.requires_confirm,
        }
        data.update(self.extra)
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    envelope: Envelope | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _remember_nonce(nonce: str) -> bool:
    if nonce in _SEEN_NONCES:
        return False
    _SEEN_NONCES.add(nonce)
    if len(_SEEN_NONCES) > _MAX_SEEN:
        for _ in range(_MAX_SEEN // 2):
            _SEEN_NONCES.pop()
    return True


def clear_nonce_cache() -> None:
    _SEEN_NONCES.clear()


def build_envelope(
    *,
    to: str,
    prompt: str,
    from_agent: str = "ratatosk",
    intent: str = Intent.CHAT.value,
    reply_channel: str = "general",
    mode: str = "ollama",
    capabilities: list[str] | None = None,
    nonce: str | None = None,
    trace_id: str | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    requires_confirm: bool | None = None,
    extra: dict[str, Any] | None = None,
) -> Envelope:
    caps = capabilities or [Capability.CHAT.value]
    intent_enum = Intent(intent) if intent in Intent._value2member_map_ else Intent.CHAT
    if requires_confirm is None:
        requires_confirm = intent_enum in HIGH_RISK_INTENTS or any(
            c in {x.value for x in HIGH_RISK_CAPABILITIES} for c in caps
        )
    expires = (_utcnow() + timedelta(seconds=ttl_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return Envelope(
        v=PROTOCOL_VERSION,
        to=to,
        from_agent=from_agent,
        intent=intent,
        prompt=prompt,
        reply_channel=reply_channel,
        mode=mode,
        capabilities=caps,
        nonce=nonce or secrets.token_hex(8),
        trace_id=trace_id or f"tr-{uuid.uuid4().hex[:10]}",
        expires_at=expires,
        requires_confirm=requires_confirm,
        extra=extra or {},
    )


def _envelope_from_dict(data: dict[str, Any], sender: str, raw: str) -> Envelope:
    return Envelope(
        v=int(data.get("v", PROTOCOL_VERSION)),
        to=str(data.get("to", "")),
        from_agent=str(data.get("from", sender)),
        intent=str(data.get("intent", Intent.CHAT.value)),
        prompt=str(data.get("prompt", "")),
        reply_channel=str(data.get("reply_channel", "general")),
        mode=str(data.get("mode", "ollama")),
        capabilities=list(data.get("capabilities") or [Capability.CHAT.value]),
        nonce=str(data.get("nonce", "")),
        trace_id=str(data.get("trace_id", "")),
        expires_at=str(data.get("expires_at", "")),
        requires_confirm=bool(data.get("requires_confirm", False)),
        sender=sender,
        raw=raw,
        extra={
            k: v
            for k, v in data.items()
            if k
            not in {
                "v",
                "to",
                "from",
                "intent",
                "prompt",
                "reply_channel",
                "mode",
                "capabilities",
                "nonce",
                "trace_id",
                "expires_at",
                "requires_confirm",
            }
        },
    )


_ADDRESS_RE = re.compile(r"^([a-zA-Z0-9_-]+)\s*:\s*(.+)$", re.DOTALL)


def parse_grove_message(msg: dict[str, Any], default_node: str = "ratatosk") -> Envelope | None:
    raw = msg.get("content", "")
    sender = msg.get("sender", "unknown")
    if not isinstance(raw, str) or not raw.strip():
        return None

    try:
        data = json.loads(raw)
        if isinstance(data, dict) and ("prompt" in data or "intent" in data):
            env = _envelope_from_dict(data, sender=sender, raw=raw)
            if not env.to:
                env.to = default_node
            return env
    except json.JSONDecodeError:
        pass

    match = _ADDRESS_RE.match(raw.strip())
    if match:
        to, prompt = match.group(1), match.group(2).strip()
        env = build_envelope(
            to=to,
            prompt=prompt,
            from_agent=sender,
            intent=Intent.CHAT.value,
            reply_channel="general",
        )
        env.sender = sender
        env.raw = raw
        return env

    env = build_envelope(
        to=default_node,
        prompt=raw.strip(),
        from_agent=sender,
        intent=Intent.CHAT.value,
        reply_channel="general",
    )
    env.sender = sender
    env.raw = raw
    return env


def validate_envelope(
    env: Envelope,
    *,
    node: str,
    check_replay: bool = True,
    now: datetime | None = None,
) -> ValidationResult:
    errors: list[str] = []
    now = now or _utcnow()

    if env.v != PROTOCOL_VERSION:
        errors.append(f"unsupported protocol version: {env.v}")

    if not env.prompt.strip():
        errors.append("empty prompt")

    target = (env.to or "").lower()
    if target not in (node.lower(), "__all__", ""):
        errors.append(f"not addressed to {node}")

    exp = _parse_iso(env.expires_at)
    if exp and now > exp:
        errors.append("envelope expired")

    if env.intent in {i.value for i in HIGH_RISK_INTENTS} and not env.requires_confirm:
        errors.append(f"intent {env.intent} requires confirmation")

    if check_replay and env.nonce:
        if not _remember_nonce(env.nonce):
            errors.append("replay detected (duplicate nonce)")

    return ValidationResult(ok=not errors, errors=errors, envelope=env)
