# Homestead · Case — face 4

*Drafted 2026-08-04 to replace §5b and the face-4 rows in the fleet placement
draft. Written in that document's register so it can be dropped in. Supersedes
the **Homestead · Sovereign** naming; the structure underneath it survives
unchanged.*

---

## The face

**Artifact:** **Homestead** — the household, and what it holds.
**Leg:** **Case** — the legal matter itself.
**Org:** **`homestead-case`** · **Base seat:** **`homestead`**

> **Homestead · Case — the law you handle yourself.**

That charter line is where the thesis lives. Not in the org handle.

## Why this name, recorded so it is not re-derived

The previous draft read **Homestead · Sovereign**, and the intent behind it was
**hands-on-ness** — you work your own case, the way you work your own land. That
intent is right and it is the whole point of this face. The word chosen for it
was not.

**The slide that has to be prevented.** *Homestead* (you work it yourself) →
*Sovereign* (self-governing) → *sovereignty test, exit, anti-capture* (political
autonomy) → *"settler order without a county — compact, claim, ledger, fence,
remedy"* (parallel institutions). Every step follows plausibly from the one
before it. Four steps on, the face describes building an alternative legal order
— which is not this product and never was. The pivot is **sovereign** itself,
a word carrying two unrelated senses: *doing it yourself*, and *not subject to
authority*. The first was meant. The second is what gets built on.

**Hands-on is already carried by "Homestead."** A homestead *is* worked by hand;
the artifact does that job alone. Putting self-reliance in the artifact **and**
the leg is what over-rotated the face into an ideology. The leg's job is to name
the **domain** — and the domain is legal matters.

**Why "Case" specifically.**

- It is the plainest possible word for what this is. "My custody case." "My
  bankruptcy case." That is how the actual user talks, and the actual user is a
  parent managing a matter out of a shoebox, not a reader of casebooks.
- **It is the vocabulary the code already speaks** — `case_store.py`,
  `sync_cases()`, `list_cases()`, `get_case_detail()`, `case_key`, "case
  databases," "case command center." The face name matches the domain model
  instead of sitting on top of it, which is what *Memory* and *Data* do for
  their faces and what *Sovereign* never did.
- It obeys this document's own rule — **short display name · substance suffix**.
  Memory, Knowledge, Data, Programs are all substances. *Sovereign* was the
  only leg naming a political posture rather than a material. (Face 5's
  artifact/leg ordering is unsettled in the placement draft — **Forge** is the
  promoted SAFE app store, i.e. an artifact, not a leg.)
- **It says "legal" without claiming legal authority.** This is the constraint
  that rules out the otherwise-obvious alternatives, and it is not stylistic —
  see below.

**Rejected, and why:**

| Candidate | Why not |
|---|---|
| **Sovereign** | The semantic slide above, plus a live legal risk — see the next section. |
| **Recourse** | Correct legal substance, but does not read as *legal* to a lay reader, which is the audience that matters here. |
| **Law** | Clearest read of all, but collides with this document's own rule: org `homestead-law` + product `homestead-law` gives `github.com/homestead-law/homestead-law`, the exact shape §32 forbids. Would force renaming a product name already settled. |
| **Rights**, **Justice**, **Counsel**, **Practice** | All read clearly and all over-claim — they assert the tool knows the law or performs legal work. *Practice* and *Counsel* are outright hazardous. |
| **Docket** | Genuine runner-up; unmistakably legal, concrete, and literally what the Today screen is. Slightly more courthouse-insider than "case." Hold in reserve. |

## The naming is a legal control, not a preference

This face is the only one on the die whose name carries regulatory
consequence, so the reasoning is recorded here rather than assumed.

*In re Reynoso*, 477 F.3d 1117 (9th Cir. 2007), swept a bankruptcy software
provider into statutory **petition-preparer** status under 11 U.S.C. § 110
because it held itself out as *"an expert system [that] knows the law."* The
determinative fact was **self-presentation**, not what the code did. *FTC v.
DoNotPay* (final order Jan. 2025) is the same shape under Section 5 —
liability for capability claims. See
[`apps/law-gazelle/docs/legal_obligations_us.md`](../apps/law-gazelle/docs/legal_obligations_us.md).

