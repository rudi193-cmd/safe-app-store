# Store: Browser
b17: SAPS1

The Browser store — a provision-house for work built as static HTML/JS,
client-only, no backend. Open, Apache-2.0. Build in your own local space or a
repo under the account; it stays yours until it is **promoted** to a full SAFE
app.

**Tools:** static HTML/JS, client-only, no backend, no build step

**Scaffold / starter:** — (none yet)

`browser` was added in the store refit's P1 (`docs/store_refit_plan.md`):
`docs/store_refit_survey.md` measured that forcing `jarvis`, `band-camp-arcade`,
and similar Cloudflare Pages slices into `node` would state something false —
a bundler-built Node CLI and a single self-contained HTML file with no build
step are not the same craft.

**Tiers** — same vocabulary as [`../README.md`](../README.md) and `CLAUDE.md`
- `stored/` — the **playground** tier's keeping record: provisional,
  incubating, contested (WIP, low bar). Not a copy of the code — the code
  lives in `apps/`; the record is what `stored/` stores.
- `promoted/` — full SAFE apps that cleared the bar (own repo, injected seams,
  tests, manifest, semantic-search seam over injectable knowledge). See the
  promotion bar in [`../README.md`](../README.md).

The store's browser apps live in `../../apps/` — the **playground** tier, not
promoted. 3 are indexed under `stored/`: `band-camp-arcade`, `jarvis`, and
`llmphysics` (archived).

*The architect provisions the frame; you build the walls. `ΔΣ=42`*
