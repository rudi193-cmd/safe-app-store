# Fresh review — The Forge design branch (2026-07-31)

**Branch:** `claude/repo-test-run-a8lt94`  
**Artifact:** `docs/design/the-forge.md` (~740 lines)  
**Tip reviewed:** `ac46b98` (post-review fixes: D11 identity, D4 custody, D3 content, D5 allowlist)  
**Reviewer context:** Nestor sibling repo (`master` after PR #26); no implementation in this branch.

**Scope:** Design log only — no `the_forge/` code, no `sap_gate.py`, Kart not wired as a dependency. Judge as architecture and honesty, not shippable product.

---

## Verdict

**Strong as a flagship design doc** for SAFE: it names real gaps (missing `sap-gate`, Kart not in-repo, willow single-operator), commits to **promotion as The Forge** (D13), and separates **manifest trust (Sigstore)** from **pedagogy memory (Nestor + py-fsrs)**. The second review pass materially improved security posture (default-deny MCP, store-minted `builder_id`, D3 “where not what” + AST floor, honest D4 custody).

**Not “we know how to build v1” yet** until: seam **plan schema**, **allowlists for non-Nestor MCPs**, **nested `apps/<builder_id>/…` vs catalog / CLAUDE.md rule 10**, and **Kart as a real dependency** are resolved or explicitly deferred in a **scope cut**.

---

## What’s working well

1. **Trust model is coherent after fixes.** D1 (store is authority) + D11 (GitHub = authenticator, not `builder_id`) + D5 (explicit allowlist, Nestor as reference) fit together. That closes the “GitHub owns the namespace” hole.

2. **D3 is no longer hand-wavy.** Pre-crossing AST scan (vault-leak pattern) + **never import/execute tenant code host-side** is the right norm and matches how `promote_check` already behaves.

3. **D4 is intellectually honest.** Store-held keys, tamper-evidence not builder non-repudiation, and a **separate signing-event ledger** for rotate/compromise timing — without pretending static cosign is Fulcio. That’s better than the first “Sigstore gives rotation” adoption bullet.

4. **D12 + Nestor inventory** align with **Nestor `master`**: serve vs ui, `_ledger_preflight`, `reject_match` / `reject_pair`, `promote_check`, import downgrade — good cross-repo wiring.

5. **D13** (injected host, inversion from day one) matches how Nestor/Jeles shipped and avoids a permanent monorepo flagship.

6. **Open / next** is unusually good: scope-cut option, Kart gap, rule 10, prompt injection, cost — not buried.

---

## Internal doc drift (fix before treating as canonical)

| Location | Issue |
|----------|--------|
| **D4 opening** | Still says “shaped on `nestor.signing` / `nestor.keyring`” — **Adopted** says **Sigstore** + signing-event ledger. |
| **Reused patterns** | “Nestor signing — concrete shape for **D4**” contradicts Sigstore adoption. Should point at **D12** / ledger *pattern*, not D4 crypto. |
| **Adopted dependencies (D4 bullet)** | Claims static Sigstore delivers “rotate-vs-compromise semantics D4 wants” — **D4’s fix** says static mode does *not*; ledger does. |
| **D6** | `tenant_id` / `saps1/tenant-<id>` vs D11 **`builder_id`** — align naming (`builder-<id>` everywhere). |
| **Early audit (Nestor)** | Nestor as “prior art for the **gate**” — add redirect: D4 = Sigstore; Nestor = D12 / serve pattern. |

---

## Substantive gaps (still open)

### P0 — blocks any honest v1

1. **`apps/<builder_id>/<name>/` vs CLAUDE.md rule 10** (`app_id = directory name`, `make run app=<name>`). Design admits it; **catalog, promote_check paths, dev-fallback `app_id`** unresolved.

2. **Kartikeya not a dependency**; `seam_install` uses optional `bwrap`. D2/D3 assume Kart. v1 either **declares Kart + fail-closed** or scope cut says “bwrap-only prototype.”

3. **D3 plan format** — still TBD. Without schema for file writes and staged MCP calls, Casbin + seam can’t be implemented.

### P1 — security / ops before strangers

4. **D5 allowlists** — Nestor documented; **willow-mcp, GitHub, LiteLLM** not. “Register server without allowlist → refuse” should be explicit in D5.

5. **Multiple audit trails** — D3 seam, D4 signing-event ledger, D12 Nestor ledger, consent/FRANK elsewhere. One “which audit answers which question” table would help operators.

6. **Prompt injection** — D3 AST floor doesn’t address **tool-result / KB poisoning** steering the plan. KB and MCP reads are **untrusted planner input**.

7. **Per-builder Nestor storage** — document **one `nestor.db` per `builder_id` vs shared DB**; shared DB + domains is weaker if the seam mis-scopes once.

### P2 — product / economics

8. **D8 decision boundary** + **checkpoint fatigue** — undefined; py-fsrs needs a stable `decision_type` taxonomy.

9. **D7 cost** — permission ≠ budget for cloud fallback.

10. **Scope cut** (seam + Kart + LiteLLM, defer D9/D12) vs **multi-tenant day one** — pick v1 or label D6/D11 phase 2.

---

## Nestor-specific notes

- **D12 `EntityResolver`** is a workable metaphor; checkpoints may fit **`nestor_match` + `SemanticMatcher` + `domain=f"builder:{id}"`** or sealed Q→A pairs better than alias graphs. Elevate the inventory “checkpoint Q→A” bullet in D12.

- **D5:** copy **tool names** from `nestor serve`, not inferred schema shapes, into per-server allowlists.

- **D9 + py-fsrs:** needs a stable **`decision_type` key** or FSRS cards won’t key cleanly.

- **Dogfood on `master`:** `promote_check.py … --record` for Nestor when implementation starts (`store_refit_plan.md`).

---

## Comparison to `master`

`master` has store refit (#139), `promote_check --record`, vault D8. This branch **adds design only** — merge is low **code** risk; it’s a large **product** commitment on paper.

---

## Suggested follow-ups (design repo)

1. Editing pass for D4 / Reused patterns / Adopted / D6 naming drift.  
2. Appendix: `app_id` / catalog / nested `apps/` (or defer nested paths in v1).  
3. Header: **scope-cut v1** or **Kart required in pyproject, fail closed**.  
4. PR for `the-forge.md` (+ this review), design-only.

---

*Posted from Nestor-side review session; complements `docs/design/the-forge.md` on the same branch.*
