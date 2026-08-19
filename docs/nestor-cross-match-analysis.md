# Nestor Cross-Match Analysis

What Nestor's StringMatcher found when it scored 30 MCP coupling audit
findings against each other. Clusters, cross-layer connections, and the
combinations that matter for decision-making.

- **30 findings** across **5 coupling layers**
- **Matcher**: StringMatcher / difflib (character-level fuzzy)
- **Threshold**: 0.30 (lowered from default 0.55 to surface structural relationships)
- **Date**: 2026-08-19

---

## Summary

| Metric | Value |
|---|---|
| Clusters found | 6 |
| Standalone findings | 15 |
| Highest affinity | 0.523 |
| Cross-layer links | 10 |

---

## Clusters

Connected components at score >= 0.40. These are findings Nestor sees as
structurally related — same vocabulary, overlapping concerns, or parallel shape.

### Auth Gate (2 findings, peak: 0.523)

- **[L2] the-squirrel** — ~30 files import sap.core.gate -> willow_gate.WillowGate. Reaches into _SIGNED_FIELDS.
- **[L2] law-gazelle** — gazelle_gate.py imports willow_gate, reaches into wg._SIGNED_FIELDS.

Highest pair in the dataset. Both reach into private fields. One AuthGate
Protocol solves both, but law-gazelle is the easier first target (single
chokepoint vs 30-file fan-out).

### safe_integration core (3 findings, triangle: 0.464 / 0.432 / 0.416)

- **[L3] 17 copies** — safe_integration.py: 17 copies, 17 distinct implementations. 4 families.
- **[L3] orphaned copies** — Only 6 of 17 are live consumers. 11 exist only for manifest health check.
- **[L3] three contracts** — Conflates KB/messaging, session/consent (SAFESession), identity/composite.

Tightly connected triangle. The copy count, the dead code, and the contract
conflation are the same problem from three angles. Fix the contracts, the
copies and orphans resolve.

### sys.path imports (2 findings, affinity: 0.444)

- **[L2] SoilClient** — story-timeline imports via sys.path.insert. 3 duplicated _get_client() bootstraps.
- **[L2] llm_router** — nasa-archive, llmphysics: direct import via sys.path.insert to stale sibling checkouts.

Identical import pattern. A shared import-resolution mechanism handles both.

### Solved abstractions (3 findings, cross-layer: 0.443 / 0.400)

- **[L1] MCP clients** — 4 apps + store TUI have direct MCP client connections via stdio_client.
- **[L2] KB read** — libs/willow-read KnowledgeClient Protocol with set_client() injection. Already solved.
- **[L2] Postgres** — libs/willow-pg: 4 apps use it for Postgres pooling. Already solved.

Cross-layer cluster. The matcher sees these as structurally similar — the
already-solved problems share vocabulary and shape with the unsolved ones.
The template is there.

### Manifest evolution (2 findings, affinity: 0.464)

- **[L4] store_scope** — 5 real SOIL prefixes, 5 deliberately empty. Declaration only.
- **[L4] future format** — story-timeline has capability-declaration format: exposes/reads_from/protocol.collections.

The evolutionary path is already defined: from bare prefixes to named
abstract capabilities.

### Invisible-to-grep (3 findings, cross-layer: 0.423 / 0.406)

- **[L1] jarvis** — Hand-rolled OAuth+PKCE MCP JSON-RPC client invisible to standard grep patterns.
- **[L5] llmphysics** — Non-standard .js manifest invisible to scans. Actually deeply coupled.
- **[L5] game-lab** — No manifest at all. Completely decoupled but invisible to catalog tooling.

Cross-layer cluster linked by shared trait: invisible to standard Python-centric
scan tooling. Any future audit that only greps Python will miss these.

---

## Cross-Layer Connections

Strongest links between findings in different coupling layers (score >= 0.35).
These reveal shared mechanics or common fix patterns that span the architecture.

