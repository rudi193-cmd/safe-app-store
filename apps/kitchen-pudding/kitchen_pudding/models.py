"""Ingredient and Recipe records."""
from __future__ import annotations

from dataclasses import dataclass, field

from kitchen_pudding.provenance import Provenance, aggregate


@dataclass(frozen=True)
class Ingredient:
    name: str
    qty: str
    unit: str
    provenance: Provenance
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "qty": self.qty,
            "unit": self.unit,
            "provenance": str(self.provenance),
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Ingredient":
        return cls(
            name=d["name"],
            qty=d["qty"],
            unit=d["unit"],
            provenance=Provenance.parse(d["provenance"]),
            note=d.get("note", ""),
        )


@dataclass(frozen=True)
class Recipe:
    id: str
    title: str
    ingredients: tuple[Ingredient, ...]
    steps: tuple[str, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)

    def provenance(self) -> Provenance:
        return aggregate(i.provenance for i in self.ingredients)

    def to_dict(self) -> dict:
        d: dict = {
            "id": self.id,
            "title": self.title,
            "ingredients": [i.to_dict() for i in self.ingredients],
            "steps": list(self.steps),
        }
        if self.tags:
            d["tags"] = list(self.tags)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Recipe":
        return cls(
            id=d["id"],
            title=d["title"],
            ingredients=tuple(Ingredient.from_dict(i) for i in d["ingredients"]),
            steps=tuple(d.get("steps", ())),
            tags=tuple(d.get("tags", ())),
        )
