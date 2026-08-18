"""Export recipes to readable text and JSON formats."""
from __future__ import annotations

import json

from kitchen_pudding.models import Recipe


def to_text(recipe: Recipe) -> str:
    """Readable plaintext recipe card."""
    lines: list[str] = []
    lines.append(recipe.title)
    lines.append("=" * len(recipe.title))
    lines.append("")

    if recipe.tags:
        lines.append(f"Tags: {', '.join(recipe.tags)}")
        lines.append("")

    try:
        lines.append(f"Provenance: {recipe.provenance()}")
    except ValueError:
        pass
    lines.append("")

    lines.append("Ingredients")
    lines.append("-----------")
    for ing in recipe.ingredients:
        note = f"  ({ing.note})" if ing.note else ""
        lines.append(f"  {ing.qty} {ing.unit} {ing.name}  [{ing.provenance}]{note}")
    lines.append("")

    if recipe.steps:
        lines.append("Steps")
        lines.append("-----")
        for i, step in enumerate(recipe.steps, 1):
            lines.append(f"  {i}. {step}")
        lines.append("")

    return "\n".join(lines)


def to_json(recipe: Recipe, *, indent: int = 2) -> str:
    """JSON export of the current (correction-replayed) recipe."""
    return json.dumps(recipe.to_dict(), indent=indent, sort_keys=True) + "\n"
