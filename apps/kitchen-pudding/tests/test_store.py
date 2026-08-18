from __future__ import annotations

import pytest

from kitchen_pudding.models import Ingredient, Recipe
from kitchen_pudding.provenance import Provenance
from kitchen_pudding.store import RecipeStore, UnknownRecipe


def _recipe(recipe_id="pud-1"):
    return Recipe(
        id=recipe_id,
        title="Sociotechnocratic Pudding",
        ingredients=(
            Ingredient("milk", "2", "cups", Provenance.MEASURED),
            Ingredient("vanilla", "1", "tsp", Provenance.ASSUMED, note="handwritten card, unreadable qty"),
        ),
        steps=("heat milk", "whisk in vanilla"),
    )


def test_add_then_get_original_round_trips(tmp_path):
    store = RecipeStore(root=tmp_path)
    store.add(_recipe())
    got = store.get_original("pud-1")
    assert got.title == "Sociotechnocratic Pudding"
    assert got.ingredients[1].provenance is Provenance.ASSUMED


def test_add_refuses_to_overwrite_existing_recipe(tmp_path):
    store = RecipeStore(root=tmp_path)
    store.add(_recipe())
    with pytest.raises(FileExistsError):
        store.add(_recipe())


def test_get_unknown_recipe_raises(tmp_path):
    store = RecipeStore(root=tmp_path)
    with pytest.raises(UnknownRecipe):
        store.get_original("does-not-exist")


def test_recipe_provenance_is_weakest_ingredient(tmp_path):
    store = RecipeStore(root=tmp_path)
    store.add(_recipe())
    assert store.get_original("pud-1").provenance() is Provenance.ASSUMED


def test_correct_does_not_change_the_original_file_on_disk(tmp_path):
    # The mechanism this test exists to catch: a correct() that overwrites the
    # original in place. If someone "simplifies" correct() to open(path, "w")
    # instead of appending to the corrections log, this is the test that goes
    # red — and it is the only one that should.
    store = RecipeStore(root=tmp_path)
    store.add(_recipe())
    original_bytes = store._recipe_path("pud-1").read_bytes()

    store.correct("pud-1", index=1, field_name="qty", value="2", note="found the original card")

    assert store._recipe_path("pud-1").read_bytes() == original_bytes


def test_correct_is_visible_through_current_but_not_get_original(tmp_path):
    store = RecipeStore(root=tmp_path)
    store.add(_recipe())

    store.correct("pud-1", index=1, field_name="qty", value="2", note="found the original card")
    store.correct("pud-1", index=1, field_name="provenance", value="measured", note="card was legible after all")

    original = store.get_original("pud-1")
    current = store.current("pud-1")

    assert original.ingredients[1].qty == "1"
    assert original.ingredients[1].provenance is Provenance.ASSUMED

    assert current.ingredients[1].qty == "2"
    assert current.ingredients[1].provenance is Provenance.MEASURED
    assert current.provenance() is Provenance.MEASURED  # both ingredients now measured


def test_corrections_accumulate_append_only(tmp_path):
    store = RecipeStore(root=tmp_path)
    store.add(_recipe())
    store.correct("pud-1", index=0, field_name="note", value="fridge, 2 days old", note="clarify freshness")
    store.correct("pud-1", index=0, field_name="note", value="fridge, whole milk", note="correcting the correction")

    log = store.get_corrections("pud-1")
    assert len(log) == 2
    assert log[0]["value"] == "fridge, 2 days old"
    assert log[1]["value"] == "fridge, whole milk"
    # the earlier correction is still readable, not overwritten by the later one
    assert store.current("pud-1").ingredients[0].note == "fridge, whole milk"


def test_correct_rejects_out_of_range_index(tmp_path):
    store = RecipeStore(root=tmp_path)
    store.add(_recipe())
    with pytest.raises(IndexError):
        store.correct("pud-1", index=99, field_name="qty", value="3", note="")


def test_correct_rejects_invalid_provenance_value(tmp_path):
    store = RecipeStore(root=tmp_path)
    store.add(_recipe())
    with pytest.raises(ValueError):
        store.correct("pud-1", index=0, field_name="provenance", value="guessed", note="")


def test_list_ids_is_sorted_and_reflects_current_titles(tmp_path):
    store = RecipeStore(root=tmp_path)
    store.add(_recipe("pud-2"))
    store.add(_recipe("pud-1"))
    assert store.list_ids() == ["pud-1", "pud-2"]


def test_correct_unknown_recipe_raises(tmp_path):
    store = RecipeStore(root=tmp_path)
    with pytest.raises(UnknownRecipe):
        store.correct("ghost", index=0, field_name="qty", value="3", note="")


def test_correct_unit_field(tmp_path):
    store = RecipeStore(root=tmp_path)
    store.add(_recipe())
    store.correct("pud-1", index=0, field_name="unit", value="ml", note="metric")
    current = store.current("pud-1")
    assert current.ingredients[0].unit == "ml"
    assert store.get_original("pud-1").ingredients[0].unit == "cups"


def test_correct_rejects_invalid_field_name(tmp_path):
    store = RecipeStore(root=tmp_path)
    store.add(_recipe())
    with pytest.raises(ValueError):
        store.correct("pud-1", index=0, field_name="name", value="water", note="")


def test_list_tags_empty_store(tmp_path):
    store = RecipeStore(root=tmp_path)
    assert store.list_tags() == []


def test_list_tags_collects_from_all_recipes(tmp_path):
    store = RecipeStore(root=tmp_path)
    store.add(Recipe(
        id="r1", title="A",
        ingredients=(Ingredient("x", "1", "g", Provenance.MEASURED),),
        tags=("bread", "quick"),
    ))
    store.add(Recipe(
        id="r2", title="B",
        ingredients=(Ingredient("y", "2", "g", Provenance.MEASURED),),
        tags=("quick", "dessert"),
    ))
    assert store.list_tags() == ["bread", "dessert", "quick"]


def test_import_from_file(tmp_path):
    import json
    store = RecipeStore(root=tmp_path)
    recipe_data = {
        "id": "imported-1",
        "title": "Imported Recipe",
        "ingredients": [{"name": "flour", "qty": "2", "unit": "cups", "provenance": "measured"}],
        "steps": ["mix"],
        "tags": ["imported"],
    }
    file_path = tmp_path / "to-import.json"
    file_path.write_text(json.dumps(recipe_data))
    recipe = store.import_from_file(file_path)
    assert recipe.id == "imported-1"
    assert recipe.tags == ("imported",)
    got = store.get_original("imported-1")
    assert got.title == "Imported Recipe"


def test_import_from_file_refuses_duplicate(tmp_path):
    import json
    store = RecipeStore(root=tmp_path)
    store.add(_recipe())
    recipe_data = _recipe().to_dict()
    file_path = tmp_path / "dup.json"
    file_path.write_text(json.dumps(recipe_data))
    with pytest.raises(FileExistsError):
        store.import_from_file(file_path)
