# CI Design — SAFE App Store

Two tiers. The store has a floor every push must clear; individual apps add
their own ceilings on top.

## Tier 1 — the store floor (`.github/workflows/store-ci.yml`)

Runs on every push to `master` and every pull request, no path filters —
plus a daily scheduled run (and `workflow_dispatch`) to catch drift no push
would surface: dependency point releases, runner-image changes, apps that go
quiet for weeks. Single OS (ubuntu), single Python (3.12) — the floor is
about repo integrity, not portability.

| Gate | Tool | What it proves |
|------|------|----------------|
| catalog | `tools/catalog_lint.py --strict` | `catalog.json` and `apps/` agree: valid statuses, `app_id` = directory name (rule 8), no unregistered app dirs, no dangling paths (archived and external-repo entries exempt, rule 4), beta/stable apps carry a matching `safe-app-manifest.json` |
| vault-clean | `tools/vault_leak_lint.py --strict` | No app persists user *data* to a fixed home path (D8); config/cache in home is classified, not flagged (D8.1) |
| compile | `python -m compileall` | Every `.py` in `apps/`, `tools/`, `scripts/`, and the repo root byte-compiles |
| app-tests | `pytest`, one matrix leg per app | Suites that have no dedicated workflow: civics-check, law-gazelle, the-squirrel, utety-chat |

## Tier 2 — per-app workflows

Path-filtered, OS/Python-matrixed workflows for apps whose surface warrants
it: `ask-jeles.yml`, `private-ledger.yml`, `source-trail.yml`,
`story-timeline.yml`. They only run when their app (or the workflow itself)
changes.

## Where a new app's tests go

- Tests exist, plain `requirements.txt`, no OS-specific surface → add the app
  to the `app-tests` matrix in `store-ci.yml`. If the tests need a dep the app
  itself treats as optional (utety-chat's TUI tests need `textual`), declare it
  as `test-deps` in a matrix `include` — don't add it to the app's
  requirements. And verify the suite in a *clean* venv first: a shared local
  venv can mask a missing dependency that a fresh CI runner will catch.
- App needs an OS matrix, editable installs, or heavier setup → give it its
  own path-filtered workflow (copy `story-timeline.yml` as the template).
- No tests yet → the app is still covered by the catalog, vault-clean, and
  compile gates. (`dating-wellbeing`'s suite is a placeholder — add it to the
  matrix when real tests land.)

## Deliberate non-gates

- `tools/receipt_gate.py` — its `install_verified`/`launch_verified` gates are
  PENDING (unimplemented), so in strict mode it can only report, not gate.
  Wire it in when the seam installer proofs land.
- `.willow/store/` sync (rule 5) — that directory is not in the repo yet;
  there is nothing in-tree to compare against `catalog.json`.
