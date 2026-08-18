# Promotion recon — Jeles's reader standard vs homestead-health's reference lane

**Scope.** homestead-health (local-first family-health-records, `apps/homestead-health`)
is being prepared for promotion. The promotion bar requires *"a semantic-search seam
over its own (injectable) knowledge — ship the reader, the corpus stays with whoever
grew it"* ([`stores/README.md`](../../../stores/README.md) §"The one seam every store
shares"; enforced by the `semantic_seam [M]` gate in
[`stores/promote_check.py`](../../../stores/promote_check.py)). **rudi193-cmd/Jeles** is
the fleet's worked standard for that reader. This note compares the two readers and
recommends inject-vs-grow.

**Bottom line.** homestead-health's `reference_lane.Reader` **already satisfies the
`semantic_seam` gate as-is**, and it should **keep its grown term-overlap reader** — do
**not** inject Jeles's reader. Jeles is the standard for a *writable, network-fed,
verified-nugget* corpus; homestead-health's lane is deliberately the opposite (a frozen
public-domain literal, no writes, no network, a structural no-subject wall). Injecting
Jeles would import posture the lane exists to forbid and would *remove* its H-7/H-2 wall
— a regression, not an upgrade. Borrow one idea (a confidence threshold); don't inject.

---

## 1. What each reader is

### Jeles — the injected-reader standard

Files read: [`jeles/corpus.py`], [`jeles/reactions/conflict_scan.py`],
[`jeles/reactions/search_adapter.py`], [`jeles/__init__.py`].

Jeles ships **two** retrieval-shaped things, and it matters which one is "the reader":