Two consequences follow:

1. **The org handle is in the URL of every legal product on this face,
   permanently.** `github.com/homestead-sovereign/homestead-law` is what a
   clinic's ethics counsel reads during diligence. In bankruptcy and family
   court specifically, "sovereign" plus a filing-adjacent tool overlaps with a
   filing pattern those courts treat with active hostility. The pilot could be
   lost on the handle with the code entirely blameless.
2. **The hands-on framing is the safest available positioning, not merely a
   softer one.** Pro se self-help is the lowest-exposure deployment model in the
   entire US analysis — a person may always represent themselves. "The tool you
   use to handle your own case" is accurate *and* defensive. The anti-government
   reading created exposure; the intended reading creates none. Same instinct,
   opposite consequence.

The name must therefore describe **what the app organizes**, not **what it
knows**. That is the same information-vs-advice line the app already enforces in
code (`workflow._fact_blocked`), expressed in the name.

## Repos

| Repo | Role |
|---|---|
| `.github` | Org profile |
| **`homestead`** | Base orchestrator seat — portfolio / orient for the face |
| **`homestead-law`** | **The promoted product.** Prose name stays **Law Gazelle** / **Gazelle**. Not a monorepo umbrella; not a sibling `gazelle` repo. |
| **`awesome-sovereign-software`** | Public catalog + report — **keeps its name and its politics** |

**On the catalog.** The sovereignty stance is not wrong; it was attached to the
wrong object. A **software catalog** is exactly where a sovereignty test
belongs — that is what such a test is *for*. The problem was only that an org
handle propagates the stance onto a legal product's URL. Catalog keeps the
word; the handle does not.

**Not on this face:** almanac catalogs, Terpsi ward programs, Hornbook learning,
Play toys, Nestor (center org).

## Promotion: `law-gazelle` → `homestead-law`

The previous draft described this as *"the entire `apps/law-gazelle` tree moves
here as one repo."* That is the destination, but it is not a transfer.

**The store treats promotion as an extraction with architectural preconditions;
this document treated it as a move.** `stores/promote_check.py` requires
`inversion [M]` (the core must not import its host), an import-pure core, and a
semantic-search seam over injectable knowledge. Law Gazelle currently imports
`vault_paths` and `pg_sqlite_shim` from `libs/` **without declaring them** — a
wholesale tree move carries that coupling across the org boundary and lands it
broken. Reconcile before transfer day, not during it.

This also makes the Möbius rules bite earlier than expected. *Depend on
contracts, not apps* · *pinned immutable refs* · *no silent vendoring* are the
same requirement as finish-list **A-1**, which is currently filed as hygiene.
It is not hygiene; it is step one of the transfer.

**A green gate is not a correctness guarantee.** `tests_green [M]` checks that
the suite runs and passes. It does — 72 green. It does **not** test long-form
dates, and
[`apps/law-gazelle/docs/bug_list.md`](../apps/law-gazelle/docs/bug_list.md)
BUG-1/BUG-2 are critical defects in the deadline arithmetic that would sail
straight through promotion. Shipping the flagship of this face on a green gate
would be trusting the gate to say something it never said. **Fixing BUG-1 and
BUG-2, with regression tests, is a precondition of transfer.**

## Matter types, and the module question

**Retain all three: custody, workers' comp, and bankruptcy.** The previous
expansion line named only "custody wedge + workers' comp scaffold." Bankruptcy
should not be dropped quietly — it is the **highest-exposure** matter type in
the whole legal review (*Reynoso* is literally about bankruptcy software), which
is an argument for deliberate handling, not omission. It is also the doctrinal
root of the artifact's own name: the **homestead exemption** is the protection
of a household's home equity from creditors.

**Sequencing: the registry precedes the modules.** `MATTER_NAV` hardcodes the
three types, with matching per-matter functions in `case_store`
(`load_coparent_meta()`, `bankruptcy_overview()`, `workers_comp_overview()`).
There is no seam for a fourth. A matter-type registry — descriptors carrying
tables, item types, deadline rules, and detail renderers — is the prerequisite
for **any** expansion of this face, and it maps cleanly onto the promotion bar's
import-pure-core-plus-injected-knowledge shape. Modules before the registry is a
second floor before a staircase.