| Score | Finding A | | Finding B | Implication |
|---|---|---|---|---|
| 0.423 | [L1] jarvis | <-> | [L5] llmphysics | Both invisible to standard grep — JS clients evade Python scans |
| 0.400 | [L1] mcp-clients | <-> | [L2] kb-read | MCP transport and KB read are the same pluggability problem |
| 0.398 | [L2] postgres | <-> | [L5] already-agnostic | willow-pg consumers are functionally agnostic — the abstraction worked |
| 0.396 | [L2] kb-read | <-> | [L5] gold-standard | KnowledgeClient Protocol and oakenscrolls injection are the same idea |
| 0.392 | [L3] template-exists | <-> | [L4] future-format | Pluggability template and manifest evolution share "protocol declaration" vocabulary |
| 0.388 | [L1] mcp-clients | <-> | [L2] soil-storage | Both are direct willow imports — one at transport, one at data layer |
| 0.381 | [L2] auth-gate | <-> | [X] roadmap | Auth gate is the roadmap's hardest item (P4) — matcher confirms the weight |
| 0.369 | [L1] ask-jeles | <-> | [L3] template-exists | ask-jeles generic client and willow_read pluggability are both "the template already exists" |
| 0.365 | [L3] dead-stubs | <-> | [L4] bug | Silent failures: dead stubs return error strings, store_scope bug silently blocks |
| 0.363 | [L2] auth-gate-gazelle | <-> | [L4] bug | Gate coupling and manifest type error both live in the permission subsystem |

---

## Decision Signals

### P0 is confirmed: safe_integration

The safe_integration triangle (3 findings, all mutually connected at
0.41–0.46) is the densest cluster. 17 copies, 11 orphaned, 3 conflated
contracts. The matcher agrees with the roadmap: this is the highest-leverage
fix.

### P1 template already exists

ask-jeles's generic MCP client connects cross-layer to the pluggability
template (0.369). The solved-abstractions cluster (willow-read + willow-pg +
MCP clients) proves the extraction pattern works. Don't design from scratch.

### Auth gate needs sequencing

0.523 affinity between the-squirrel and law-gazelle, but law-gazelle is a
single chokepoint vs 30-file fan-out. Do gazelle first as the AuthGate
Protocol prototype, then tackle squirrel.

### The ai-game-master bug is real

L4-bug connects to both dead-stubs (0.365) and auth-gate-gazelle (0.363) —
three silent permission failures in the same subsystem. Fix the type error
immediately, investigate the pattern.

### The invisible cluster is a scan gap

jarvis + llmphysics + game-lab cluster not by coupling type but by
invisibility to standard tooling. Any future audit that only greps Python
will miss these. Add JS manifest scanning and no-manifest detection.

### 49% agnostic validates the approach

willow-pg's connection to already-agnostic (0.398) and gold-standard (0.378)
confirms: abstractions that exist and are used actually decouple. The
remaining 51% is extraction, not invention.

---

## All 30 Findings

### Layer 1 — Direct MCP Client Connections

**L1-mcp-clients** (top match: 0.400 -> L2-kb-read-solved)
- Finding: 4 apps + store TUI have direct MCP client connections via stdio_client. Endpoint discovery copy-pasted 4x.
- Recommendation: Extract ask-jeles mcp_generic.py/mcp_registry.py into libs/mcp-connect. Configurable endpoint, multi-transport.

**L1-jarvis** (top match: 0.423 -> L5-llmphysics-misclassified)
- Finding: jarvis has hand-rolled OAuth+PKCE MCP JSON-RPC client invisible to standard grep patterns.
- Recommendation: Rewrite jarvis WillowClient to target MCP spec generically. Use same configurable endpoint pattern.

**L1-ask-jeles-template** (top match: 0.369 -> L3-template-exists)
- Finding: ask-jeles already has generic multi-server MCP client: mcp_generic.py reads .mcp.json, discovers arbitrary servers.
- Recommendation: Extract into shared libs/mcp-connect. This is the template — don't write a new generic client from scratch.

**L1-ratatosk** (top match: 0.368 -> L2-claim-verifier)
- Finding: ratatosk is tool-name-agnostic: no hardcoded tool names, full dynamic pass-through via list_tools().
- Recommendation: Already server-agnostic in tool selection. Only the launch command is hardcoded — parameterize it.

### Layer 2 — Direct Python Imports

**L2-kb-read-solved** (top match: 0.443 -> L2-postgres-solved)
- Finding: libs/willow-read KnowledgeClient Protocol with set_client() injection. 7 apps use it. Already solved.
- Recommendation: Replicate this pattern for all other Layer 2 categories.

