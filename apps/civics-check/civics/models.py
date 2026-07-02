"""Shared constants and light types for the civics catalog."""

from __future__ import annotations

LANES = (
    "schoolhouse",
    "constitution_hall",
    "citizenship_court",
    "underground",
)

TIERS = ("tap", "show", "know")

# tap = kid pick / browse only; show = guided quiz; know = USCIS-style typing
KINDS = (
    "browse",
    "quiz",
    "pick",
    "match",
    "sort",
    "debate",
    "duel",
)

CATALOG_VERSION = 2
