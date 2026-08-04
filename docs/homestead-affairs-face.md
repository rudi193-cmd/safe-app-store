# Homestead · Affairs — face 4

*Drafted 2026-08-04 to replace §5b and the face-4 rows in the fleet placement
draft. Written in that document's register so it can be dropped in. Supersedes
the **Homestead · Sovereign** naming and the interim **Homestead · Case**
proposal; the repo structure underneath survives both.*

---

## The face

**Artifact:** **Homestead** — the household, and what it holds.
**Leg:** **Affairs** — the practical business of running it.
**Org:** **`homestead-affairs`** · **Base seat:** **`homestead`**

> **Homestead · Affairs — the affairs you handle yourself.**

That charter line is where the thesis lives. Not in the org handle.

## What this face is

A homesteader is their own everything. No specialist stands between them and the
work: they keep their own log, know what the season owes them, fix their own
equipment, doctor their own animals, keep their own books, and handle their own
deeds and disputes.

The modern household is in the same position and rarely notices. **It has no
institutional memory of itself.** Every institution holds one slice — the
insurer, the county, the clinic, the lender, the school — and nobody holds the
whole except you, in a drawer, badly.

| A homesteader does alone | The modern household equivalent |
|---|---|
| Keeps the farm log — planted, yielded, broke | Deeds, titles, IDs, warranties, policies, receipts |
| Knows what the season owes | Renewals and filings: registration, insurance, property tax, benefits recertification |
| Fixes their own equipment | Maintenance history — car, roof, HVAC, appliances |
| Doctors their own animals and family | Health records nobody holds end to end |
| Keeps their own books | Budget, taxes, benefits |
| Handles their own deeds and disputes | **Legal matters** — the first module built |
| Knows the land and its bounds | Survey, easements, assessment, utilities |

This face is **not all of a household's life** — it is the part a household
**must handle itself**. Records, deadlines, obligations, upkeep. The practical
burden, not the joy. That distinction is what lets the leg say *no*, which is
the work a leg does.

## Why "Affairs", recorded so it is not re-derived

Three earlier names, and why each failed — the failures are the instructive
part.

**1. `Sovereign` — the semantic slide.** The intent was **hands-on-ness**: you
work your own affairs the way you work your own land. That intent is exactly
right and is the whole point of this face. The word was not. *Homestead* (you
work it yourself) → *Sovereign* (self-governing) → *sovereignty test, exit,
anti-capture* (political autonomy) → *"settler order without a county — compact,
claim, ledger, fence, remedy"* (parallel institutions). Every step follows
plausibly from the one before. Four steps on, the face describes building an
alternative legal order, which this is not and never was. The pivot is
**sovereign** itself, carrying two unrelated senses — *doing it yourself* and
*not subject to authority*. The first was meant; the second is what gets built
on.

Note also that hands-on-ness is **already carried by "Homestead."** A homestead
*is* worked by hand. Putting self-reliance in the artifact *and* the leg is what
over-rotated the face into an ideology. The leg's job is to name the domain.

**2. `Case` — too narrow.** Proposed while the face was mistaken for *the law
face*. Law is one module of a homestead, not its definition. A leg of `Case`
admits only legal matters and excludes the household's records, money,
maintenance, and renewals — most of what this face is for.