- **The corpus reader — `jeles/corpus.py`.** This is the injected reader / semantic-search
  seam. Public entrypoints:
  - `search_nuggets(query, limit)` — ranked lookup, never logs a gap on a miss (the
    passive/background ask).
  - `ask_corpus(question, include_asserted=False)` — the deliberate ask: answers only when
    a candidate clears `MIN_ASK_SCORE`, else logs a gap and returns `{found: False, …}`.
  - Retrieval is **deterministic token overlap**, *not* embeddings. `_score` ranks
    (recall + bonuses for exact-question / answer / tag hits); `_confidence` *decides*
    (harmonic mean of precision & recall, with any unmatched query token disqualifying —
    "a nugget about *staging* cannot answer a question about *production*").
    **Ranking and answering are separated on purpose.**
  - The **corpus/vault is injected**: nuggets live in a SQLite SOIL store keyed by
    `WILLOW_STORE_ROOT` / `JELES_CORPUS_COLLECTION` (same `records`-table shape as
    willow-mcp's SOIL `Store`), so the reader ships and the corpus stays with whoever
    grew it. The corpus is **writable** at runtime (`put_nugget`, `log_gap`) and carries
    provenance/verification state — `{question, answer, sources, verified_by, verified_at,
    tags}` plus human/machine/asserted `verification_kind` (see `to_search_hit`).
  - `jeles/__init__.py` keeps the top-level import **network-free** and I/O-free
    (`tests/test_import_purity.py`); the corpus core imports stdlib only.

- **The conflict reaction — `jeles/reactions/conflict_scan.py` (+ `search_adapter.py`).**
  This is the famous *"search for what refutes, not what resembles"* seam: `frame_queries`
  biases queries toward supersession/rivalry/refutation; a finding is corroborated only by
  **≥2 distinct registrable domains** (`_witnesses`, `WITNESS =
  "jeles:conflict-scan/2-independent-sources"`); `react`/`apply` is a propose/enforce split
  over an **injected `searcher`**. This half is **outward-facing web search** —
  `search_adapter.make_searcher` does real egress (SearXNG/Brave/Tavily/DDG) through
  `jeles._egress`. It is *not* a reader over the app's own corpus, and it **dials the
  network**.

### homestead-health — the grown reader

File read: [`apps/homestead-health/homestead_health/reference_lane.py`] (schedule context:
[`…/reference.py`]).

- `Reader(corpus: Corpus | None = None)` — **injectable corpus**, defaulting to the pinned
  `CORPUS`. `ask(question, *, limit=3)` returns cited `Result`s.
- Retrieval is **term-set overlap** (`_terms` drops stopwords; score = size of the
  intersection between the question's terms and each entry's question terms), best-first.
  On zero overlap it returns nothing rather than improvising — "a reference lane that
  invents an answer is the symptom-checker H-2 forbids."
- The corpus is a **frozen, pinned, dated public-domain literal** (`Corpus.version` /
  `as_of`; H-5's operator-act discipline — a new edition is a dated commit, never a
  runtime fetch). It **never dials** (I-17, no health exception).
- **Structural no-subject wall.** `Entry`/`Corpus` fields are a closed allowlist enforced
  at import by `_check_no_subject_can_enter()`; there is no subject parameter anywhere and
  the module imports nothing that carries one. This is the H-7/H-2 wall (reference and a
  child's record never meet on one surface) made structural, not a disclaimer.
- **Attribution rides through**: each `Result.attribution` surfaces `source (license)`, so a
  CC-BY part is never quoted uncredited.

---

## 2. Side-by-side

| Dimension | Jeles `corpus` reader | homestead-health `reference_lane.Reader` |
|---|---|---|
| Retrieval mechanism | Deterministic token overlap; `_score` ranks, `_confidence` decides (harmonic P/R, unmatched-token-disqualifying) | Deterministic term-set overlap (intersection size), best-first |
| Embeddings / model / vectors | None | None |
| Rank vs answer separation | **Yes** — `search_nuggets` vs `ask_corpus` + `MIN_ASK_SCORE` gate | No — `ask()` returns any overlapping entry (or nothing) |
| Reader injectable? | Yes (library, host wires it) | Yes (`Reader(corpus=…)`) |
| Corpus injectable? | Yes — external SQLite SOIL store via env (`WILLOW_STORE_ROOT`) | Yes via constructor; default is an **in-module pinned literal** |
| Corpus writable at runtime? | **Yes** (`put_nugget`, `log_gap`, gap-logging side effects) | **No** (frozen dataclasses; edits are dated commits — H-5) |
| Network at read time? | Reader: no. Sibling `conflict_scan`: **yes** (web egress) | **Never** (I-17) |
| Provenance model | `verified_by` / `verified_at` / human·machine·asserted kinds | `source` + `license` only (public-domain / CC-BY) |
| Schema wall | None (open nugget dict) | **Closed allowlist + `_check_no_subject_can_enter` (no subject can enter)** |
| Import purity of core | Stdlib-only, network-free (`test_import_purity`) | Stdlib-only (`re`, `dataclasses`, `datetime`) |
| Gate symbol it would declare | `jeles.corpus:ask_corpus` (or `:search_nuggets`) | `homestead_health.reference_lane:Reader` |

**They are the same retrieval family** — deterministic lexical overlap, no embeddings on
either side. Jeles's is the more disciplined instance of it (rank-vs-answer split, a
confidence threshold, gap logging), built to sit in front of a *live, writable, verified*
corpus. homestead-health's is a thinner instance built to sit in front of a *frozen,
public, subject-free* one.

---

## 3. Does `reference_lane.Reader` satisfy the `semantic_seam` gate as-is?

**Yes, mechanically — as-is.** The `semantic_seam [M]` gate
([`stores/promote_check.py`] lines ~405–415) is a **shape/existence check, not a behavior
check**: it splits the attested `semantic_seam` on `:` into `module:symbol` and asserts,
via `_defines_symbol`, that the symbol is *defined* in the candidate's core. It does not
run retrieval or grade quality. The surrounding gates it must also clear:

- `import_pure_core [M]` — no network module imported at import time. `reference_lane`
  imports only `re`/`dataclasses`/`datetime` → **passes**.
- `inversion [M]` — core must not import its host → **passes** (it imports no host).
- `semantic_seam [M]` — declare `"semantic_seam": "homestead_health.reference_lane:Reader"`
  in `promotion.json`; `Reader` is a defined class → **passes**.

So no code change is required to *satisfy the gate*. It also matches the README's
injected-reader spirit — *ship the reader; the corpus stays with whoever grew it* — because
`Reader(corpus=…)` is injectable and the pinned `CORPUS` is only the shipped default. If
anything, the lane is **purer against the bar's no-network intent** than Jeles's full
package, whose sibling `conflict_scan` dials out.

One declaration nicety: `Reader` is the seam (the injectable capability). Declaring the
class is correct — the gate resolves a class or a function equally.

---

## 4. Recommendation — grow, don't inject

**Keep homestead-health's grown term-overlap reader. Do not inject Jeles's reader.**

### Why not inject

1. **Wrong posture.** Jeles's reader is engineered for a **writable, env-configured,
   network-fed verified-nugget corpus** (`put_nugget`/`log_gap`, SQLite SOIL collection,
   `verified_by`/machine/asserted kinds) with a **web-search sibling that egresses**
   (`conflict_scan` + `search_adapter`). homestead-health's reference lane is defined by the
   opposite invariants — **frozen** pinned literal (H-5), **no writes** at runtime, **never
   dials** (I-17). Injecting Jeles drags a mutable store, gap-logging side effects, and env
   collection wiring into a lane whose whole design is "the bytes are here, frozen."

2. **It would remove the wall.** The lane's H-7/H-2 defense is a **structural no-subject
   allowlist** (`_check_no_subject_can_enter`) and a schema of exactly
   `{question, answer, source, license}`. Jeles's nugget dict is open and carries
   provenance/verification fields with no such wall. Adopting Jeles's shape wholesale
   deletes the one invariant that keeps the reference lane clear of "the practice of
   medicine." That is a regression the promotion bar should *reward the lane for keeping*,
   not trade away.

3. **No retrieval win to buy.** Both readers are the same deterministic lexical-overlap
   family — neither uses embeddings — so injecting Jeles does not upgrade the *kind* of
   retrieval. It only swaps a small, purpose-fit reader for a larger, differently-scoped
   machine plus its store and network posture.

4. **Provenance mismatch.** homestead-health cites `source` + `license` (public-domain /
   CC-BY) and rides that through every `Result`. Jeles's `verified_by`/`verified_at`/kind
   model is meaningful for human-checked nuggets and is dead weight (or misleading) over
   pinned public-domain reference.

### What to borrow instead (grow toward the standard, don't import it)

Jeles's genuinely portable lesson is **"ranking and answering are different decisions."**
homestead-health's `ask()` currently surfaces *any* overlapping entry. A one-content-word
overlap can float a barely-related entry to the top. A cheap, in-lane, stdlib-only
refinement — no dependency on Jeles — would adopt Jeles's discipline:

- Keep `ask()` as the loose rank (its current best-first behavior), and/or
- Add a confidence gate à la `_confidence`/`MIN_ASK_SCORE`: require symmetric overlap (an
  unmatched query content word is disqualifying) before returning an entry as a confident
  answer, so a weak lexical brush-past yields *nothing* rather than a misleading citation.
  This strengthens the same H-2 "don't improvise" instinct the lane already has, using a
  mechanism the fleet already trusts.

This preserves the no-subject wall, the frozen corpus, and the no-network guarantee while
importing Jeles's *idea* (the part that is the actual standard) rather than its *code* (the
part scoped to a different job).

