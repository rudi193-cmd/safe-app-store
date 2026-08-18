# homestead-health — promotion readiness

**Prepared 2026-08-18. Verdict: mechanically ready; the gate dry-runs green.**
What remains is not code — it is the witnessed ratification (`verified_by ≠
author`), the extraction to its own repo, and release scaffolding. This directory
holds the prepared attestation (`promotion.json`) and this assessment; it is
**staged, not live** — `promotion.json` is under `docs/promotion/`, not at the app
root, so `promote_check` does not read it as a live claim until it is moved to the
extracted repo's root (see *The two `[A]` gates* below).

Produced by a fan-out of seven agents (four local reading the store's own gate, the
two promoted siblings, Nestor, and the app itself; three remote scouting willow-mcp,
willow-gate, and Jeles). `verified_by ≠ author` — the build's author cannot verify
it, so the fan-out is the second set of eyes; a human still seals.

## The dry-run — every gate green

`promote_check` run against a scratch extraction (the package + tests + manifest +
this `promotion.json` at the root), 2026-08-18:

```
promoted: true
  witnessed [M]        author='vishwakarma' verified_by='sean' (attested — no seal declared)
  own_repo [A]         https://github.com/rudi193-cmd/homestead-health
  host_repointed [A]   attested
  manifest [M]         safe-app-manifest.json ok
  tests_green [M]      128 passed
  vault_leak [M]       no data leaks (PASS)
  import_pure_core [M] homestead_health: network-free at import
  inversion [M]        host not imported (seams injected)
  semantic_seam [M]    homestead_health.reference_lane:Reader defined
```

## The pivotal finding — the `inversion` gate

The engine pin is **not** a problem, and getting `host` wrong is the one way to
fail a build that is actually clean. `homestead.keep` is an **injected dependency**
(published as `homestead-affairs`, consumed like any library — the way Nestor
depends on `cryptography`), never the "host". Proven empirically:

- `host="homestead-affairs"` → `host_root="homestead"` → **FAILS** (8/9 core files
  import `homestead.keep`).
- `host="safe-app-store"` → `host_root="safe"` → **PASSES** (nothing named `safe` is
  importable; the core reaches into no store internals).

`host` is *what the module was extracted from* — for homestead-health that is the
store monorepo, the law-gazelle→homestead-law path. **`host` must be
`"safe-app-store"`.** The two promoted siblings (`homestead-law`, `homestead-ledger`)
import `homestead.keep` the identical way; the face's own base engine is exempt from
the "one seam file" rule (that rule is for cross-org pins).

## Gate-by-gate

| Gate | Status | Note |
|---|---|---|
| attestation | staged | `promotion.json` prepared here; moves to the repo root at extraction |
| witnessed `[M]` | ✅ floor | `verified_by ≠ author`; the cryptographic seal is **not required** (opt-in `trust` block only) |
| own_repo `[A]` | ⏳ extraction | honest only after `rudi193-cmd/homestead-health` exists |
| host_repointed `[A]` | ⏳ extraction | honest only after the store consumes the extracted package |
| manifest `[M]` | ✅ | `safe-app-manifest.json` present and shaped (freshened — see below) |
| tests_green `[M]` | ✅ | 128 passed / 0 xfailed |
| vault_leak `[M]` | ✅ | no fixed-path data leak (the app's own I-19/I-20 scans are stricter) |
| import_pure_core `[M]` | ✅ | network-free at import (the app's full-walk scan exceeds the gate's) |
| inversion `[M]` | ✅ | `host="safe-app-store"` → passes |
| semantic_seam `[M]` | ✅ | `homestead_health.reference_lane:Reader` resolves |

## The two `[A]` gates, and why the attestation is staged

`own_repo` and `host_repointed` are **attested** gates — `promote_check` checks their
*shape*, not their truth. Filing a live `promotion.json` at the app root today would
have the script report `promoted: true` while `rudi193-cmd/homestead-health` does not
exist and the store has not been repointed — a false claim on two gates the script
cannot catch. So the attestation is staged here and becomes honest at the same commit
that performs the extraction. The dry-run above is a *proof the gates pass given the
extraction*, not a claim the extraction has happened.

## The seal — not required

The `witnessed` floor (`verified_by` set and `≠ author`) is sufficient by design; the
cryptographic seal (`trust` block → `willow_gate.custody` custody ledger + a
verifier-signed checkpoint + `NESTOR_KEYRING`) is opt-in and, once *claimed*,
fail-closed. `willow_gate`/`forge`/`nestor` are not even importable in the build
environment. Given this is health data, a seal would be a defensible *strengthening*
— see `docs/promotion/recon/willow-gate.md` (remote scout) for the recipe — but it is
not a gate requirement.

## Identities (`verified_by ≠ author`)

- **author = `vishwakarma`** — the building agent that wrote the module (the
  *proposer*). The code-author, not the human who commissioned it.
- **verified_by = `sean`** — the human who reviewed this readiness and *ratifies* (the
  disposer). A different hand from the author, which is the whole of §0.2.

Both handles are adjustable; what matters is that the ratifier is not the author.

## What moves, what's added, what's deferred

**Moves as-is:** `homestead_health/` (all modules), `tests/` (incl. `conftest.py`'s
cold-checkout shim), `pyproject.toml`, `requirements.txt`, `README.md` (already
matches the sibling shape), `LICENSE`, `docs/` — **including `docs/audits/`, the
adversarial-review trail that makes `verified_by ≠ author` credible; it is stronger
than either promoted sibling's and must travel with the code.**

**Added at extraction (release scaffolding — the real gap, not engineering):**
hatch-vcs dynamic version (the pyproject already anticipates it), `NOTICE`,
`CHANGELOG.md`, `release-please-config.json` + manifest, `.github/workflows/`,
`tools/changelog_dedup.py`, `[project.urls]` repointed to the new repo, and a
`test_invariants_release.py` once those files exist. `homestead-ledger` is the more
complete file-shape template.

**Deliberately NOT copied from the siblings:** the `<0.2` engine cap is intentional
(health carries the L4/L5 medical rungs; do not widen to the siblings' `<1.0` without
checking the engine's releases), and there is **no UI surface yet** — so promote
*library-only* first (a `promote_check`-legal shape) and skip the `packaging/` +
artifact CI that would build a binary that does not exist.

## Open — pending the remote scouts

- **The reference lane's reader — inject Jeles's or keep the grown one?** The plan's
  one open provenance question. The grown `reference_lane.Reader` (term-overlap,
  zero-dependency, no network) passes the `semantic_seam` gate as-is and fits the
  "ship the reader, corpus injected" pattern — but it is *lexical*, not embeddings.
  The Jeles remote scout's recommendation lands in
  `docs/promotion/recon/jeles.md`; decision deferred to it.
- **willow-mcp governance / willow-gate seal recipe** — the two other remote scouts
  (`docs/promotion/recon/willow-mcp.md`, `docs/promotion/recon/willow-gate.md`).

## The one gate that is a person's, not a script's

Everything mechanical is met or a scaffolding edit. The real gate is the human seal:
a second hand attesting they reviewed what the building agent proposed. That is
`sean`'s to give — this document exists so that review has something complete to
stand on.
