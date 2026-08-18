from __future__ import annotations

from kitchen_pudding.models import Ingredient, Recipe
from kitchen_pudding.provenance import Provenance
from kitchen_pudding.search import search
from kitchen_pudding.store import RecipeStore


def _add_recipes(store):
    store.add(Recipe(
        id="cake-1", title="Chocolate Cake",
        ingredients=(
            Ingredient("flour", "2", "cups", Provenance.MEASURED),
            Ingredient("cocoa", "1", "cup", Provenance.ASSUMED),
        ),
        steps=("mix dry", "bake"),
        tags=("dessert", "chocolate"),
    ))
    store.add(Recipe(
        id="bread-1", title="Sourdough Bread",
        ingredients=(
            Ingredient("flour", "3", "cups", Provenance.MEASURED),
            Ingredient("salt", "1", "tsp", Provenance.MEASURED),
        ),
        steps=("knead", "proof", "bake"),
        tags=("bread", "fermented"),
    ))
    store.add(Recipe(
        id="sauce-1", title="Tomato Sauce",
        ingredients=(
            Ingredient("tomatoes", "4", "whole", Provenance.FITTED),
            Ingredient("garlic", "2", "cloves", Provenance.MEASURED),
        ),
        steps=("simmer",),
        tags=("sauce",),
    ))


def test_search_all_returns_everything(tmp_path):
    store = RecipeStore(root=tmp_path)
    _add_recipes(store)
    assert len(search(store)) == 3


def test_search_by_title(tmp_path):
    store = RecipeStore(root=tmp_path)
    _add_recipes(store)
    results = search(store, title="chocolate")
    assert len(results) == 1
    assert results[0].id == "cake-1"


def test_search_by_title_case_insensitive(tmp_path):
    store = RecipeStore(root=tmp_path)
    _add_recipes(store)
    results = search(store, title="SOURDOUGH")
    assert len(results) == 1
    assert results[0].id == "bread-1"


def test_search_by_ingredient(tmp_path):
    store = RecipeStore(root=tmp_path)
    _add_recipes(store)
    results = search(store, ingredient="flour")
    assert len(results) == 2
    ids = {r.id for r in results}
    assert ids == {"cake-1", "bread-1"}


def test_search_by_tag(tmp_path):
    store = RecipeStore(root=tmp_path)
    _add_recipes(store)
    results = search(store, tag="dessert")
    assert len(results) == 1
    assert results[0].id == "cake-1"


def test_search_by_max_provenance(tmp_path):
    store = RecipeStore(root=tmp_path)
    _add_recipes(store)
    results = search(store, max_provenance=Provenance.ASSUMED)
    assert len(results) == 1
    assert results[0].id == "cake-1"


def test_search_by_min_provenance(tmp_path):
    store = RecipeStore(root=tmp_path)
    _add_recipes(store)
    results = search(store, min_provenance=Provenance.MEASURED)
    assert len(results) == 1
    assert results[0].id == "bread-1"


def test_search_combined_filters(tmp_path):
    store = RecipeStore(root=tmp_path)
    _add_recipes(store)
    results = search(store, ingredient="flour", min_provenance=Provenance.MEASURED)
    assert len(results) == 1
    assert results[0].id == "bread-1"


def test_search_no_matches(tmp_path):
    store = RecipeStore(root=tmp_path)
    _add_recipes(store)
    results = search(store, title="nonexistent")
    assert results == []


def test_search_empty_store(tmp_path):
    store = RecipeStore(root=tmp_path)
    assert search(store) == []


def test_search_reflects_corrections(tmp_path):
    store = RecipeStore(root=tmp_path)
    _add_recipes(store)
    store.correct("cake-1", index=1, field_name="provenance", value="measured", note="verified")
    results = search(store, min_provenance=Provenance.MEASURED)
    assert len(results) == 2
    ids = {r.id for r in results}
    assert "cake-1" in ids