### For the promotion.json

```json
"semantic_seam": "homestead_health.reference_lane:Reader"
```

with `core_module: "homestead_health"` and the core kept import-pure (it already is).

---

## Files cited

Jeles (cloned `https://github.com/rudi193-cmd/Jeles`, depth 1):
- `jeles/corpus.py` — `search_nuggets`, `ask_corpus`, `_score`, `_confidence`, `_tokens`,
  `MIN_ASK_SCORE`, `to_search_hit`; injected SQLite SOIL store.
- `jeles/reactions/conflict_scan.py` — `frame_queries`, `_witnesses`, `react`/`apply`,
  `WITNESS`; the refute-not-resemble reaction over an injected `searcher`.
- `jeles/reactions/search_adapter.py` — `make_searcher` and the SearXNG/Brave/Tavily/DDG
  backends; the network edge behind conflict_scan.
- `jeles/__init__.py` — public surface and top-level import purity.

This repo:
- `stores/promote_check.py` — the `semantic_seam [M]` gate (module:symbol existence check),
  `import_pure_core`, `inversion`.
- `stores/README.md` — "The one seam every store shares."
- `apps/homestead-health/homestead_health/reference_lane.py` — `Reader`, `Corpus`, `Entry`,
  `Result`, `ask`, `_check_no_subject_can_enter`.
- `apps/homestead-health/homestead_health/reference.py` — the pinned schedule (H-5 context).

[`jeles/corpus.py`]: https://github.com/rudi193-cmd/Jeles/blob/main/jeles/corpus.py
[`jeles/reactions/conflict_scan.py`]: https://github.com/rudi193-cmd/Jeles/blob/main/jeles/reactions/conflict_scan.py
[`jeles/reactions/search_adapter.py`]: https://github.com/rudi193-cmd/Jeles/blob/main/jeles/reactions/search_adapter.py
[`jeles/__init__.py`]: https://github.com/rudi193-cmd/Jeles/blob/main/jeles/__init__.py
[`stores/promote_check.py`]: ../../../stores/promote_check.py
[`apps/homestead-health/homestead_health/reference_lane.py`]: ../../../apps/homestead-health/homestead_health/reference_lane.py
[`…/reference.py`]: ../../../apps/homestead-health/homestead_health/reference.py
