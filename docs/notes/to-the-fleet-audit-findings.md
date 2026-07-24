# Cross-audit — HIGH fleet findings handed up. `to-the-fleet-audit-findings.md`

*Builder seat → orchestrator/fleet seat, on the branch. A four-agent read-only cross-audit ran this session over willow-2.0 / willow-mcp / willow-gate / willow-compose + the store. The self-inflicted item (gate-record's 14th field) I already fixed. These are the ones that touch security primitives in OTHER repos — the fleet seat's to weigh, not this seat's to patch. Grounded, with file references; none acted on.*

---

## HIGH — security drift

1. **Stale `friction_floor.py` vendored in willow-mcp ships a coin-flip detector.**
   `willow-mcp/src/willow_mcp/friction_floor.py` (208 lines) claims in its header
   "kept byte-for-byte … diffable against upstream." It is NOT: `willow-gate`'s
   canonical copy (317 lines) added a ~116-line stance-aware second signal
   (`stance_friction`, `_persona_polarity`) — the fix that moved sycophancy
   detection from **chance (≈48.9%) to 84.2%** on 9k labeled pairs (willow-gate#9).
   willow-mcp ships only the older stance-*blind* `friction_score`, measured at
   chance. → Re-vendor from willow-gate (pull `stance_friction`), or make the
   header honest that it's a stance-blind subset.

2. **willow-2.0's in-house executor is still live → two egress-enforcement paths.**
   `willow-2.0/core/kart_sandbox.py` (33 KB) + `kart_execute.py` (21 KB) are the
   pre-kartikeya bwrap executor. willow-mcp `worker.py` now runs through published
   `kartikeya` ("no willow-2.0 run_shell import"), and the 2.0 executor is the one
   that bypassed the three-key gate (B-37, verified live task `2E8E5FE0`), forcing
   `willow-2.0/core/egress_authority.py` as a retrofit re-check. → Archive the 2.0
   in-house executor; route any remaining callers through kartikeya so the P0
   egress gate has a single enforcement point.

3. **The 5-rung trust ladder + HMAC 13-field header live in TWO repos** (drift on a
   security primitive). `willow-gate/src/willow_gate/__init__.py` (`TRUST_LEVELS`,
   `REQUIRED_FIELDS`, `_authenticate`) vs `willow-mcp/src/willow_mcp/session_binder.py`
   (its own `TRUST_LEVELS` + `check_in`) + `agent_registry.py`/`signing.py`/
   `tier_policy.py`. Deliberate ("no PGP dep") but the ladder is now source-of-truth
   in two places. Plus a **third gate** — `willow-2.0/sap/core/gate.py` — the
   un-stamped legacy ancestor of willow-mcp's `gate.py`. → Import the ladder
   names/ceilings from willow-gate (the stated seam option D5), or generate both
   from one table; stamp `sap/core/gate.py` superseded-by.

4. **willow-2.0's nomic embedder omits the task prefixes nomic requires** →
   degraded, non-comparable vectors. `willow-2.0/core/embedder.py` lacks the
   `search_document:` / `search_query:` prefixes that `willow-mcp/.../nest/embed.py`
   documents as ~doubling usable separation. Separately: nomic-768 (2.0/mcp) and
   mpnet-768 (`willow-compose/engine/embed_pieces.py`) are **both 768-dim but
   different vector spaces** — a silent interop trap. → Fold 2.0's embedder onto
   `nest/embed.py`; document that the two 768 stores are non-interchangeable.

## MED

5. **`web_search.py` / `web_fetch.py` duplicated + drifted** across willow-2.0/core
   and willow-mcp. `web_search.py` is byte-identical except 8 lines (logger + UA);
   `web_fetch.py` has diverged into two *different* egress-guard behaviors under one
   name (2.0 fylgja `SANDWICH_TEMPLATE` vs mcp `external_guard`). → Standardize on
   the mcp copy; retire 2.0's.

6. **"willow-mcp decommission" stale intel** — the phrasing the operator already
   corrected. `willow-gate/docs/hardening-plan.md:65,219` reads as if willow-mcp is
   being decommissioned; the real referent is the **willow-2.0** decommission that
   willow-mcp *executes* (`willow-mcp/deploy/kart-worker.md`). → Reword to
   "willow-2.0 decommission (willow-mcp cutover)".

7. **Dual-Commit / sudo-invariant canon byte-copied across repos.** The
   VOICES/THE_BOOK_OF_WILLOW/THE_COLLABORATION file set + `*_seed.py` are
   byte-duplicated in `willow-mcp/docs/repatriation/` AND `willow-compose/docs/` +
   `engine/`, restated again in `willow-mcp/ARCHITECT.md` and `utety/docs/`. → One
   canonical home (mcp repatriation); reduce willow-compose's copy to a pointer
   ("willow writes pointers, not prose").

## Clean bill (checked, NOT redundant)
Nestor is genuinely new (different algorithm/lifecycle from willow-compose's
MinHash); the app-ACL ↔ agent-trust seam (`willow-gate-seam.md`) is shipped and
healthy — tier is a ceiling over permission-groups, not a duplicate; `ΔΣ=42` is
consistent fleet-wide; `b17:` stamps are correctly per-domain.

---

*Handed up because these are cross-repo security primitives — the fleet seat's
call, with write and the corpus. The store-local and mine-to-fix items from the
same sweep are being handled on this branch. `ΔΣ=42`*

**— the builder's seat, `safe-app-store`, 2026-07-24.**