**L2-soil-storage** (top match: 0.444 -> L2-llm-router)
- Finding: story-timeline imports SoilClient via sys.path.insert. 3 duplicated _get_client() bootstraps. ~10 call sites.
- Recommendation: Define StorageBackend Protocol (put/list/delete). Single willow_store lib collapses 3 duplicated bootstraps.

**L2-auth-gate** (top match: 0.523 -> L2-auth-gate-gazelle)
- Finding: the-squirrel: ~30 files import sap.core.gate -> willow_gate.WillowGate. Reaches into private _SIGNED_FIELDS.
- Recommendation: Define AuthGate Protocol (check_in/authorize/check_out). Deepest coupling, hardest target.

**L2-auth-gate-gazelle** (top match: 0.523 -> L2-auth-gate)
- Finding: law-gazelle: gazelle_gate.py imports willow_gate, reaches into wg._SIGNED_FIELDS for signed header building.
- Recommendation: Same AuthGate Protocol. Single chokepoint in law-gazelle vs 30-file fan-out in the-squirrel.

**L2-lattice-easy-win** (top match: 0.333 -> L2-soil-storage)
- Finding: 3 apps (dating-wellbeing, game, field-notes) duplicate lattice_fallback.py with identical constants.
- Recommendation: Promote to libs/willow-lattice. Constants only, no willow import. Most mechanical fix in the entire audit.

**L2-postgres-solved** (top match: 0.443 -> L2-kb-read-solved)
- Finding: libs/willow-pg: 4 apps use it for Postgres pooling. Clean, single import. Already solved.
- Recommendation: No action needed. Proven pattern to replicate for other categories.

**L2-claim-verifier** (top match: 0.368 -> L1-ratatosk)
- Finding: source-trail: core feature (verify_text) is 100% delegated to core.source_trail via dynamic import.
- Recommendation: Define ClaimVerifier Protocol (verify_text -> dict). Inject implementation.

**L2-llm-router** (top match: 0.444 -> L2-soil-storage)
- Finding: nasa-archive, llmphysics: direct import of Willow core llm_router via sys.path.insert to stale sibling checkouts.
- Recommendation: Define LLMRouter Protocol (complete/load_keys). llmphysics already has WILLOW_PROXY HTTP fallback.

**L2-persona** (top match: 0.360 -> L2-postgres-solved)
- Finding: ratatosk crown.py: from willow.fylgja import persona. Single _persona_gate() function.
- Recommendation: Define PersonaProvider Protocol. Shallow, single call site.

### Layer 3 — safe_integration.py Shim

**L3-17-copies** (top match: 0.432 -> L3-three-contracts)
- Finding: safe_integration.py: 17 copies, 17 distinct implementations. 4 families. Already tracked as issue #83.
- Recommendation: Collapse to libs/safe-integration. Split into 2-3 Protocol interfaces. NullBackend replaces dead stubs.

**L3-dead-stubs** (top match: 0.394 -> L3-orphaned-copies)
- Finding: safe_integration ask/ask_raw: always return 'LLM routing not available in portless mode'. Dead stubs.
- Recommendation: 'Portless mode' is willow-specific vocabulary hardcoded as user-facing text. Replace with NullBackend.

**L3-orphaned-copies** (top match: 0.464 -> L3-three-contracts)
- Finding: safe_integration: only 6 of 17 copies are live consumers. 11 exist only for manifest health check.
- Recommendation: 11 orphaned copies: replace immediately with shared status() from libs/safe-integration.

**L3-three-contracts** (top match: 0.464 -> L3-orphaned-copies)
- Finding: safe_integration conflates 3 distinct contracts: KB/messaging, session/consent, identity/composite.
- Recommendation: Split into separate Protocol interfaces. Conflating them is why the 17 copies diverged.

**L3-template-exists** (top match: 0.392 -> L4-future-format)
- Finding: willow_read.py already solves pluggability: Protocol + set_client() + graceful degradation. Working template.
- Recommendation: Replicate KnowledgeClient pattern for full safe_integration surface. oakenscrolls-office injection is gold standard.

**L3-squirrel-precedent** (top match: 0.360 -> L3-three-contracts)
- Finding: the-squirrel safe_integration already delegates to external safe_app_common package. One app already migrated.
- Recommendation: safe-app-common is the extraction target shape. Other apps should follow the-squirrel's lead.

