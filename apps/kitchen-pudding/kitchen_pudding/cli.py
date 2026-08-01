"""CLI: add, list, show, correct.

`make run app=kitchen-pudding` calls this with no arguments, which prints
usage and exits 0 rather than erroring — same "runnable with no args" shape
as the store's other CLI-first apps.
"""
from __future__ import annotations

import argparse
import sys

from kitchen_pudding.models import Ingredient, Recipe
from kitchen_pudding.provenance import Provenance
from kitchen_pudding.store import RecipeStore, UnknownRecipe


def _parse_ingredient(raw: str) -> Ingredient:
    parts = raw.split(":")
    if len(parts) not in (4, 5):
        raise argparse.ArgumentTypeError(
            f"ingredient must be name:qty:unit:provenance[:note], got {raw!r}"
        )
    name, qty, unit, prov = parts[:4]
    note = parts[4] if len(parts) == 5 else ""
    try:
        provenance = Provenance.parse(prov)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return Ingredient(name=name, qty=qty, unit=unit, provenance=provenance, note=note)


def _cmd_add(args: argparse.Namespace, store: RecipeStore) -> int:
    ingredients = tuple(_parse_ingredient(i) for i in args.ingredient)
    recipe = Recipe(id=args.id, title=args.title, ingredients=ingredients, steps=tuple(args.step))
    try:
        store.add(recipe)
    except FileExistsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"added {recipe.id!r} ({recipe.provenance()} overall)")
    return 0


def _cmd_list(args: argparse.Namespace, store: RecipeStore) -> int:
    ids = store.list_ids()
    if not ids:
        print("(no recipes yet)")
        return 0
    for recipe_id in ids:
        recipe = store.current(recipe_id)
        print(f"{recipe_id}\t{recipe.title}\t{recipe.provenance()}")
    return 0


def _cmd_show(args: argparse.Namespace, store: RecipeStore) -> int:
    try:
        recipe = store.current(args.id)
    except UnknownRecipe:
        print(f"error: no recipe {args.id!r}", file=sys.stderr)
        return 1
    print(f"{recipe.title}  [{recipe.provenance()}]")
    for i, ing in enumerate(recipe.ingredients):
        note = f"  ({ing.note})" if ing.note else ""
        print(f"  {i}. {ing.qty} {ing.unit} {ing.name}  [{ing.provenance}]{note}")
    for step in recipe.steps:
        print(f"  - {step}")
    corrections = store.get_corrections(args.id)
    if corrections:
        print(f"  ({len(corrections)} correction(s) on record — original unchanged)")
    return 0


def _cmd_correct(args: argparse.Namespace, store: RecipeStore) -> int:
    try:
        store.correct(args.id, args.index, args.field, args.value, args.note)
    except (UnknownRecipe, IndexError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"correction recorded for {args.id!r}[{args.index}].{args.field}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kitchen-pudding")
    sub = parser.add_subparsers(dest="command")

    add = sub.add_parser("add", help="add a new recipe")
    add.add_argument("id")
    add.add_argument("--title", required=True)
    add.add_argument("--ingredient", action="append", default=[], metavar="name:qty:unit:provenance[:note]")
    add.add_argument("--step", action="append", default=[])
    add.set_defaults(func=_cmd_add)

    listp = sub.add_parser("list", help="list recipes")
    listp.set_defaults(func=_cmd_list)

    show = sub.add_parser("show", help="show a recipe, corrections applied")
    show.add_argument("id")
    show.set_defaults(func=_cmd_show)

    correct = sub.add_parser("correct", help="append a correction — never overwrites the original")
    correct.add_argument("id")
    correct.add_argument("index", type=int)
    correct.add_argument("field", choices=["qty", "unit", "provenance", "note"])
    correct.add_argument("value")
    correct.add_argument("--note", default="", help="why this correction was made")
    correct.set_defaults(func=_cmd_correct)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    store = RecipeStore()
    return args.func(args, store)


if __name__ == "__main__":
    raise SystemExit(main())
