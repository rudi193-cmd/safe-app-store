# The Forge — promotion / enrollment plan (design, 2026-08-11)

> Enrollment prep for lifting The Forge out of the `stores/` monorepo into its
> own standing repo. "The maker enrolls; someone else promotes" (§0.2) — this
> doc is the enrollment (author's hand); ratification (`verified_by ≠ author`)
> is a different seat. Every gate below is `stores/promote_check.py`, run
> fail-closed. Facts marked *(grounded)* were measured, not assumed.

## STATUS — enrollment done (2026-08-11)

Both forks settled (model side as a library; real package imports). The package
was extracted (`tools/extract_forge_pkg.py`) and pushed to
**`rudi193-cmd/forge`, branch `claude/continuing-projects-o0jm9a`** — NOT the
default branch, so merging it is the ratifier's act.

**Structured to the homestead convention** (per USER: "look at the root
homestead folder"): the base repo holds ONLY the engine, **flat in `forge/`**
(as `homestead` holds `homestead.keep`), and all runtime state hangs off one
shared home, **`~/.forge`** (override `FORGE_HOME`), resolved in one place
(`forge/paths.py`) the way homestead-law and homestead-ledger share
`~/.homestead`. Modules that pin the engine are separate repos, later. 18 engine
modules flat + `paths.py` + vendored `_ids.py`; `tests/` (12 files); README in
the house style; `pyproject.toml` + `promotion.json`. `model_egress`'s
`socket`/`urlparse` are moved to lazy so the whole flat package is network-free
at import (`pure_core = forge`).

`promote_check` run against the pushed tree:

- **PASS** — own_repo, manifest (pyproject, library-clean), tests_green (**154
  passed, 1 skipped** in place), vault_leak, import_pure_core (`forge`
  network-free at import), inversion (host not imported), semantic_seam
  (`forge.checkpoint_memory:CheckpointMemory`), and **`witnessed`** —
  `verified_by = rudi193` (the human operator ratifies; distinct from the author
  `vishwakarma`, §0.2). Recorded on the forge feature branch 2026-08-11.
- **FAIL — the last gate** — `host_repointed` (not true until safe-app-store
  consumes the package). **Held by USER** pending the engine landing on forge's
  default branch, then the repoint (delete the `stores/` model-side modules +
  their tests, declare `the-forge` a dependency — rule 8, code not duplicated).

What remains: (6) land the engine on forge `main` (the ratifying push — auto-
blocked for the author, so it's the operator's act or an explicit grant); (7)
repoint the host and flip `host_repointed`; (8) run `promote_check --record`,
writing `stores/python/promoted/the-forge.json`. Only `host_repointed` is not
yet green — every other gate passes.

## Destination

`rudi193-cmd/Forge` already exists (public, pushable) — promotion is an
extraction *into* it, not a repo to stand up. `own_repo [A]` is satisfied by
`repo_url = https://github.com/rudi193-cmd/Forge` (the gate only requires a
repo_url that does not contain `safe-app-store`).

## What The Forge physically is — three layers, three trust postures

1. **The sandboxed spine** — `apps/the-forge/src/the_forge/` (cli, plan,
   sandbox_runner, mount_policy, scan, mcp_registry, stub_builder). The
   playground build; runs *under* the trust boundary (D1, contested tier).
2. **The store-side driver** — `stores/forge_build.py`: runs one build through
   the REAL trust boundary, consuming the shared SAFE infra by injection.
3. **The model side** — the work of the last two sessions, all store-side (D1):
   the checkpoint loop (`checkpoint*.py`, `human_loop`, `soil_store`,
   `friction_floor`) and the measuring panel (`measure_panel`, `instrument_*`,
   `calibration*`) and model routing (`model_route`, `model_egress`).

The shared SAFE trust-boundary infra — `sap_gate` (D4), `principal` (D2/D11),
`seam` (D3/D4), `session` (D6/D11), `quota` (D6) — is the **host's** substrate.
It is injected into a build; it is NOT part of the Forge extraction. Rule 8's
inversion: the host imports the Forge, never the reverse.

## FORK 1 — what is the promotion unit? (needs a design call)

- **(A) Promote the model side as a library-clean core.** The
  refuse-a-confident-wrong-answer harness (checkpoint loop + measuring panel +
  calibration), with the trust-boundary seams injected. The spine (layers 1–2)
  stays in the store as the host's build-integration point. Smallest pure unit,
  cleanest inversion, matches "library-clean like Nestor/Jeles."
- **(B) Promote the whole Forge** (spine + driver + model side) with the shared
  SAFE infra injected. Larger, and the sandboxed spine is deliberately
  contested-tier (D1) — promoting it blurs the tier wall it was built to honor.

Recommendation: **(A)**. It is the honest library-clean unit, it is what the
five gates below already nearly pass, and it leaves the D1 tier wall intact.

## The ten gates — grounded current state

| Gate | Kind | State | What's needed |
|------|------|-------|---------------|
| `attestation` | — | absent | write `promotion.json` (below) |
| `witnessed [M]` | M | **not mine** | `verified_by` set, ≠ `author` — a second seat |
| `own_repo [A]` | A | ready | `repo_url = …/Forge` |
| `host_repointed [A]` | A | pending | host must consume the package (below) |
| `manifest [M]` | M | easy | ship `pyproject.toml` with `[project].name` (library-clean path) |
| `tests_green [M]` | M | **the work** | package must run `cd <cand> && pytest` green; tests travel with it |
| `vault_leak [M]` | M | **PASS *(grounded)*** | ran the store's own lint over the core modules → verdict PASS |
| `import_pure_core [M]` | M | ready w/ designation | only `model_egress.py` imports `socket`/`urllib` *(grounded)*; designate it the impure adapter, keep it out of `pure_core` (exactly Jeles' `willow_mcp_client` pattern) |
| `inversion [M]` | M | ready | core does not import the host; `host = safe-app-store`, host_root `safe` appears in no top-level import |
| `semantic_seam [M]` | M | identified | `checkpoint_memory:CheckpointMemory` — loose recognition over the maker's sealed-decision corpus (injected via Nestor) |

## FORK 2 — the packaging refactor (the real mechanical work)

13 of the store-side modules load their siblings via
`importlib.util.spec_from_file_location` *(grounded)*, a monorepo-in-place
device. As an installed package (`cd <cand> && pytest` must pass, per
`tests_green`), those become normal package imports. Two ways:

- **(i) Real package** — a `forge/` package with ordinary relative imports; the
  cleanest end state, but touches every spec-load site and every test's loader
  preamble.
- **(ii) Keep spec-load, ship self-contained** — the modules already resolve
  siblings by path relative to the package root, so a package that carries them
  plus its `tests/` may pass in place with a thinner diff.

Recommendation: **(i)** — the spec-load pattern exists only to survive the
monorepo; extraction is exactly when it should retire. But this is the largest
diff of the enrollment, so it is its own bite, sized once Fork 1 is settled.

## The `promotion.json` the author writes (enrollment)

```json
{
  "app_id":        "the-forge",
  "author":        "vishwakarma",
  "verified_by":   "",                 // ← a second seat fills this (§0.2)
  "repo_url":      "https://github.com/rudi193-cmd/Forge",
  "host":          "safe-app-store",
  "core_module":   "forge",
  "pure_core":     "forge",            // model_egress excluded as the impure adapter
  "semantic_seam": "checkpoint_memory:CheckpointMemory",
  "host_repointed": false,             // ← flips true once the host consumes the package
  "major": "python"
}
```

`verified_by` and `host_repointed` are deliberately left un-passing: the author
cannot ratify their own work, and the host is not repointed until the package
exists to be consumed.

## `host_repointed` — the last mechanical gate

After extraction, `safe-app-store` imports the Forge package instead of housing
the code. Concretely: the store-side `stores/*.py` Forge modules become a thin
re-export of (or are deleted in favor of) the installed `forge` package, and
`stores/forge_build.py` imports it. Only then is `host_repointed: true` honest.

## Ordered bites

1. **This doc** — the grounded plan (done).
2. **Settle Fork 1 + Fork 2** with the user (unit = model side? refactor =
   real package?).
3. **Packaging refactor** — shape the chosen unit into `forge/` with real
   imports + its own `tests/`, `pyproject.toml`; `cd forge && pytest` green.
4. **Dry-run `promote_check`** against the packaged candidate; close every
   mechanical gate except `witnessed`/`host_repointed`.
5. **Extract into `rudi193-cmd/Forge`** (needs the repo added to session scope).
6. **Repoint the host**, flip `host_repointed`.
7. **Hand off for ratification** — a second seat sets `verified_by`, runs
   `promote_check --record`, which writes `stores/python/promoted/the-forge.json`.

## Not in this bite

- Finishing the model loop (decision-extraction + the build loop) — the user's
  "2". It can proceed in parallel; the promotable unit grows to include it when
  it lands, or promotes after. Sequencing is Fork-1-adjacent.
- Any ratifying action — structurally another hand.
