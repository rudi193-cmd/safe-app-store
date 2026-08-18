"""JSON-file recipe store, local-first, under the shared vault.

Two rules this module exists to enforce, not just to document:

1. **The original record never changes.** ``add()`` refuses to overwrite an
   existing id. A recipe file written once stays exactly what was written.
2. **A correction lands beside the record, never on top of it**
   (CLAUDE.md). ``correct()`` appends to a separate append-only log;
   :meth:`RecipeStore.current` replays that log over the original to produce
   the current view. The original and the correction are both still there —
   you can always ask "what did this recipe originally claim?" separately
   from "what do we believe now?"
"""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from kitchen_pudding.models import Ingredient, Recipe
from kitchen_pudding.provenance import Provenance

try:
    import vault_paths as _vp
except ImportError:  # not yet installed via `pip install -e libs/vault-paths`
    import sys

    _canonical_src = Path(__file__).resolve().parents[3] / "libs" / "vault-paths" / "src"
    if not _canonical_src.is_dir():
        raise ImportError(
            "vault_paths is not installed and libs/vault-paths isn't reachable "
            "from this checkout. Run `pip install -e libs/vault-paths` from the "
            "store root — where the vault lives is that library's one decision "
            "to own, not a second copy of it here."
        ) from None
    sys.path.insert(0, str(_canonical_src))
    import vault_paths as _vp  # type: ignore[no-redef]


def _default_root() -> Path:
    return _vp.app_dir("kitchen-pudding")


_VALID_FIELDS = {"qty", "unit", "provenance", "note"}


class UnknownRecipe(KeyError):
    pass


class RecipeStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root is not None else _default_root()
        self.recipes_dir = self.root / "recipes"
        self.recipes_dir.mkdir(parents=True, exist_ok=True)

    def _recipe_path(self, recipe_id: str) -> Path:
        return self.recipes_dir / f"{recipe_id}.json"

    def _corrections_path(self, recipe_id: str) -> Path:
        return self.recipes_dir / f"{recipe_id}.corrections.jsonl"

    # ── writes ──────────────────────────────────────────────────────────

    def add(self, recipe: Recipe) -> None:
        path = self._recipe_path(recipe.id)
        if path.exists():
            raise FileExistsError(
                f"recipe {recipe.id!r} already exists — corrections go through "
                f"correct(), the original record is never overwritten"
            )
        path.write_text(json.dumps(recipe.to_dict(), indent=2, sort_keys=True) + "\n")

    def correct(self, recipe_id: str, index: int, field_name: str, value: str, note: str) -> None:
        if field_name not in _VALID_FIELDS:
            raise ValueError(f"field must be one of {sorted(_VALID_FIELDS)}, got {field_name!r}")
        original = self.get_original(recipe_id)
        if not (0 <= index < len(original.ingredients)):
            raise IndexError(f"recipe {recipe_id!r} has {len(original.ingredients)} ingredients, index {index} out of range")
        if field_name == "provenance":
            Provenance.parse(value)  # validate before it lands in the log
        entry = {
            "index": index,
            "field": field_name,
            "value": value,
            "note": note,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        with self._corrections_path(recipe_id).open("a") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")

    # ── reads ───────────────────────────────────────────────────────────

    def get_original(self, recipe_id: str) -> Recipe:
        path = self._recipe_path(recipe_id)
        if not path.exists():
            raise UnknownRecipe(recipe_id)
        return Recipe.from_dict(json.loads(path.read_text()))

    def get_corrections(self, recipe_id: str) -> list[dict]:
        path = self._corrections_path(recipe_id)
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line]

    def current(self, recipe_id: str) -> Recipe:
        """The original recipe with every correction replayed, in order, on
        top of it. Does not touch the files on disk — a fresh read every
        time, so a bug here can never corrupt the record it's reading."""
        recipe = self.get_original(recipe_id)
        ingredients = list(recipe.ingredients)
        for entry in self.get_corrections(recipe_id):
            i = entry["index"]
            field_name = entry["field"]
            value = entry["value"]
            if field_name == "provenance":
                value = Provenance.parse(value)
            ingredients[i] = replace(ingredients[i], **{field_name: value})
        return replace(recipe, ingredients=tuple(ingredients))

    def list_ids(self) -> list[str]:
        return sorted(p.stem for p in self.recipes_dir.glob("*.json"))

    def list_tags(self) -> list[str]:
        tags: set[str] = set()
        for recipe_id in self.list_ids():
            recipe = self.current(recipe_id)
            tags.update(recipe.tags)
        return sorted(tags)

    def import_from_file(self, path: Path) -> Recipe:
        """Import a recipe from a JSON file on disk. Same ``add()`` rules
        apply: refuses to overwrite an existing id."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        recipe = Recipe.from_dict(data)
        self.add(recipe)
        return recipe
