"""gate.py — the paper-first gate.

Reaching live requires ALL of:
  1. a separate live credential present in the environment (never in the repo),
  2. an explicit human confirmation phrase set in the environment,
  3. a minimum paper track record (enough simulated fills over enough days).

is_live_authorized() returns False by default and stays False until every
condition is met. In this build even a fully-cleared gate does NOT enable real
orders — the LiveAdapter still refuses — but the gate is the real mechanism that
any future guarded live build would rely on, so it is implemented and tested for
real.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import Config, GateConfig, get_secret


@dataclass
class GateStatus:
    authorized: bool
    has_credential: bool
    has_confirmation: bool
    paper_fills: int
    paper_days: int
    meets_paper_record: bool
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "authorized": self.authorized,
            "has_credential": self.has_credential,
            "has_confirmation": self.has_confirmation,
            "paper_fills": self.paper_fills,
            "paper_days": self.paper_days,
            "meets_paper_record": self.meets_paper_record,
            "reasons": self.reasons,
        }


class LiveGate:
    def __init__(self, gate_config: GateConfig | None = None) -> None:
        self.cfg = gate_config or GateConfig()

    def _has_credential(self) -> bool:
        val = get_secret(self.cfg.live_credential_env)
        return bool(val and val.strip())

    def _has_confirmation(self) -> bool:
        val = get_secret(self.cfg.live_confirm_env)
        return val is not None and val.strip() == self.cfg.live_confirm_phrase

    def status(self, paper_fills: int = 0, paper_days: int = 0) -> GateStatus:
        has_cred = self._has_credential()
        has_conf = self._has_confirmation()
        meets_record = (
            paper_fills >= self.cfg.min_paper_fills
            and paper_days >= self.cfg.min_paper_days
        )
        reasons: list[str] = []
        if not has_cred:
            reasons.append(
                f"no live credential ({self.cfg.live_credential_env} unset)"
            )
        if not has_conf:
            reasons.append(
                f"no explicit confirmation "
                f"({self.cfg.live_confirm_env} != {self.cfg.live_confirm_phrase!r})"
            )
        if not meets_record:
            reasons.append(
                f"paper track record insufficient "
                f"({paper_fills}/{self.cfg.min_paper_fills} fills, "
                f"{paper_days}/{self.cfg.min_paper_days} days)"
            )
        authorized = has_cred and has_conf and meets_record
        if authorized:
            reasons.append("all gate conditions met")
        return GateStatus(
            authorized=authorized,
            has_credential=has_cred,
            has_confirmation=has_conf,
            paper_fills=paper_fills,
            paper_days=paper_days,
            meets_paper_record=meets_record,
            reasons=reasons,
        )

    def is_live_authorized(self, paper_fills: int = 0, paper_days: int = 0) -> bool:
        return self.status(paper_fills, paper_days).authorized


def is_live_authorized(paper_fills: int = 0, paper_days: int = 0) -> bool:
    """Module-level convenience. False by default."""
    return LiveGate().is_live_authorized(paper_fills, paper_days)
