"""Dedicated tests for Ingredient and Recipe data models.

Covers serialization round-trips, edge cases in from_dict, frozen
immutability, provenance aggregation through Recipe.provenance(), and
the interaction between defaults and explicit values.
"""
from __future__ import annotations

import json

import pytest

from kitchen_pudding.models import Ingredient, Recipe
from kitchen_pudding.provenance import Provenance


class TestIngredient:

    def test_to_dict_round_trip(self):
        ing = Ingredient("flour", "2", "cups", Provenance.MEASURED, note="sifted")
        d = ing.to_dict()
        got = Ingredient.from_dict(d)
        assert got == ing

    def test_to_dict_shape(self):
        ing = Ingredient("sugar", "1", "tbsp", Provenance.ASSUMED)
        d = ing.to_dict()
        assert d == {
            "name": "sugar",
            "qty": "1",
            "unit": "tbsp",
            "provenance": "assumed",
            "note": "",
        }

    def test_from_dict_missing_note_defaults_empty(self):
        d = {"name": "salt", "qty": "1", "unit": "pinch", "provenance": "measured"}
        ing = Ingredient.from_dict(d)
        assert ing.note == ""

    def test_from_dict_with_note(self):
        d = {"name": "salt", "qty": "1", "unit": "pinch", "provenance": "measured",
             "note": "kosher"}
        ing = Ingredient.from_dict(d)
        assert ing.note == "kosher"

    def test_from_dict_provenance_case_insensitive(self):
        d = {"name": "x", "qty": "1", "unit": "g", "provenance": "FITTED"}
        assert Ingredient.from_dict(d).provenance is Provenance.FITTED

    def test_from_dict_invalid_provenance_raises(self):
        d = {"name": "x", "qty": "1", "unit": "g", "provenance": "guessed"}
        with pytest.raises(ValueError):
            Ingredient.from_dict(d)

    def test_from_dict_missing_required_key_raises(self):
        with pytest.raises(KeyError):
            Ingredient.from_dict({"name": "x"})

    def test_frozen(self):
        ing = Ingredient("egg", "2", "whole", Provenance.MEASURED)
        with pytest.raises(AttributeError):
            ing.qty = "3"

    def test_json_serializable(self):
        ing = Ingredient("butter", "100", "g", Provenance.FITTED)
        text = json.dumps(ing.to_dict())
        got = Ingredient.from_dict(json.loads(text))
        assert got == ing

    def test_provenance_string_in_dict(self):
        ing = Ingredient("x", "1", "g", Provenance.MEASURED)
        assert isinstance(ing.to_dict()["provenance"], str)
        assert ing.to_dict()["provenance"] == "measured"


class TestRecipe:

    def _recipe(self, **overrides):
        defaults = dict(
            id="test-1",
            title="Test Recipe",
            ingredients=(
                Ingredient("milk", "2", "cups", Provenance.MEASURED),
                Ingredient("vanilla", "1", "tsp", Provenance.ASSUMED),
            ),
            steps=("heat milk", "add vanilla"),
        )
        defaults.update(overrides)
        return Recipe(**defaults)

    def test_to_dict_round_trip(self):
        recipe = self._recipe()
        d = recipe.to_dict()
        got = Recipe.from_dict(d)
        assert got == recipe

    def test_to_dict_shape(self):
        recipe = self._recipe()
        d = recipe.to_dict()
        assert d["id"] == "test-1"
        assert d["title"] == "Test Recipe"
        assert isinstance(d["ingredients"], list)
        assert isinstance(d["steps"], list)
        assert len(d["ingredients"]) == 2
        assert len(d["steps"]) == 2

    def test_from_dict_missing_steps_defaults_empty(self):
        d = {
            "id": "r1",
            "title": "No Steps",
            "ingredients": [
                {"name": "x", "qty": "1", "unit": "g", "provenance": "measured"},
            ],
        }
        recipe = Recipe.from_dict(d)
        assert recipe.steps == ()

    def test_from_dict_missing_id_raises(self):
        with pytest.raises(KeyError):
            Recipe.from_dict({"title": "X", "ingredients": []})

    def test_frozen(self):
        recipe = self._recipe()
        with pytest.raises(AttributeError):
            recipe.title = "Changed"

    def test_provenance_is_weakest_ingredient(self):
        recipe = self._recipe()
        assert recipe.provenance() is Provenance.ASSUMED

    def test_provenance_all_measured(self):
        recipe = self._recipe(ingredients=(
            Ingredient("a", "1", "g", Provenance.MEASURED),
            Ingredient("b", "2", "g", Provenance.MEASURED),
        ))
        assert recipe.provenance() is Provenance.MEASURED

    def test_provenance_single_ingredient(self):
        recipe = self._recipe(ingredients=(
            Ingredient("a", "1", "g", Provenance.FITTED),
        ))
        assert recipe.provenance() is Provenance.FITTED

    def test_provenance_empty_ingredients_raises(self):
        recipe = self._recipe(ingredients=())
        with pytest.raises(ValueError):
            recipe.provenance()

    def test_json_full_round_trip(self):
        recipe = self._recipe()
        text = json.dumps(recipe.to_dict())
        got = Recipe.from_dict(json.loads(text))
        assert got == recipe

    def test_ingredients_are_tuple(self):
        recipe = self._recipe()
        assert isinstance(recipe.ingredients, tuple)

    def test_steps_are_tuple(self):
        recipe = self._recipe()
        assert isinstance(recipe.steps, tuple)

    def test_ingredients_in_dict_are_list(self):
        recipe = self._recipe()
        d = recipe.to_dict()
        assert isinstance(d["ingredients"], list)
        assert isinstance(d["steps"], list)
