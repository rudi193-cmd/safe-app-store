# quick-stupids

The subject-app pattern. A **subject app** is a fixed
`{question: answer}` set of principles from a named source, filed as
jeles nuggets under a per-app id prefix and tag, with three subcommands:

- `seed`  — upsert the principles as nuggets (deterministic sha1 ids over
  the question mean re-seeding updates in place, never duplicates)
- `list`  — show what's on file under this app's id prefix
- `check <claim>` — search the app's own nuggets for ones that bear on a
  claim

## Use

```python
from quick_stupids.core import subject_app

subject_app(
    prog="qstupid",
    id_prefix="quick-stupids/founding/",
    tags=["founding", "quick-stupids"],
    source="file://CLAUDE.md#rules-that-do-apply-here",
    verified_by="rudi193@gmail.com",
    written_by="apps/quick-stupids/qstupid.py",
    principles={"maxim.": "question?", ...},
    hits_header="That would be filed under:",
    hits_footer="It isn't lost. It's misfiled.",
    no_hits_message="…",
)
```

`principles` is caller-built — parsed from a doc, hardcoded, generated —
so a subject app can front any named source of rules that fits in
`{answer_headline: interrogative_question}` shape.

## What it deliberately doesn't do

- Never seals. Nuggets go in at whatever `verification_kind` jeles gives
  (default `human` when `verified_by` is a person). Promotion to a
  seal is a separate step, out of scope for this pattern.
- No fuzzy matching in seed. Deterministic sha1 over the question means
  re-seeding is upsert, not merge.
- No orchestration across subject apps. Two apps with different
  `id_prefix` values live in the same corpus but never see each other's
  nuggets in `list` or `check` — each app's identity is its prefix.
