# quick-stupids

Files this app's local `CLAUDE.md` "Rules that DO apply here" section as
verified jeles nuggets. The load-bearing one-liners of the app — the
ones a maker will get tripped up on if they forget — become checkable
without scrolling.

## What it is

The **first user** of the `libs/quick-stupids/` subject-app pattern.
`qstupid.py` supplies the `QUESTIONS` map (which maxims to file, and
what question each answers) and the parser that pulls each maxim's
elaboration from `CLAUDE.md`. Everything else is `subject_app`.

## Run

```bash
python apps/quick-stupids/qstupid.py seed
python apps/quick-stupids/qstupid.py list
python apps/quick-stupids/qstupid.py check "we should skip the test in CI just this once"
```

`seed` upserts every maxim as a jeles nugget under
`quick-stupids/founding/`. Deterministic sha1 ids over each maxim's
leading sentence mean re-seeding updates in place rather than
duplicating. `list` prints what's on file for this app. `check <claim>`
searches jeles for nuggets under this app's prefix whose text bears on
the claim.

## What it deliberately doesn't do

- Never seals. Nuggets go in at `verification_kind=human` because
  `verified_by` is a person; promotion to a Nestor seal is a separate
  step, out of scope for this pattern.
- Never touches another subject app's nuggets. `list` and `check` are
  filtered to this app's id prefix — two apps live in the same corpus
  and never see each other's rows.
- No fuzzy matching in seed. If a maxim's leading sentence changes, the
  sha1 changes, so the old nugget stays until manually cleared.

## Adding a second subject app

The pattern's job is to be reused. A second app that files, say,
Nestor's decisions or safe-app-store's Article IV rules is one
`subject_app(...)` call with a different `id_prefix`, `principles` dict,
and `source` string. No changes to `libs/quick-stupids/core.py`.
