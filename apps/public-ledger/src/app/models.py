"""
Public Ledger Data Models
=========================
Frozen dataclasses for audit claims, evidence, and results.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class AuditClaim:
    """A single verifiable claim to audit against public records."""
    claim_id: str
    text: str
    claim_type: str  # nonprofit_funding | federal_spending | wealth_gap | contractor_link
    entities: tuple[str, ...] = ()
    amount_claimed: float | None = None
    currency: str = "USD"
    time_period: str | None = None
    source_report: str = ""


@dataclass(frozen=True)
class SourceEvidence:
    """A single piece of evidence from a public data source."""
    api_source: str  # propublica | usaspending | paperclip_cube | ons_uk
    url: str
    raw_field: str
    value_found: float | None = None
    description: str = ""
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class AuditResult:
    """The outcome of auditing a single claim."""
    claim: AuditClaim
    verdict: str  # SUPPORTED | PARTIALLY_SUPPORTED | UNSUPPORTED | INSUFFICIENT_DATA | DISPUTED
    confidence: str  # high | medium | low
    evidence: tuple[SourceEvidence, ...] = ()
    discrepancy: str | None = None
    ledger_narrative: str = ""
    audited_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
