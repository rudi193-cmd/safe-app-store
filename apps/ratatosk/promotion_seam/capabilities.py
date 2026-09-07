"""Capability gate — no raw remote shell by default."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from promotion_seam.protocol.envelope import Envelope, Intent


class ActionResult(str, Enum):
    EXECUTED = "executed"
    QUEUED_CONFIRM = "queued_confirm"
    REJECTED = "rejected"
    DEGRADED = "degraded"


@dataclass
class PendingConfirm:
    trace_id: str
    envelope: Envelope
    reason: str


@dataclass
class CapabilityGate:
    auto_confirm_chat: bool = True
    pending: dict[str, PendingConfirm] = field(default_factory=dict)

    def classify(self, env: Envelope) -> ActionResult:
        if env.intent in {Intent.SHELL.value, Intent.RUN_TASK.value}:
            if env.requires_confirm:
                self.pending[env.trace_id] = PendingConfirm(
                    trace_id=env.trace_id,
                    envelope=env,
                    reason=f"high-risk intent: {env.intent}",
                )
                return ActionResult.QUEUED_CONFIRM
            return ActionResult.REJECTED
        if env.intent == Intent.CHAT.value and self.auto_confirm_chat:
            return ActionResult.EXECUTED
        if env.intent in {
            Intent.OPEN_STATUS.value,
            Intent.SUMMARIZE.value,
            Intent.REPLY.value,
        }:
            return ActionResult.EXECUTED
        return ActionResult.DEGRADED

    def approve(self, trace_id: str) -> PendingConfirm | None:
        return self.pending.pop(trace_id, None)

    def reject(self, trace_id: str) -> None:
        self.pending.pop(trace_id, None)