### Layer 4 — store_scope in Manifests

**L4-store-scope** (top match: 0.464 -> L4-future-format)
- Finding: store_scope in manifests: 5 real SOIL prefixes, 5 deliberately empty. Declaration only.
- Recommendation: Evolve toward abstract capability declarations.

**L4-future-format** (top match: 0.464 -> L4-store-scope)
- Finding: story-timeline manifest already has capability-declaration format: exposes/reads_from/protocol.collections.
- Recommendation: Generalize story-timeline format as the standard.

**L4-bug** (top match: 0.365 -> L3-dead-stubs)
- Finding: ai-game-master: store_scope is string not list. Gate treats as [] (deny-all). Silent permission nullification.
- Recommendation: Fix to list: ["user-{uuid}/ai-game-master/**"]. Real bug.

**L4-signing-vs-enforcement** (top match: 0.392 -> L5-game-lab)
- Finding: sap_gate.py signs manifests (Ed25519 + hash-chained ledger) but never enforces store_scope at runtime.
- Recommendation: Signing and enforcement are separate mechanisms in separate repos.

### Layer 5 — Already Agnostic

**L5-already-agnostic** (top match: 0.398 -> L2-postgres-solved)
- Finding: 20 of 41 apps (49%) have zero functional coupling to willow-mcp. Already MCP-agnostic.
- Recommendation: No decoupling work needed. oakenscrolls-office/private-ledger injection pattern is the target.

**L5-gold-standard** (top match: 0.396 -> L2-kb-read-solved)
- Finding: oakenscrolls-office and private-ledger: willow_bridge.py with injected callable, import ban enforced by test.
- Recommendation: Gold standard. test_willow_bridge_is_pure_injection bans 'import willow'. Copy this pattern.

**L5-game-lab** (top match: 0.406 -> L5-llmphysics-misclassified)
- Finding: game-lab: only app with no manifest at all. Completely decoupled but invisible to catalog tooling.
- Recommendation: Add a manifest for discoverability. Zero coupling work needed otherwise.

**L5-llmphysics-misclassified** (top match: 0.423 -> L1-jarvis)
- Finding: llmphysics: non-standard .js manifest invisible to scans. Actually deeply coupled despite appearing Layer 5.
- Recommendation: Migrate to standard safe-app-manifest.json. Flag jac_cli.py for LLMRouter Protocol migration.

### Cross-Cutting

**roadmap** (top match: 0.381 -> L2-auth-gate)
- Finding: 49% agnostic. 4 proven abstractions exist. Work is extraction not design.
- Recommendation: P0: safe_integration (17->1). P1: MCP client lib. P2: StorageBackend. P3: lattice (3->1). P4: auth gate. P5: manifests.

**vault-paths-precedent** (top match: 0.358 -> L1-mcp-clients)
- Finding: vault-paths extraction: 9 copies -> 1 lib (box audit A5). The proven precedent.
- Recommendation: Same extraction mechanics. vault-paths proved this repo can do it. safe_integration is the next one.

**promoted-servers-design** (top match: 0.355 -> L3-template-exists)
- Finding: willow-mcp has 138 tools. Nestor 7 tools, Jeles 10 tools. Promoted organs are deliberate.
- Recommendation: Promoted MCP servers withhold capabilities by design. Generic CRUD is the threat model they defend against.

---

## Method

30 finding/recommendation pairs from the MCP coupling audit were seeded into
Nestor's memory as drafts via `memory.add_pair(status="draft")`. Each
finding's full source text was then cross-matched against every other finding
using StringMatcher (difflib SequenceMatcher with `autojunk=False`,
canonical operand ordering for symmetry). Clusters were identified as
connected components in the graph of pairs scoring >= 0.40. Cross-layer
connections were extracted from pairs scoring >= 0.35 where the two findings
belong to different coupling layers.

The default CONTEXT_THRESHOLD (0.55) was lowered to 0.30 for this analysis.
StringMatcher's character-level fuzzy matching produces scores in the
0.30–0.52 range for these natural-language descriptions — well below the
threshold designed for near-duplicate translation segments. The scores are
relative, not absolute: a 0.52 here means "the matcher sees these as the
most structurally similar pair in the dataset," not "52% match."
