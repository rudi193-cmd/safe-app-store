"""Provenance ledger: every quantity is measured, fitted, or assumed.

Same discipline the rest of the store runs on (CLAUDE.md: "Provenance is a
state, not a score. Every input is measured, fitted or assumed, and a result
is worth its weakest input, propagated by min()."). Applied here to
ingredients: "2 cups flour, measured" is a different claim from "2 cups
flour, assumed" — someone guessed the second one, maybe from a photo of a
dish nobody wrote the recipe down for — and a recipe's trustworthiness is
the weakest ingredient in it, not an average.
"""
from __future__ import annotations

from enum import IntEnum
from typing import Iterable


class Provenance(IntEnum):
    """Ordered weakest-to-strongest so :func:`aggregate` can use plain min()."""

    ASSUMED = 0
    FITTED = 1
    MEASURED = 2

    @classmethod
    def parse(cls, value: str) -> "Provenance":
        try:
            return cls[value.strip().upper()]
        except KeyError as exc:
            valid = ", ".join(p.name.lower() for p in cls)
            raise ValueError(f"unknown provenance {value!r}; must be one of: {valid}") from exc

    def __str__(self) -> str:  # readable in CLI output and JSON dumps
        return self.name.lower()


def aggregate(provenances: Iterable[Provenance]) -> Provenance:
    """A recipe's provenance is the min() of its ingredients' — one assumed
    quantity drags the whole dish down. Raises on an empty recipe rather than
    returning a default, since "no ingredients" is not a provenance claim."""
    values = list(provenances)
    if not values:
        raise ValueError("cannot aggregate provenance over zero ingredients")
    return min(values)