**The five module names need re-deriving.** `compact / claim / ledger / fence /
remedy` were derived from "settler order without a county" — the framing this
section removes. Some (*claim*, *remedy*, *ledger*) are ordinary legal words that
may survive on their own merits; *compact* and *fence* came from the settler
framing specifically. They should be re-derived from the domain rather than
inherited through a rename. **Open — do not carry them forward by default.**

## What crosses the org boundary

| Takes from other faces | Gives to other faces |
|---|---|
| Nestor to score **catalog entries**; Almanac for "survives vendor" receipts; `willow-gate` and vault paths as pinned contracts; SAFE manifest schema | Sovereignty test + awesome list; `homestead-law` as the flagship promoted app; the matter-type pack pattern |

**Required carve-out — Nestor never consumes case data.** The Terpsi row states
this for ward data ("Nestor **spec** for ward-aware checks", *not ward data*).
The Sovereign row never did, and case files are the most privilege-loaded data
on the die. The general rule (*Nestor consumes public / published only*) already
covers it, but it must be **written on this face's line**, because this is the
line a partner org or a regulator reads. Nestor gets schemas, gates, and catalog
entries from this face. It does not get matters.

This is also the constellation answer for this app generally: it is the organ
that **cannot** deposit into the shared bloodstream. See
[`docs/law-gazelle-expansion.md`](law-gazelle-expansion.md).

## Opposite pair

| Face A | Face B | Tension |
|---|---|---|
| **Homestead · Case** | **Play · Forge** | **What you must do vs. what you choose to do.** A case arrives whether you wanted it or not, on someone else's schedule; play is entered freely. Obligation against craft. |

Sharper than the previous "ground you hold vs. workshop," and it survives the
rename because it never depended on the sovereignty reading.

## Scaling posture (§12 row)

| Face | Expands with humans by… | Repo / product scaling | Stays thin |
|---|---|---|---|
| **Homestead · Case** | More **matter types** covered, and more **installs** of `homestead-law` | `homestead-law` (matter packs **inside** the repo) + `awesome-sovereign-software` | Not almanac catalogs; not a repo per matter type |

Field scale here is **boxes, not repos** — more households running the same
program, each holding its own case data locally. That is the whole architecture.

## Open

- [ ] Ratify **Homestead · Case**; org `homestead-case`
- [ ] Re-derive the module names from the domain (the settler-order five do not
      carry forward automatically)
- [ ] Fix BUG-1 / BUG-2 + regression tests — **transfer precondition**
- [ ] Declare the host-lib dependencies (finish-list A-1) — first step of the
      Möbius contract, not hygiene
- [ ] Matter-type registry before any module or fourth type
- [ ] Add the *"Nestor takes no case data"* carve-out to this face's Möbius row
- [ ] Reconcile MISSION.md — it currently tells an access-to-justice story
      (pilot org, docassemble, grants) that is not the same as *the law you
      handle yourself*; both are defensible, they are not the same product
- [ ] Confirm `homestead-law` as the product repo name under the new org
      (`github.com/homestead-case/homestead-law` — no collision)

---

## Related

- [`docs/law-gazelle-expansion.md`](law-gazelle-expansion.md) — the six expansion directions and the constellation question
- [`apps/law-gazelle/docs/finish_list.md`](../apps/law-gazelle/docs/finish_list.md) — 24 tracked items across four tracks
- [`apps/law-gazelle/docs/bug_list.md`](../apps/law-gazelle/docs/bug_list.md) — 12 defects, two critical
- [`apps/law-gazelle/docs/legal_obligations_us.md`](../apps/law-gazelle/docs/legal_obligations_us.md) — *Reynoso*, § 110, UPL by deployment model
- [`apps/law-gazelle/docs/legal_obligations_intl.md`](../apps/law-gazelle/docs/legal_obligations_intl.md) — EU AI Act Annex III, GDPR Art. 9
- [`stores/README.md`](../stores/README.md) — the promotion bar

ΔΣ=42