**3. `Life` / `Living` — no edge, and a live collision.**
[Homestead Living](https://homesteadliving.com/) is an established bi-monthly
homesteading magazine with named contributors; `homestead-living` would be
permanently confused with it. More fundamentally, *Life* excludes nothing —
learning is life, play is life, money is life — so it overlaps every other face
and cannot defend this one's edges. This is the face that most needs edges.

**Why `Affairs` works.**

- **"Getting your affairs in order"** is a phrase every reader already knows,
  and it covers legal, financial, medical, and property in one word while
  naturally excluding play and learning.
- It is a **substance**, satisfying the die's own rule — *short display name ·
  substance suffix* — alongside Memory, Knowledge, Data, Programs, Play.
- It **names the domain without claiming authority in it** — see the next
  section, the constraint that rules out the otherwise-obvious words.
- *Own affairs* is the language of the German exemption for handling one's own
  matters; a quiet asset for the legal module.

**Also rejected:** `Recourse` (correct substance, doesn't read as legal to a lay
reader), `Law` (clearest read, but org `homestead-law` + product `homestead-law`
is the collision §32 forbids), `Rights` / `Justice` / `Counsel` / `Practice`
(all over-claim; the last two are hazardous), `Keep` (native to the repo's own
"keeping record" vocabulary but cold and archaic — **retained as a candidate
name for the shared engine**, below), `Upkeep` (warm and apt for maintenance,
odd against a custody matter).

## The naming is a legal control, not a preference

This is the only face on the die whose name carries regulatory consequence, so
the reasoning is recorded rather than assumed.

*In re Reynoso*, 477 F.3d 1117 (9th Cir. 2007), swept a bankruptcy software
provider into statutory **petition-preparer** status under 11 U.S.C. § 110
because it held itself out as *"an expert system [that] knows the law."* The
determinative fact was **self-presentation**, not what the code did. *FTC v.
DoNotPay* (final order Jan. 2025) is the same shape under FTC Act § 5 —
liability for capability claims. See
[`apps/law-gazelle/docs/legal_obligations_us.md`](../apps/law-gazelle/docs/legal_obligations_us.md).

Two consequences:

1. **The org handle sits in the URL of every product on this face,
   permanently.** `github.com/homestead-sovereign/homestead-law` is what a
   clinic's ethics counsel reads during diligence; in bankruptcy and family
   court, "sovereign" beside a filing-adjacent tool overlaps a pattern those
   courts treat with hostility. A pilot could be lost on the handle with the
   code entirely blameless.
2. **The hands-on framing is the safest available positioning, not merely a
   softer one.** Pro se self-help is the lowest-exposure deployment model in the
   whole US analysis — a person may always represent themselves. *The affairs
   you handle yourself* is accurate **and** defensive. The anti-government
   reading created exposure; the intended reading creates none.

The name must describe **what the household holds**, never **what the software
knows**. That is the information-vs-advice line the code already enforces
(`workflow._fact_blocked`), expressed in the name.

## The engine is already generic — law was the hardest module, not the product

Strip the legal vocabulary from Law Gazelle and what remains is domain-neutral:

- a **canonical record store** the user owns and the app may not mutate,
- a **sidecar** for the user's own annotations, kept separate from the record,
- **deadlines** computed from the records and surfaced before anything else,
- **claims tied to source documents**, and
- **mandatory human verification** before anything is used.

`sync_cases`, `check_stale`, `_merge_overlay`, `_fact_blocked`, the urgent
queue, the chronology builder — none of that is legally specific. It is a
household record engine with a legal domain layer on top.

Which reframes the build: **law was not the product, it was the hardest first
module.** Deadlines that cause real harm when missed, evidence that must tie to
a source, facts that may never be invented. An engine that survives custody and
bankruptcy will carry warranty claims and service histories without strain.

**Open — extract the shared engine.** A pinned, import-pure record/deadline
library consumed by every module on the face. It satisfies the promotion bar's
import-pure-core requirement with something real to point at (finish-list D-2),
satisfies the Möbius rule *depend on contracts, not apps*, and gives this face
something **other faces can pin** — today face 4 is nearly all consumer and
little producer. **`homestead-keep`** is the candidate name; *keeping* is the
right verb even though it was the wrong leg.

## Repos

| Repo | Role |
|---|---|
| `.github` | Org profile |
| **`homestead`** | Base orchestrator seat — portfolio / orient for the face |
| **`homestead-law`** | **Module one.** Promoted `law-gazelle`; prose name stays **Law Gazelle** / **Gazelle**. Not a monorepo umbrella, not a sibling `gazelle` repo. |
| **`private-ledger`** | **Module two, already built.** Household money, local-first SQLite, "mirror not judge" — the homesteader keeping their own books. Currently has no die face. Name open: it has its own identity, and the earlier rejection of `homestead-ledger` was about a settler-order module *inside* `homestead-law`, a different question. |
| **`homestead-keep`** *(proposed)* | The shared record/deadline/evidence engine — import-pure, pinned by the modules |
| **`awesome-sovereign-software`** | Public catalog + report — **keeps its name and its politics** |

**On the catalog.** The sovereignty stance was not wrong, it was attached to the
wrong object. A **software catalog** is exactly where a sovereignty test belongs
— that is what such a test is *for*. The problem was only that an org handle
propagates the stance onto a legal product's URL.

**Later modules, same shape:** household records and renewals, maintenance
history, property, family health records. Each is a module; none is a new face.

**Not on this face:** almanac catalogs (public data belongs to face 3), Terpsi
ward programs, Hornbook learning, Forge/Play toys, Nestor (center org).

## Two levels, and don't confuse them

The old draft produced `homestead-ledger` / `homestead-compact` as repo names by
collapsing these:

- **Modules** are sibling repos on the org — law, money, upkeep. Different
  domains of a household's affairs.
- **Matter packs** live *inside* `homestead-law` — custody, bankruptcy, workers'
  comp, and later housing, benefits, debt defense, small claims. Different kinds
  of legal matter; they belong to the registry, not the org.

**The five settler-order names** (`compact / claim / ledger / fence / remedy`)
came from the framing this section removes. Some are ordinary legal words that
may survive on merit; *compact* and *fence* came from the settler framing
specifically. **Re-derive from the domain; do not inherit them through a
rename.**

## Promotion: `law-gazelle` → `homestead-law`

The earlier draft described this as *"the entire `apps/law-gazelle` tree moves
here as one repo."* That is the destination, but it is not a transfer.

**The store treats promotion as an extraction with architectural preconditions;
the draft treated it as a move.** `stores/promote_check.py` requires
`inversion [M]` (the core must not import its host), an import-pure core, and a
semantic-search seam over injectable knowledge. Law Gazelle imports
`vault_paths` and `pg_sqlite_shim` from `libs/` **without declaring them** — a
wholesale tree move carries that coupling across the org boundary and lands it
broken. Reconcile before transfer day, not during it.

This makes the Möbius rules bite earlier than expected: *depend on contracts,
not apps* · *pinned immutable refs* · *no silent vendoring* are the same
requirement as finish-list **A-1**, currently filed as hygiene. It is not
hygiene; it is step one of the transfer.

**A green gate is not a correctness guarantee.** `tests_green [M]` checks that
the suite runs and passes. It does — 72 green. It does **not** test long-form
dates, and [`bug_list.md`](../apps/law-gazelle/docs/bug_list.md) BUG-1/BUG-2 are
critical defects in the deadline arithmetic that would sail straight through
promotion. Shipping the flagship of this face on a green gate would trust the
gate to say something it never said. **Fixing BUG-1 and BUG-2, with regression
tests, is a transfer precondition.**

## Matter types inside `homestead-law`

**Retain all three: custody, workers' comp, bankruptcy.** The earlier expansion
line named only "custody wedge + workers' comp scaffold." Bankruptcy is the
**highest-exposure** matter type in the legal review — *Reynoso* is literally
about bankruptcy software — which argues for deliberate handling, not quiet
omission. It is also the doctrinal root of the artifact's name: the **homestead
exemption** protects a household's home equity from creditors.

**The registry precedes any fourth.** `MATTER_NAV` hardcodes the three, with
matching per-matter functions in `case_store`. A matter-type registry —
descriptors carrying tables, item types, deadline rules, detail renderers — is
the prerequisite for any expansion.

Ranked candidates when it exists: **housing** (eviction and foreclosure — the
most on-name matter possible, since *homestead* is keeping the roof, and
eviction clocks run in days), **debt collection defense**, **benefits appeals**
(structurally identical to workers' comp), and **small claims** (the lowest-UPL
forum that exists — many small claims courts bar lawyers outright).

**Out on risk, not on fit:** immigration (notario UPL enforcement is aggressive,
downside is deportation), protective orders and DV (safety-critical), traffic
and minor criminal (*TIKD* lost a Florida UPL case on traffic tickets). **And
never a forms-and-instructions product** — *UPL Comm. v. Parsons Technology*
enjoined Quicken Family Lawyer on exactly that shape.

## What crosses the org boundary

| Takes from other faces | Gives to other faces |
|---|---|
| Nestor to score **catalog entries**; `willow-gate` and vault paths as pinned contracts; SAFE manifest schema; **`justice-almanac`** for court-rules and deadline data | Sovereignty test + awesome list; `homestead-law`; **`homestead-keep`** as a pinnable record/deadline engine |

**A Möbius edge worth drawing:** court rules and deadline tables are *public
data*, and public data belongs to Almanac · Data, which holds the map.
`justice-almanac` already exists on that face. So the **tables** are pinned from
the almanac; the **engine** lives here. Face 4 takes data and returns a verified
engine.

**Required carve-out — Nestor never consumes household affairs.** The Terpsi row
states this for ward data ("Nestor **spec** for ward-aware checks", *not ward
data*). This face's row never did, and household records are the most
privilege-loaded data on the die. The general rule (*Nestor consumes public /
published only*) covers it, but it must be **written on this line**, because
this is the line a partner org or a regulator reads. Nestor gets schemas, gates,
and catalog entries from this face. It does not get affairs.

This is also the constellation answer for these apps generally: face 4 is the
organ that **cannot** deposit into the shared bloodstream. See
[`docs/law-gazelle-expansion.md`](law-gazelle-expansion.md).

## Opposite pair

| Face A | Face B | Tension |
|---|---|---|
| **Homestead · Affairs** | **Forge · Play** | **What you must handle vs. what you choose to make.** Affairs arrive whether you wanted them or not, on someone else's schedule; the forge is entered freely. Obligation against craft. |

Sharper than the previous "ground you hold vs. workshop," and it never depended
on the sovereignty reading.

*(Face 5 reorders to **Forge · Play** — Forge, the promoted SAFE app store, is
the artifact; Play is the leg. Org `forge-play` was already artifact-first; the
seat becomes `forge`. Seat and product coincide there legitimately: unlike
Homestead, the store **is** that face's orchestrator.)*

## Scaling posture (§12 row)

| Face | Expands with humans by… | Repo / product scaling | Stays thin |
|---|---|---|---|
| **Homestead · Affairs** | More **domains** a household handles itself, and more **installs** of each module | Modules as sibling repos; matter packs **inside** `homestead-law`; one shared engine | Not almanac catalogs; not a repo per matter type |

Field scale here is **boxes, not repos** — more households running the same
programs, each holding its own records locally. That is the whole architecture.

## Open

- [ ] Ratify **Homestead · Affairs**; org `homestead-affairs`
- [ ] Place **`private-ledger`** on this face; settle whether it keeps its name
- [ ] Extract the shared record/deadline engine (`homestead-keep`?)
- [ ] Re-derive module names from the domain — the settler-order five do not
      carry forward
- [ ] Fix BUG-1 / BUG-2 + regression tests — **transfer precondition**
- [ ] Declare the host-lib dependencies (finish-list A-1) — step one of the
      Möbius contract, not hygiene
- [ ] Matter-type registry before any fourth matter type
- [ ] Add the *"Nestor takes no affairs"* carve-out to this face's Möbius row
- [ ] Draw the `justice-almanac` → deadline-engine edge in §12
- [ ] Reconcile MISSION.md — it tells an access-to-justice story (pilot org,
      docassemble, grants) that is not the same product as *the affairs you
      handle yourself*; both are defensible, they are not identical, and MISSION
      is still the only document a partner org would read

---

## Related

- [`docs/law-gazelle-expansion.md`](law-gazelle-expansion.md) — expansion directions, and the constellation question
- [`apps/law-gazelle/docs/finish_list.md`](../apps/law-gazelle/docs/finish_list.md) — 24 tracked items across four tracks
- [`apps/law-gazelle/docs/bug_list.md`](../apps/law-gazelle/docs/bug_list.md) — 12 defects, two critical
- [`apps/law-gazelle/docs/legal_obligations_us.md`](../apps/law-gazelle/docs/legal_obligations_us.md) — *Reynoso*, § 110, UPL by deployment model
- [`apps/law-gazelle/docs/legal_obligations_intl.md`](../apps/law-gazelle/docs/legal_obligations_intl.md) — EU AI Act Annex III, GDPR Art. 9
- [`stores/README.md`](../stores/README.md) — the promotion bar

ΔΣ=42
