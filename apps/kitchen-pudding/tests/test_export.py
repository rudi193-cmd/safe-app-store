from __future__ import annotations

import json

from kitchen_pudding.export import to_json, to_text
from kitchen_pudding.models import Ingredient, Recipe
from kitchen_pudding.provenance import Provenance


def _recipe(**overrides):
    defaults = dict(
        id="test-1",
        title="Test Recipe",
        ingredients=(
            Ingredient("flour", "2", "cups", Provenance.MEASURED),
            Ingredient("sugar", "1", "tbsp", Provenance.ASSUMED, note="guessed"),
        ),
        steps=("mix", "bake"),
        tags=("dessert", "quick"),
    )
    defaults.update(overrides)
    return Recipe(**defaults)


def test_to_text_includes_title():
    text = to_text(_recipe())
    assert "Test Recipe" in text
    assert "==========" in text


def test_to_text_includes_ingredients():
    text = to_text(_recipe())
    assert "2 cups flour" in text
    assert "1 tbsp sugar" in text


def test_to_text_includes_provenance():
    text = to_text(_recipe())
    assert "[measured]" in text
    assert "[assumed]" in text


def test_to_text_includes_notes():
    text = to_text(_recipe())
    assert "(guessed)" in text


def test_to_text_includes_steps():
    text = to_text(_recipe())
    assert "1. mix" in text
    assert "2. bake" in text


def test_to_text_includes_tags():
    text = to_text(_recipe())
    assert "Tags: dessert, quick" in text


def test_to_text_no_tags():
    text = to_text(_recipe(tags=()))
    assert "Tags:" not in text


def test_to_text_no_steps():
    text = to_text(_recipe(steps=()))
    assert "Steps" not in text


def test_to_text_overall_provenance():
    text = to_text(_recipe())
    assert "Provenance: assumed" in text


def test_to_json_round_trips():
    recipe = _recipe()
    output = to_json(recipe)
    parsed = json.loads(output)
    restored = Recipe.from_dict(parsed)
    assert restored == recipe


def test_to_json_valid_json():
    output = to_json(_recipe())
    data = json.loads(output)
    assert data["id"] == "test-1"
    assert len(data["ingredients"]) == 2
