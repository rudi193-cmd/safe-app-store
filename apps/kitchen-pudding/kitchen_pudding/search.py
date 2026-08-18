"""Search and filter recipes in the store."""
from __future__ import annotations

from kitchen_pudding.models import Recipe
from kitchen_pudding.provenance import Provenance
from kitchen_pudding.store import RecipeStore


def search(
    store: RecipeStore,
    *,
    title: str | None = None,
    ingredient: str | None = None,
    tag: str | None = None,
    max_provenance: Provenance | None = None,
    min_provenance: Provenance | None = None,
) -> list[Recipe]:
    """Return current-view recipes matching all given filters.

    Filters are AND-combined: a recipe must match every non-None filter.
    String filters are case-insensitive substrings.
    ``max_provenance`` keeps only recipes whose overall provenance is at most
    that level (e.g. ASSUMED keeps only assumed-level recipes).
    ``min_provenance`` keeps only recipes at or above that level.
    """
    results: list[Recipe] = []
    for recipe_id in store.list_ids():
        recipe = store.current(recipe_id)
        if title is not None and title.lower() not in recipe.title.lower():
            continue
        if ingredient is not None:
            needle = ingredient.lower()
            if not any(needle in ing.name.lower() for ing in recipe.ingredients):
                continue
        if tag is not None:
            needle = tag.lower()
            if not any(needle in t.lower() for t in recipe.tags):
                continue
        try:
            prov = recipe.provenance()
        except ValueError:
            if max_provenance is not None or min_provenance is not None:
                continue
            prov = None
        if prov is not None:
            if max_provenance is not None and prov > max_provenance:
                continue
            if min_provenance is not None and prov < min_provenance:
                continue
        results.append(recipe)
    return results
