"""CLI: add, list, show, correct, search, export, import.

`make run app=kitchen-pudding` calls this with no arguments, which prints
usage and exits 0 rather than erroring — same "runnable with no args" shape
as the store's other CLI-first apps.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from kitchen_pudding.export import to_json, to_text
from kitchen_pudding.models import Ingredient, Recipe
from kitchen_pudding.provenance import Provenance
from kitchen_pudding.search import search
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
    tags = tuple(t.strip() for t in args.tag if t.strip())
    recipe = Recipe(
        id=args.id, title=args.title, ingredients=ingredients,
        steps=tuple(args.step), tags=tags,
    )
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
    if recipe.tags:
        print(f"  tags: {', '.join(recipe.tags)}")
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


def _cmd_search(args: argparse.Namespace, store: RecipeStore) -> int:
    max_prov = Provenance.parse(args.max_provenance) if args.max_provenance else None
    min_prov = Provenance.parse(args.min_provenance) if args.min_provenance else None
    results = search(
        store,
        title=args.title,
        ingredient=args.ingredient_name,
        tag=args.tag_filter,
        max_provenance=max_prov,
        min_provenance=min_prov,
    )
    if not results:
        print("(no matching recipes)")
        return 0
    for recipe in results:
        tags = f"  [{', '.join(recipe.tags)}]" if recipe.tags else ""
        print(f"{recipe.id}\t{recipe.title}\t{recipe.provenance()}{tags}")
    return 0


def _cmd_export(args: argparse.Namespace, store: RecipeStore) -> int:
    try:
        recipe = store.current(args.id)
    except UnknownRecipe:
        print(f"error: no recipe {args.id!r}", file=sys.stderr)
        return 1
    if args.format == "json":
        output = to_json(recipe)
    else:
        output = to_text(recipe)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"exported {recipe.id!r} to {args.output}")
    else:
        print(output, end="")
    return 0


def _cmd_import(args: argparse.Namespace, store: RecipeStore) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 1
    try:
        recipe = store.import_from_file(path)
    except FileExistsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (KeyError, ValueError) as exc:
        print(f"error: invalid recipe file: {exc}", file=sys.stderr)
        return 1
    print(f"imported {recipe.id!r} ({recipe.provenance()} overall)")
    return 0


def _cmd_tags(args: argparse.Namespace, store: RecipeStore) -> int:
    tags = store.list_tags()
    if not tags:
        print("(no tags yet)")
        return 0
    for tag in tags:
        print(tag)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kitchen-pudding")
    sub = parser.add_subparsers(dest="command")

    add = sub.add_parser("add", help="add a new recipe")
    add.add_argument("id")
    add.add_argument("--title", required=True)
    add.add_argument("--ingredient", action="append", default=[], metavar="name:qty:unit:provenance[:note]")
    add.add_argument("--step", action="append", default=[])
    add.add_argument("--tag", action="append", default=[])
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

    srch = sub.add_parser("search", help="search recipes by title, ingredient, tag, or provenance")
    srch.add_argument("--title", default=None)
    srch.add_argument("--ingredient-name", default=None)
    srch.add_argument("--tag-filter", default=None, metavar="TAG")
    srch.add_argument("--max-provenance", default=None, choices=["assumed", "fitted", "measured"])
    srch.add_argument("--min-provenance", default=None, choices=["assumed", "fitted", "measured"])
    srch.set_defaults(func=_cmd_search)

    exp = sub.add_parser("export", help="export a recipe to text or JSON")
    exp.add_argument("id")
    exp.add_argument("--format", choices=["text", "json"], default="text")
    exp.add_argument("--output", "-o", default=None, metavar="FILE")
    exp.set_defaults(func=_cmd_export)

    imp = sub.add_parser("import", help="import a recipe from a JSON file")
    imp.add_argument("file")
    imp.set_defaults(func=_cmd_import)

    tagsp = sub.add_parser("tags", help="list all tags in use")
    tagsp.set_defaults(func=_cmd_tags)

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
