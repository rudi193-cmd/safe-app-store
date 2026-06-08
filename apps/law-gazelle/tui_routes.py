"""
tui_routes.py — drill-down route stack for Law Gazelle TUI.

b17: LGRTE1  ΔΣ=42
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RouteFrame:
    """One level in the navigation stack."""

    route: str
    params: dict[str, Any] = field(default_factory=dict)
    label: str = ""

    def breadcrumb(self) -> str:
        return self.label or ROUTE_LABELS.get(self.route, self.route)


ROUTE_LABELS: dict[str, str] = {
    "home": "Today",
    "action_deck": "Action",
    "packet": "Packet",
    "fact_review": "Fact Review",
    "matters": "Matters",
    "matter_items": "Matter",
    "drafts": "Drafts",
    "session": "Session",
    "activity": "Activity",
}

MATTER_NAV: list[tuple[str, str, str]] = [
    ("coparent", "Coparent", "D-000-DM-0000-00000 atoms and issues"),
    ("bankruptcy", "Bankruptcy", "Flags, creditors, checklist"),
    ("workers_comp", "Workers Comp", "WCA claim atoms"),
    ("cross_case", "Cross-Case", "Intersections and shared context"),
    ("cases", "All Cases", "Case summary overview"),
]

MATTER_ITEM_ROUTES = frozenset({"coparent", "bankruptcy", "workers_comp", "cross_case", "cases"})

# Routes where row actions (done, note, snooze) apply to case items
ACTIONABLE_ROUTES = frozenset({"home", "matter_items", "action_deck", "fact_review"})

# Routes where triage keys apply to the active workflow card
WORKFLOW_CARD_ROUTES = frozenset({"action_deck", "fact_review"})

# Routes where o opens a file
OPEN_FILE_ROUTES = frozenset({"drafts", "session"})


def breadcrumb_text(stack: list[RouteFrame]) -> str:
    """Render stack as Today › Action › Packet."""
    if not stack:
        return "Today"
    parts = [stack[0].breadcrumb()]
    for frame in stack[1:]:
        parts.append(frame.breadcrumb())
    return " › ".join(parts)


def footer_hints(route: str, *, show_resolved: bool) -> str:
    """Contextual key hints for the current route."""
    base = "Enter open · Esc back · r refresh · q quit"
    if route == "home":
        resolved = "showing resolved" if show_resolved else "hiding resolved"
        return (
            f"Enter action deck · i rank today · m matters · d drafts · a activity · "
            f"t toggle resolved ({resolved})"
        )
    if route == "action_deck":
        return "Enter step · n note · z snooze · x done · Esc back"
    if route == "packet":
        return "Esc back to action deck · " + base
    if route == "fact_review":
        return (
            "f AI inspect (cached) · Shift+f re-inspect · "
            "1 verified · 2 needs source · 3 do not use · Esc back"
        )
    if route == "activity":
        return "u today · m matters · d drafts · s session · Esc back"
    if route == "matters":
        return f"Enter open matter · u today · d drafts · s session · {base}"
    if route == "matter_items":
        return f"x done · n note · z snooze · u today · m matters · {base}"
    if route == "drafts":
        return f"o open draft · u today · m matters · s session · {base}"
    if route == "session":
        return f"o open artifact · u today · m matters · d drafts · {base}"
    return base
