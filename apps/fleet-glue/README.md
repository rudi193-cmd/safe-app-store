# fleet-glue

Reduces standup friction across **Nestor**, **Jeles**, and **willow-mcp**
without laundering trust.

## Not a shipped organ

This is a **playground build**. The Nestor decision graph, consulted on
placement, ruled `apps/` out for a build that writes to fleet stores
(safe-app-store/CLAUDE.md rule 6). The maker asked to land it here anyway
so we can drive it further before promotion.

The standing pattern for a mature build is `stores/README.md` Article IV:
lift it out into its own repo with injected seams, its own tests, an
import-pure core, and the host repointed as a consumer. Until then, this
directory is the lab.

## What it does

| Piece | Behavior |
|---|---|
| `configure_lab(root)` | One root → `WILLOW_HOME`, `WILLOW_STORE_ROOT`, `NESTOR_DB`, `NESTOR_LEDGER`; mints `NESTOR_SEAL_KEY` → `nestor/seal.key` (chmod 0600) so a second session on the same lab picks it up rather than minting a new one that demotes every sealed row |
| `install()` | Registers the tier-1.5 recognizer through `nestor.cascade.set_tier15_recognizer` — the seam Nestor's decision 0205 added specifically to retire monkeypatching |
| `log_gap(q, topic=)` | Writes to **both** `jeles.corpus` gaps and `willow_mcp.gaps.log(topic, question)` and returns both ids |
| `corroborate_to_draft(...)` | URLs → Nestor draft + evidence rows + one citation warrant |
| `promote_gap_to_jeles(...)` | Answer → nugget; threads the willow `gap_id` through so `resolve` and `mark_promoted` land on the right row (`mark_promoted` is gated on a successful `resolve` — the underlying tool silently returns `None` on a missing id) |
| `advisory_ratify(...)` | Read-only canon door — builds a real `willow_mcp.mem_ratify.RatifyRequest`, returns the `Decision` |
| `conflict_scan(claim)` | Thin wrapper over `jeles.reactions.conflict_scan` with a default corpus-backed searcher |
| `triage_summary()` | Group current pairs into **Seal / Known / Reject / Other** + both gap backlogs |
| `doctor_summary()` | Env + imports + oracle availability + cascade wire + willow doctor |

## What it refuses to do

- Auto-seal from Jeles, lexicon, or willow KB
- Treat a jeles nugget as tier-1 verified
- Bypass the human seal path for tool-oracle routing
- Monkeypatch `cascade.translate_segment` — the seam does it right
- Merge the oracle DB with app memory into one undifferentiated store

## Install

```bash
pip install "nestor-meaning" "jeles" "willow-mcp[nestor]"
pip install -e .
```

## Run

```bash
python app.py                 # dry standup + doctor summary
python app.py --lab ./lab     # explicit lab root
python app.py --lab ./lab --seed-jeles-demo --probe
```

Or from the store root:

```bash
make run app=fleet-glue
```

## Test

```bash
pytest -q
```

The main test is `tests/test_drive.py` — the operator drive script recast
as pytest. It walks a day-in-life, adversarial inputs, idempotency, the
rejection wall, `conflict_scan.apply=True`, and a cross-session
persistence check with a clean-env child process (26 assertions).

## Layout

```
apps/fleet-glue/
  safe-app-manifest.json
  README.md
  pyproject.toml
  requirements.txt
  app.py                  # `make run` entry — configure_lab + install + doctor
  src/fleet_glue/         # the library
    __init__.py
    standup.py
    hooks.py
    gaps_compat.py
    corroborate.py
    promote.py
    conflict.py
    triage.py
  tests/
    test_drive.py         # 26-check operator drive
```

## Recorded shape

The three organs and how fleet-glue speaks to each:

- **Nestor** — via the shipped `nestor.established.install()` (PR #222 /
  decision 0206 seam), plus direct `memory` / `evidence` / `warrant` /
  `cascade.set_ledger_path` calls in `corroborate.py`
- **Jeles** — `jeles.corpus.put_nugget` / `search_nuggets` / `log_gap` /
  `list_gaps` / `list_nuggets`, and `jeles.reactions.conflict_scan`
- **willow-mcp** — `willow_mcp.gaps.log` / `resolve` / `mark_promoted` /
  `list_gaps`, `willow_mcp.mem_ratify.ratify`, `willow_mcp.tool_oracle`
  read-only (available / pending)
