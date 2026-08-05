# Two die-level rules

*Short note for the fleet placement draft. Both rules were worked out inside the
face-4 section ([`homestead-affairs-face.md`](homestead-affairs-face.md)) but
govern four faces each, so they belong at die altitude. Reasoning and worked
examples stay in that section; this is the statement.*

**Drafted 2026-08-04.**

---

## Rule 1 — Seats

**Current text:** base repos are *optional* — "an org can exist with only
`.github` + products until someone opens a seat; the base repo is the
**reserved slot** for that face's Jarvis/charter work."

**The problem:** that is the right default and the wrong absolute. The instinct
behind it — don't create empty orgs full of empty repos — is correct. But it
stops holding the moment a face has something **every module must share**: an
engine, a schema, a root. At that point the seat is not a reserved slot, it is a
**dependency**, and a dependency cannot be optional.

> **A seat is optional until the face has a shared artifact. Then it is
> mandatory, and it comes first — before the second module exists to pin it.**

**Where each face stands today:**

| Face | Seat | Shared artifact | Seat status |
|---|---|---|---|
| Willow · Memory | `willow` | Charter, envelopes, syscall table | **Mandatory** — §10 already tracks the transfer |
| Almanac · Data | `almanac` | `propagate-engine`, vertical index, template-first merge | **Mandatory** |
| Homestead · Affairs | `homestead` | `homestead.keep` — record/deadline/evidence engine | **Mandatory** |
| Forge · Play | `forge` | The store itself — the bar, manifest schema, promotion path | **Mandatory** (seat and product coincide) |
| Terpsi · Programs | `terpsi` | `terpsi-core`, once it exists | **Mandatory on arrival** |
| Hornbook · Knowledge | `hornbook` | None yet — UTETY and Jeles are independent | Optional |
| Die-Namic *(center)* | `die-namic` | Nestor is the product, not a shared seat artifact | Optional — the draft's own default is *no* |

Stated this way, four faces stop quietly violating a rule they were never
exceptions to. The rule was written for the simple case; most faces are not the
simple case.

**Corollary — ordering.** Where the seat is mandatory it is also *first*. A
module cannot pin an engine that does not exist, so the seat repo precedes the
second module on that face, not the other way round.

---

## Rule 2 — Roots

**Current text:** every persistence path derives from the vault root
(`WILLOW_STORE_ROOT`), per installer design D8 — enforced by
`libs/vault-paths` and checked by `tools/vault_leak_lint.py --strict` in
`store-ci.yml`.

**The problem:** that rule is written for apps running *inside* the fleet, for
the operator. It does not survive contact with a promoted product installed by
someone who has never heard of Willow.

> **Does someone who does not run the fleet install this?**
>
> - **No** → `~/.willow`, `vault-paths`, no change. That is most of `apps/*`.
> - **Yes** → its own root. You cannot ask a stranger to adopt your
>   infrastructure's vocabulary.

**Why**, precisely: a legal aid clinic opening a custody matter should not have
to set `WILLOW_STORE_ROOT`, and a shipped product carrying its host's brand in
its environment is the same coupling `inversion [M]` exists to forbid —
expressed in paths instead of imports.

**What this is not.** It is **not** isolation. `~/.homestead` and `~/.willow`
are the same uid with the same permissions, and a directory name is not a
security boundary. What keeps Nestor out of another face's data is the gate and
the store-scope wall, and that holds whichever path the data sits at. Any
argument for a separate root that leans on isolation is wrong.

**Where each face stands today:**

| Face | Installed by non-fleet humans? | Root |
|---|---|---|
| **Homestead · Affairs** | **Yes** — clinics, self-represented litigants | **`~/.homestead`** |
| **Terpsi · Programs** | **Yes** — bands, schools, camps, district IT | **Own root, when it ships** |
| Hornbook · Knowledge | Possibly — UTETY campus / reading rooms | Revisit at promotion |
| Forge · Play | Makers, who may or may not run the fleet | Revisit at promotion |
| Almanac · Data | Mostly public repos, not installs | `~/.willow` |
| Willow · Memory | Fleet infrastructure by definition | `~/.willow` |

**Terpsi is the second instance, and it is the sharper one.** Institutions
install it, and its ward data — minors, program records — is the most regulated
data on the die. Whatever `~/.homestead` establishes, Terpsi will want on the
same terms and with more at stake.

**The root belongs to the household or the institution, not to the face.**
Modules that serve the same subject share a root: `homestead-law` and
`private-ledger` both sit under `~/.homestead`, because a household's affairs
are one thing and splitting law from money into two roots would be the actual
mistake.

**`~/.willow` is not being migrated.** Adding a root for a shipping face is
cheap and lands the benefit where it accrues — the install. Migrating the fleet
root wholesale would cost `vault-paths`, the leak linter, every app's path
module, `CLAUDE.md`, the docs, **and a data move on a machine holding live case
files** — while buying nothing a stranger would ever see.

**Ordering constraint.** `tools/vault_leak_lint.py` treats a persistence path as
clean only when the line derives from `WILLOW_STORE_ROOT` / `WILLOW_HOME`;
anything else home-rooted holding data is a leak. `store-ci.yml` runs it
`--strict`. **Teach the linter the new root before moving path resolution**, or
`vault_leak [M]` flips from PASS to FAIL and CI reddens. This applies to every
face that adopts its own root, not just the first.

---

## Related

- [`docs/homestead-affairs-face.md`](homestead-affairs-face.md) — where both rules were derived, with the worked example
- [`apps/law-gazelle/docs/finish_list.md`](../apps/law-gazelle/docs/finish_list.md) — Track E, the first implementation
- [`stores/README.md`](../stores/README.md) — the promotion bar
- `tools/vault_leak_lint.py` · `libs/vault-paths` — what enforces Rule 2 today

ΔΣ=42
