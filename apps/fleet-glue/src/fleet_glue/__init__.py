"""fleet_glue — Nestor x Jeles x willow-mcp without trust laundering.

Binds against the shipped surfaces:

  * ``nestor.established.install`` (registers a tier-1.5 recognizer through
    ``cascade.set_tier15_recognizer`` — no monkeypatch of translate_segment)
  * ``jeles.corpus`` for nuggets / gaps
  * ``willow_mcp.gaps`` for the fleet gap spine
  * ``willow_mcp.mem_ratify`` as the canon door

Never seals. Never promotes automatically. Every lane that lands in Nestor
lands as ``status="draft"`` with attached evidence + citation warrants.
"""
from .standup import configure_lab, doctor_summary
from .hooks import install, installed, uninstall
from .gaps_compat import log_gap, list_all_gaps
from .corroborate import corroborate_to_draft
from .promote import (
    advisory_ratify,
    promote_gap_to_jeles,
    promote_gap_to_nestor_draft,
)
from .conflict import scan as conflict_scan
from .triage import summary as triage_summary

__all__ = [
    "configure_lab",
    "doctor_summary",
    "install",
    "installed",
    "uninstall",
    "log_gap",
    "list_all_gaps",
    "corroborate_to_draft",
    "advisory_ratify",
    "promote_gap_to_jeles",
    "promote_gap_to_nestor_draft",
    "conflict_scan",
    "triage_summary",
]
