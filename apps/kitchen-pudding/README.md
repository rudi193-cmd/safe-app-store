# kitchen-pudding

Local-first recipe store. The one thing it does that Mealie, Tandoor, and
KitchenOwl don't: every ingredient carries a provenance tag — `measured`,
`fitted`, or `assumed` — and a recipe's overall trustworthiness is the
**weakest** ingredient in it, via `min()`, not an average.

Not a fork of any of those. All three are AGPLv3; see
`safe-app-manifest.json`'s `notes.not_a_fork` for why that ruled them out as
a base rather than just a comparison.

## Run it

```bash
python app.py add pud-1 --title "Sociotechnocratic Pudding" \
  --ingredient "milk:2:cups:measured" \
  --ingredient "vanilla:1:tsp:assumed:handwritten card, unreadable qty" \
  --step "heat milk" --step "whisk in vanilla"

python app.py show pud-1
python app.py list
python app.py correct pud-1 1 provenance measured --note "card was legible after all"
```

`add` refuses to overwrite an existing recipe id. `correct` never touches the
original file — it appends to a correction log beside it, and `show`/`list`
replay corrections over the original to produce the current view. `show`
tells you the correction count exists; it does not hide that a recipe has
been amended.

## Storage

One JSON file per recipe plus one append-only `.jsonl` correction log per
recipe, under the shared vault (`libs/vault-paths`; falls back to
`~/.willow/store/kitchen-pudding/` if that library isn't installed). No
network access — `safe-app-manifest.json` declares `"network": "none"`.

## Tests

```bash
python -m pytest tests/ -q
```

Covers both real mechanisms, not just CLI output: `test_store.py::test_correct_does_not_change_the_original_file_on_disk`
is the gate that would go red if `correct()` were ever "simplified" into an
in-place overwrite, and `test_provenance.py::test_aggregate_single_assumed_ingredient_drags_down_a_large_recipe`
is the one that would go red if aggregation quietly became a mean instead of
a `min()`.

## Status

Playground build, `state: building` (`stores/python/stored/kitchen-pudding.json`).
Not in the store's CI matrix yet — see `docs/PRODUCT_PLAN.md` for what's
built versus open.
