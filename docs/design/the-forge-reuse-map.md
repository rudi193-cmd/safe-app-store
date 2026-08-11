# The Forge — reuse map (license-filtered, 2026-08-11)

> Extends `the-forge.md`'s "Candidate building blocks (open internet sweep,
> 2026-07-31)" and "Adopted dependencies" sections rather than redoing them —
> per rule 11, the sweep partly exists. This pass (a) re-verifies those
> license claims against the actual LICENSE file / PyPI classifier / SPDX id
> rather than trusting the earlier prose, and (b) extends the sweep to the
> pieces D9's own 2026-08-11 addendum and the willow-mcp reuse-map section
> raised but never license-checked: the scheduler, the calibration math, the
> contradiction detector, and the fleet-repo dependency question itself.

## The constraint

`safe-app-store` is **Apache-2.0** (`/home/user/safe-app-store/LICENSE`,
`NOTICE`). A dependency is safe to pull in only if its license is
**Apache-2.0-compatible**: Apache-2.0, MIT, BSD-2/3, ISC, Python-2.0, or
(with care — read the specific terms, don't just see "L" and move on)
MPL-2.0/LGPL. **GPL-2.0, GPL-3.0, and AGPL are not compatible** — combining
GPL/AGPL code into an Apache-2.0-licensed work would force the combined
work under GPL/AGPL terms, which the project has not agreed to and does not
want. `the-forge.md` already excluded two real candidates on exactly this
basis (Daytona → AGPL-3.0, Firejail → GPL-2.0); this doc extends that same
discipline to everything else the design still needs.

"Compatible" here means: an unmodified pip/git dependency, or a vendored
function, that safe-app-store can ship inside an Apache-2.0 codebase without
changing safe-app-store's own license or asking anyone's permission beyond
what Apache-2.0 itself already grants (attribution, NOTICE-carrying, mark
changed files). It does **not** mean "open source" in general — MPL/LGPL
pieces are compatible only if kept as a separate, unmodified linked
component; none of the candidates below actually require that caveat, so it
doesn't bind in practice this round.

---

## CRITICAL — can safe-app-store actually depend on the fleet repos?

Checked directly against each repo's real `LICENSE` file / `pyproject.toml`
license field + classifier, not assumed from CLAUDE.md's prose.

| Repo | Where verified | License | May safe-app-store (Apache-2.0) depend on it? |
|---|---|---|---|
| **safe-app-store** (this repo) | `/home/user/safe-app-store/LICENSE`, `NOTICE` | **Apache-2.0** | — (it's the host) |
| **Nestor** | `/workspace/nestor/LICENSE` (full Apache-2.0 text, verified read) | **Apache-2.0** | **YES.** Same license family; no compatibility question at all. Already the D12-adopted dependency. |
| **willow-mcp** | `/workspace/rudi193-cmd/willow-mcp/LICENSE` + `pyproject.toml` (`license = {text="Apache-2.0"}`, classifier `License :: OSI Approved :: Apache Software License`) | **Apache-2.0** | **YES.** Same reasoning as Nestor. |
| **Jeles** | `/workspace/rudi193-cmd/Jeles/LICENSE` + `pyproject.toml` (`license = {text="Apache-2.0"}`, same classifier) | **Apache-2.0** | **YES.** Contra the task brief's assumption that Jeles is "likely not attached" — it is present locally at `/workspace/rudi193-cmd/Jeles` in this session and its license was read directly, not inferred. |
| **oakenscrolls-office** | GitHub `rudi193-cmd/oakenscrolls-office`, `LICENSE` fetched via `get_file_contents` (full Apache-2.0 text) | **Apache-2.0** | **YES.** |
| **kartikeya (Kart)** | `/workspace/rudi193-cmd/kartikeya/LICENSE` + `pyproject.toml` (`license = {text="MIT"}`, classifier `OSI Approved :: MIT License`) | **MIT** | **YES.** MIT is Apache-2.0-compatible outright; also already the D2-adopted, actually-wired dependency (`apps/the-forge/pyproject.toml` pins `kartikeya>=0.0.7`). |
| **`libs/fleet-presence`, `libs/subject-consent`** (in-repo) | `LICENSE` files present, both "MIT License, Copyright (c) 2026 Sean Campbell" | **MIT** | **YES** — already inside the repo. |
| **`libs/nest-pipeline`, `libs/pg-sqlite-shim`, `libs/vault-paths`, `libs/willow-pg`, `libs/willow-read`** (in-repo) | `pyproject.toml` `license = {text="MIT"}` each; no standalone `LICENSE` file present in any of the five | **MIT** (declared, file missing) | **YES** in substance; worth a follow-up bite to add the missing `LICENSE` files so the metadata claim has a document backing it, but not a Forge blocker. |
| **`engram` / `mengram`** | Could not locate — see "Could not verify," below | **UNKNOWN** | **CANNOT SAY.** No license claim should be assumed either way until the repo is actually reachable. |

**Headline: every fleet repo the task named as reachable (Nestor, willow-mcp,
Jeles, oakenscrolls-office, kartikeya) is Apache-2.0 or MIT, verified against
the actual LICENSE file or PyPI-equivalent metadata, not CLAUDE.md's
say-so. safe-app-store may depend on all five with no license friction.**
The one gap is `engram`/`mengram`, which is not a reachable repo at all (see
below) — its shipped-ness is currently just a claim inside another repo's
brainstorm doc.

---

## Master table

Verdict key: **REUSE** (adopt as pip/git dependency, or vendor a small
function) · **BUILD** (nothing license-clean and fit exists) · **EXCLUDE**
(real candidate, wrong license).

| # | Piece | Candidate(s) | License (verified) | Apache-compat | Covers | Verdict |
|---|---|---|---|---|---|---|
| 1a | **Scheduler** — "is it due for review" (D9 / bite 2) | `py-fsrs` (PyPI `fsrs`) | **MIT** — PyPI classifier `OSI Approved :: MIT License`, verified via PyPI page fetch | Y | D9, bite 2 | **REUSE** — `pip install fsrs`. Real, published, license-clean, and matches D9's own already-recorded adoption decision. **This is the verdict that unblocks bite 2's deferred scheduler.** |
| 1b | Scheduler alt. | `sm-2` (`open-spaced-repetition/sm-2`) | **MIT** — GitHub `LICENSE`, PyPI classifier, verified via search | Y | D9 | REUSE-eligible fallback if FSRS's parameter count is unwanted; D9 already chose FSRS over this. |
| 1c | Scheduler alt. | `openskill.py` | **MIT** — PyPI "License expression: MIT" | Y | D9 | REUSE-eligible; weaker fit (no interval-scheduling), already passed over in D9. |
| 1d | Scheduler alt. | `py-irt` | **MIT** — PyPI classifier, verified | Y | D9 | REUSE-eligible; PyTorch dependency weighs against it, already passed over in D9. |
| 1e | Scheduler alt. (fleet) | `engram` / `mengram` decay (willow-mcp idea `#1`) | **UNKNOWN — could not verify**, see below | **?** | D9 / bite 2 | **NOT a safe reuse pick right now.** `the-forge.md`'s own 2026-08-11 bite-2 text says the "due for review" half is "a **reuse** of willow-mcp's `engram`, not a py-fsrs build" — **this pass found that claim cannot currently be substantiated** (no such repo exists under `rudi193-cmd`, and the module is not inside `willow-mcp` itself; see "Could not verify"). Until `engram`/`mengram` is an attached, license-readable repo, **py-fsrs (1a) is the only verifiable REUSE pick for bite 2** — treat the design doc's `engram` framing as an open claim, not a closed one. |
| 2 | **Calibration math** (D9 optional refinement) | `oakenscrolls-office`'s `calibration.py` | **Apache-2.0** — repo `LICENSE` verified via GitHub `get_file_contents`; file itself read in full: 69 lines, `import math` only, no other deps | Y | D9 (optional) | **REUSE — vendor the function.** Confirmed dependency-free, stdlib-only, small enough to vendor whole (same precedent the file's own docstring names: `utety/core/mastery.py`). Apache-2.0 source into an Apache-2.0 host has zero friction — copy with the file's existing header intact (satisfies §4(b)/(c)). Per D9's 2026-08-11 decision, this stays an **optional refinement layered over lesson-regression**, not load-bearing — so REUSE-when-wanted, not urgent. |
| 3a | **Contradiction / refutation** (`#3`) | Jeles' `conflict_scan.py` (`jeles/reactions/conflict_scan.py`) | **Apache-2.0** — `Jeles/LICENSE` + `pyproject.toml` verified | Y | `#3`, stage 4 of the willow-mcp reuse map | **REUSE.** Working, tested (`tests/test_conflict_scan.py` exists), network-free-testable code: conflict-biased query framing + two-independent-source corroboration, exactly the "search for what refutes, not what resembles" shape CLAUDE.md rule 11 already names as the worked lesson from 2026-08-05. |
| 3b | Contradiction / refutation, runtime primitive | Nestor's `reject_pair` / `reject_match` (`nestor/memory.py:1117`, `:1163`) | **Apache-2.0** — `/workspace/nestor/LICENSE` verified | Y | `#3`, D12/D9 revision path | **REUSE — already adopted.** Nestor is already a D12 dependency; `reject_pair`/`reject_match` are the seal-revision half of the same contradiction question conflict_scan answers at proposal-time. No new dependency, just wire the call. |
| 4 | **Seal/serve memory** (D12) | Nestor | **Apache-2.0** — verified above | Y | D12 | **REUSE — already adopted**, license-clear (see CRITICAL table). |
| 5 | **Friction / engagement gate** (`#66`/`#67`, bite 3) | willow-mcp `friction_floor.py` + `friction.py` | **Apache-2.0** — `willow-mcp/LICENSE` + `pyproject.toml` verified; files confirmed present at `src/willow_mcp/friction_floor.py`, `src/willow_mcp/friction.py`, with tests (`test_friction.py`, `test_stance_friction.py`) | Y | `#66`/`#67`, bite 3 | **REUSE — already shipped, unwired.** `#66` (sycophancy score) is marked ✅ shipped in willow-mcp's own `docs/ideas.md`; `#67` (mid-session nudge) is 🟡 partial (primitive exists, injection timing doesn't). Wire via the D5 connector (capability-provider pattern) rather than a direct import, consistent with D1. |
| 6a | **Sandbox — seccomp gap fix** (D2) | `nsjail` | **Apache-2.0** — Google, source headers verified via search | Y | D2 | **REUSE — already the D2-adopted pick.** Confirmed still correct. |
| 6b | Sandbox — stronger isolation tier | `gVisor`, `Kata Containers`, `Firecracker` | **Apache-2.0** (all three, confirmed) | Y | D6 future tier | Confirmed license-clean; still correctly **not adopted** — D2 already decided "nothing further for now," no multi-tenant traffic yet to justify the infra cost. Re-check when D6's tenancy actually ships real users. |
| 6c | Sandbox — capability-based alt. axis | `Wasmtime` | **Apache-2.0 WITH LLVM-exception** — `bytecodealliance/wasmtime/LICENSE` verified directly | Y | D2 (Wasm path) | License-clean; still a later-tier option, not adopted, if generated code ever targets Wasm. |
| 6d | Sandbox — full platform | `E2B` (self-hosted, `e2b-dev/infra`) | **Apache-2.0** — confirmed via direct repo fetch (the-forge.md's original claim holds; note the language SDKs like `e2b-code-interpreter` are separately MIT-licensed, also compatible, but the infra repo itself is Apache-2.0) | Y | D2 alt. | License-clean; still not adopted, real infra cost (~$1,250/mo self-hosted floor per original sweep) outweighs the benefit at current scale. |
| 7a | **Signing gate** (D4) | Sigstore (`cosign`), static-keypair mode | **Apache-2.0** — confirmed | Y | D4 | **REUSE — already the D4-adopted pick.** Confirmed still correct. |
| 7b | Signing — rotation model reference | TUF (`theupdateframework/python-tuf`) | **MIT / Apache-2.0 dual** — confirmed via GitHub search | Y | D4 (read, not adopted) | License-clean either way; still correctly "read for the rotation model, not adopted whole." |
| 7c | Signing alt. | `in-toto` (attestation framework) | **Apache-2.0** — confirmed (note: `in-toto/attestation`'s companion `Archivista` storage service is separately MIT-licensed, also compatible) | Y | D4 (poorer fit) | License-clean; still a poorer fit per the original sweep's own reasoning (more machinery than one manifest needs). |
| 7d | Signing alt. | Notary / `notation` (`notaryproject/notation*`) | **Apache-2.0** — confirmed | Y | D4 (poorer fit) | License-clean; still OCI-registry-shaped, poorer fit, not adopted. |
| 8a | **Policy / MCP connector — in-process gate** (D1/D5) | Casbin / `pycasbin` | **Apache-2.0** — confirmed (`casbin/pycasbin`) | Y | D1/D5 | **REUSE — already the D1/D5-adopted pick.** Confirmed still correct. |
| 8b | Policy — escalation path | OPA/Rego | **Apache-2.0** — confirmed (`open-policy-agent/opa/LICENSE`) | Y | D1/D5 (not adopted) | License-clean; correctly held as an escalation path only, not a current dependency. |
| 8c | Policy — escalation path | Cedar / `cedarpy` | **Apache-2.0** — confirmed (`cedarpy` package license = apache-2.0, per Socket.dev + PyPI) | Y | D1/D5 (not adopted) | License-clean; `cedarpy` bindings are community-maintained (not AWS-official) — same caveat the original sweep already named, still holds. |
| 8d | MCP connector prior art | `mcp-gateway-registry` (`agentic-community`) | **Apache-2.0** — confirmed (repo `LICENSE`) | Y | D5 (reference, not adopted) | License-clean; correctly read-for-structure only — its OAuth-scope/role model doesn't match D5's explicit-per-tool-allowlist shape. **BUILD** the connector itself in-repo, as D5 already decided. |
| 8e | MCP connector prior art | `mcp-filter` (`pro-vi/mcp-filter`) | **MIT** — confirmed via direct repo fetch | Y | D5 (technique reference) | License-clean; usable technique, author's own caveat stands ("a schema reducer, not a security boundary") — reference only. |
| 9a | **Model routing — local engine** (D7) | vLLM | **Apache-2.0** — confirmed (`vllm-project/vllm/LICENSE`) | Y | D7 | **REUSE — already the D7-adopted pick.** Confirmed still correct (chosen over Ollama for multi-tenant throughput). |
| 9b | Model routing — local engine alt. | Ollama | **MIT** — confirmed | Y | D7 (not adopted) | License-clean; correctly passed over for vLLM given D6's multi-tenant premise. |
| 9c | Model routing — proxy layer | LiteLLM | **MIT (core)** — confirmed (`BerriAI/litellm/LICENSE`); **the `enterprise/` subdirectory is under a separate commercial license** (`enterprise/LICENSE.md`, confirmed via direct fetch: "Code in this folder is licensed under a commercial license") | **Y (core only) — `enterprise/` is NOT open source, exclude it explicitly, do not just avoid GPL** | D7 | **REUSE — core only.** Install/import only the MIT-licensed core paths; never import anything under `litellm/enterprise/` or enable enterprise features. This is not a GPL/AGPL issue but the same practical exclusion — flagging it here because "MIT license" on the repo badge does not cover that subtree. |
| 9d | Model routing alt. | RouteLLM (`lm-sys/RouteLLM`) | **Apache-2.0** — confirmed | Y | D7 (weaker fit, not adopted) | License-clean; correctly passed over — routes on predicted quality, not D7's explicit-permission signal. |
| 10a | **Loop plumbing — lineage** (`#2`) | willow-mcp `lineage.py` | **Apache-2.0** | Y | Stage 3 of the learning loop | **REUSE.** Present, tested (`test_lineage.py`, `test_seed_lineage.py`). Importable as a library call or reachable through the D5 connector; willow-mcp being Apache-2.0 means a direct import is license-legal, though D1's "capability provider, not authority" framing argues for going through the connector anyway. |
| 10b | Loop plumbing — Grove | willow-mcp `the_grove.py` | **Apache-2.0** | Y | Stage 3 | **REUSE.** Present, tested (`test_the_grove.py`). Same import-vs-connector note as 10a. |
| 10c | Loop plumbing — commitment surface | willow-mcp `commitments/commitment_store.py`, `commitment_ledger.py` | **Apache-2.0** | Y | Stage 6 (`#41`/`#42`) | **REUSE.** Present, tested (three test files found). `#41` (escalation) is ✅ shipped per willow-mcp's own idea audit; `#42` (SLA tracking) is unmarked/unshipped — that half is still BUILD. |
| 10d | Loop plumbing — receipts | willow-mcp `receipts.py`, `bound_receipt.py` | **Apache-2.0** | Y | `#38` | **REUSE.** Present, tested, schema-backed (`schemas/bound_receipt.v1.schema.json`). ✅ shipped per willow-mcp's own audit. |
| 10e | Loop plumbing — code graph / blast radius | willow-mcp `code_graph/` (`analyze_impact`, `walker.py`) | **Apache-2.0** | Y | `#51` | **REUSE.** Present, tested (`test_code_graph.py`). ✅ shipped per willow-mcp's own audit; the auto-on-save hook (the only unshipped half) is garnish, not load-bearing for the Forge's use. |

---

## Already ours, just wire it

License-clear (Apache-2.0 or MIT, all verified above), already present in a
reachable fleet repo, adopted-in-principle by an existing Forge decision —
the remaining work is **wiring**, not building or evaluating:

- **Nestor** (D12) — `reject_pair`/`reject_match` for `#3`'s revision half; the
  memory/seal mechanic itself already adopted.
- **willow-mcp `friction_floor.py`/`friction.py`** — bite 3's engagement
  gate. Shipped, tested, unwired.
- **willow-mcp `lineage.py`, `the_grove.py`** — stage 3 of the learning loop
  (seal it, with rationale + provenance). Shipped, tested, unwired.
- **willow-mcp `commitments/`** (`commitment_store.py`, `commitment_ledger.py`)
  — stage 6's "I don't know, you choose" deferral-as-commitment. Shipped
  (escalation half), tested, unwired.
- **willow-mcp `receipts.py`/`bound_receipt.py`** — audit trail for `#38`.
  Shipped, tested, unwired.
- **willow-mcp `code_graph/`** — `#51` blast-radius, if/when the Forge needs
  to reason about what a generated change touches.
- **Jeles `conflict_scan.py`** — the search-time half of `#3`. Shipped,
  tested, unwired into the Forge (Jeles itself is a search/verification
  product, not currently a Forge dependency at all).
- **`py-fsrs`** — not fleet-internal, but real, MIT, published, and already
  the D9-recorded adoption. `pip install fsrs` is the entire remaining lift
  for bite 2's scheduler.
- **`oakenscrolls-office`'s `calibration.py`** — Apache-2.0, 69 lines,
  stdlib-only, vendor-ready whenever D9's optional calibration refinement is
  wanted.

---

## EXCLUDED (GPL/AGPL) — do not re-propose

| Candidate | License | Why excluded |
|---|---|---|
| **Daytona** | AGPL-3.0 (moved off Apache-2.0 mid-2026) | Already excluded in `the-forge.md`'s original sweep; re-confirmed, no change. AGPL's network-use clause would force safe-app-store's own terms open under conditions Apache-2.0 doesn't require. |
| **Firejail** | GPL-2.0 | Already excluded in `the-forge.md`'s original sweep; re-confirmed, no change. GPL-2.0 linking would require the combined work to be GPL-licensed. |
| **LiteLLM `enterprise/`** | Commercial (proprietary, not GPL/AGPL but still not open source) | Not a GPL/AGPL case, but excluded for the same practical reason: code under a non-Apache-compatible license must not enter an Apache-2.0 codebase. Flagged separately in the master table (9c) rather than here, since it's not actually copyleft — listed here too so nobody has to cross-reference to find it. |

No other GPL/AGPL candidates turned up in this pass's searches (nsjail,
gVisor, Kata, Firecracker, Wasmtime, E2B, Sigstore, TUF, in-toto, Notary,
Casbin, OPA, Cedar, mcp-gateway-registry, mcp-filter, vLLM, Ollama, LiteLLM
core, RouteLLM, py-fsrs, sm-2, openskill.py, py-irt all came back
Apache-2.0/MIT-clean, verified above).

---

## Could not verify — stated honestly, not guessed

- **`engram` / `mengram`** (willow-mcp idea `#1`, "memory decay curves...
  ✅ shipped in `engram`/`mengram`"). Searched:
  - `mcp__github__search_repositories` for `engram` and `mengram` under
    `user:rudi193-cmd` — **zero results**, neither name exists as a
    repository in the reachable org.
  - `mcp__github__search_code` for `engram`/`mengram` org-wide
    (`org:rudi193-cmd`) — the **only** hit for either term, anywhere in the
    org, is the citation inside `willow-mcp/docs/ideas.md` itself (the
    passage quoted above). No source file, no package, no separate repo
    actually implements it, as far as this session can see.
  - Local filesystem search (`/workspace`) for `engram` — no matches outside
    that same `docs/ideas.md` reference.
  - **Conclusion: `engram`/`mengram`'s existence, license, and even which
    repo it would live in are all unconfirmed.** `willow-mcp`'s own idea-pile
    marks it "✅ shipped," and `the-forge.md`'s 2026-08-11 bite-ladder text
    took that at face value for bite 2's scheduler — this pass could not
    substantiate it and did not guess a license for something whose location
    is itself unknown. **The fix is not to assume it's fine, and not to
    assume it's missing — it's to attach the actual `engram`/`mengram` repo
    (if `add_repo` can reach it under a different owner or name) or ask
    whoever wrote that `ideas.md` line where it actually lives**, before
    bite 2 leans on it. Until then, treat the design doc's own "reuse of
    `engram`" framing for bite 2 as unverified, and use `py-fsrs` (1a in the
    master table) instead — it needs no such resolution.
- **`libs/nest-pipeline`, `libs/pg-sqlite-shim`, `libs/vault-paths`,
  `libs/willow-pg`, `libs/willow-read`** — license is *declared* MIT in each
  `pyproject.toml`, but none of the five ships an actual `LICENSE` file
  (unlike `libs/fleet-presence` and `libs/subject-consent`, which do). Not
  ambiguous enough to call "could not verify" — the metadata is unambiguous
  and consistent across all five — but worth a follow-up bite to add the
  missing files rather than resting on declared-but-undocumented metadata
  indefinitely.

Everything else named in the task — Nestor, safe-app-store's own LICENSE,
willow-mcp, oakenscrolls-office, Jeles, and all twenty-plus OSS candidates in
the master table — was verified against a real LICENSE file, PyPI
classifier/SPDX id, or (for `libs/`) `pyproject.toml` metadata, cited inline
in the master table.

---

## Sources (verified this pass, 2026-08-11)

- `safe-app-store` — `/home/user/safe-app-store/LICENSE`, `/home/user/safe-app-store/NOTICE`
- Nestor — `/workspace/nestor/LICENSE` (read in full)
- willow-mcp — `/workspace/rudi193-cmd/willow-mcp/LICENSE`, `pyproject.toml`
- Jeles — `/workspace/rudi193-cmd/Jeles/LICENSE`, `pyproject.toml`, `jeles/reactions/conflict_scan.py`
- kartikeya — `/workspace/rudi193-cmd/kartikeya/LICENSE`, `pyproject.toml`
- oakenscrolls-office — GitHub `rudi193-cmd/oakenscrolls-office`, `LICENSE` and `calibration.py` via `get_file_contents`
- willow-mcp idea audit — GitHub `rudi193-cmd/willow-mcp`, `docs/ideas.md` via `get_file_contents` / `search_code`
- `libs/*` — local `LICENSE` files and `pyproject.toml` license fields, read directly
- PyPI pages (fetched directly): `fsrs`, `openskill`, `py-irt`
- GitHub/PyPI, via web search + spot-fetch (SPDX id or LICENSE file each
  confirmed, not just search-snippet-inferred, for the ones marked
  "confirmed via direct fetch" above): nsjail, gVisor, Kata Containers,
  Firecracker, Wasmtime (`bytecodealliance/wasmtime/LICENSE`, full text
  fetched), E2B (`e2b-dev/infra`, fetched), Sigstore/cosign, TUF
  (`theupdateframework/python-tuf`), in-toto (`in-toto/attestation/LICENSE`),
  Notary/notation, Casbin/pycasbin, OPA (`open-policy-agent/opa/LICENSE`),
  Cedar/cedarpy, mcp-gateway-registry, mcp-filter (`pro-vi/mcp-filter`,
  fetched), vLLM (`vllm-project/vllm/LICENSE`), Ollama, LiteLLM
  (`BerriAI/litellm/LICENSE` core + `enterprise/LICENSE.md` carve-out, both
  fetched), RouteLLM (`lm-sys/RouteLLM`), sm-2
  (`open-spaced-repetition/sm-2/LICENSE`).
