---
kind: spec
name: intake-desk
description: "The desk where an unverified human account enters the system, is routed against what is already known, and is witnessed by someone who is not its author."
status: proposed
b17: SAPS1
---

# The Intake Desk — Spec

> **One sentence:** A local-first desk that takes an unverified human account,
> keeps it whole, breaks out the claims inside it, routes each claim against
> what is already known, and refuses to publish anything on the word of the
> person who filed it.

`ΔΣ=42` · Proposed 2026-08-04. Downstream of [`VISION.md`](../../VISION.md) Patterns
1–3 and [`stores/README.md`](../../stores/README.md).

---

## 0. Why this exists

The store already has four organs of a memory system:

```
field-notes   →   the-binder   →   ask-jeles   →   story-timeline
  (capture)       (connect)        (search)          (compose)
```

Every arrow points **into** the vault. Nothing takes testimony from a person who
is not the operator, and nothing hands a story back. Two apps already do intake
well — `nasa-archive` (consented oral history, cultural principles as columns)
and `the-squirrel` (confidence-graded family narrative) — but each hardcodes it
for one domain. The desk is that capability, generalized, with the domain
injected.

**Audiences, in build order.** Same pipeline, three clocks:

| Audience | Clock | The account is | Publishing means |
|---|---|---|---|
| Historical society / archive | decades | a recorded interview | the society's own catalog |
| Reporter / newsroom | days | a source conversation, a tip | a story with a sourcing trail |
| Writer | whatever | their own raw idea, unresearched | a draft with the checkable parts checked |

Build for the archive. It has the least money, the most volunteers, the most
material actively rotting, and it already practices consented oral history — so
the ethics are native rather than bolted on. The other two are the same desk
with a shorter retention policy.

---

## 1. The law it inherits

The desk does not invent governance. It is
[`CLAUDE.md`](../../CLAUDE.md) §5–§8 with *story* substituted for *build*:

| Store law (about code) | Desk (about an account) |
|---|---|
| §5 `apps/` is a contested commons, **untrusted by default** | intake is untrusted; nothing is fact on arrival |
| §6 each build reads and writes **only its own lane** | a source cannot vouch for itself |
| §7 **attributed to its maker**, ideally signed | every statement carries narrator + taker |
| §8 promotion is **witnessed**, `verified_by ≠ author` | nothing publishes on its author's word alone |
| §8 the bar is enforced fail-closed by `promote_check.py` | the publish gate is fail-closed |
| §4 **archive, don't delete** | corrections and retractions are appended, never erased |
| `stores/README.md` — *ship the mold and the reader; the wood stays* | the instrument travels; the corpus never leaves |

The last row is the one that will be under pressure the moment this works. It is
enforced in §9, not in prose.

---

## 2. Nouns

Five, and the separation between the first two is the whole design.

**Statement** — what a person actually said or wrote, verbatim, whole,
immutable. The recording, the transcript, the writer's raw dump. Never edited,
never normalized, never deleted. Everything else points *back into* it by
character offset.

**Claim** — one checkable assertion extracted from a statement. `(subject,
predicate, object, time, place)`, loosely. A statement yields 0..n claims. A
claim without a `statement_id` and an offset span cannot exist — there is no
free-floating fact in this system.

**Narrator** — the person whose account it is. *Usually not the operator.* This
is precisely the axis [`libs/subject-consent`](../../libs/subject-consent/) was
built for: consent for a third party the data is *about*.

**Taker** — the person who ran the session. The byline on the intake, not on the
truth.

**Docket** — what the routing pass returns for a claim. Evidence, agreement,
disagreement, and gaps. **Never a verdict.**

---

## 3. The lifecycle

```
   filed ──▶ routed ──▶ ruled ──▶ published
     │          │         │
     │          │         └──▶ withheld   (consent revoked / narrator asked)
     │          │         └──▶ disputed   (ruled, contested, both kept)
     └──────────┴──────────────▶ uncheckable  (terminal, and legitimate)
```

Six states, one hard rule per transition:

1. **filed** — a statement exists with a narrator, a taker, and a consent record.
   No consent record → the statement is not filed. *Absence is not consent.*
2. **routed** — the machine has produced a docket. This state is reachable
   without a human and is **not** an assertion of anything.
3. **ruled** — a human has judged the claim. The ruler is recorded. **The ruler
   may not be the narrator and may not be the taker.**
4. **published** — the claim may leave the vault, in the formats §9 permits.
5. **withheld** — consent revoked, or the narrator asked. The record stays; the
   export stops. Never a delete.
6. **uncheckable** — no source could exist. A first-person feeling, a private
   moment, a room with two people in it and one of them is dead. **This is a
   successful outcome, not a failure**, and it is the ΔΣ=42 column made
   operational.

---

## 4. Storage

Local-first SQLite, per [`VISION.md`](../../VISION.md) §"Direction locked" — the desk must
run with **zero Willow and zero Postgres**. Willow/Jeles are an optional
enrichment seam (§7), never a dependency. `nasa-archive`'s Supabase schema is the
proven ancestor; this is that shape, localized and de-domained.

```sql
-- Enums as CHECK constraints (SQLite).

-- How a fact entered. Extends nasa-archive's source_type with the two
-- states the general desk needs and a domain archive did not.
--   public_record          — census, court filing, newspaper, web archive
--   oral_history_consented — a person said it, in session, and consented
--   authored               — the writer's own unresearched assertion
--   unverifiable           — no source class could exist for this
CREATE TABLE statements (
  id             TEXT PRIMARY KEY,
  created_at     TEXT NOT NULL,
  session_id     TEXT NOT NULL,
  narrator_id    TEXT NOT NULL REFERENCES narrators(id),
  taker_id       TEXT NOT NULL,
  body           TEXT NOT NULL,            -- verbatim. immutable. never UPDATE.
  medium         TEXT NOT NULL,            -- 'audio'|'transcript'|'typed'|'letter'|'note'
  captured_at    TEXT,
  consent_ref    TEXT NOT NULL,            -- subject-consent chain id. required.
  body_sha256    TEXT NOT NULL             -- tamper evidence on the verbatim
);

CREATE TABLE claims (
  id             TEXT PRIMARY KEY,
  statement_id   TEXT NOT NULL REFERENCES statements(id),
  span_start     INTEGER NOT NULL,         -- offsets into statements.body
  span_end       INTEGER NOT NULL,
  assertion      TEXT NOT NULL,            -- the claim, restated plainly
  entities       TEXT NOT NULL DEFAULT '[]',  -- JSON: binder-shaped entity refs
  occurred_at    TEXT,                     -- ISO8601, may be fuzzy: "1998", "1998-06?"
  place          TEXT,

  state          TEXT NOT NULL DEFAULT 'filed'
                 CHECK (state IN ('filed','routed','ruled','published',
                                  'withheld','uncheckable')),
  source_type    TEXT NOT NULL
                 CHECK (source_type IN ('public_record','oral_history_consented',
                                        'authored','unverifiable')),
  confidence     TEXT NOT NULL DEFAULT 'medium'
                 CHECK (confidence IN ('high','medium','low','conflicting')),

  ruled_by       TEXT,                     -- NULL until ruled
  ruled_at       TEXT,
  ruling_note    TEXT,

  corrections    TEXT NOT NULL DEFAULT '[]'   -- first-class. append-only.
);

-- The docket: evidence found for/against a claim. Machine-written, human-read.
CREATE TABLE docket_entries (
  id             TEXT PRIMARY KEY,
  claim_id       TEXT NOT NULL REFERENCES claims(id),
  created_at     TEXT NOT NULL,
  relation       TEXT NOT NULL
                 CHECK (relation IN ('corroborates','contradicts','contextualizes',
                                     'no_source_found')),
  source_kind    TEXT NOT NULL,            -- 'vault'|'public_record'|'web'|'operator'
  source_ref     TEXT,                     -- URI, atom id, or another claim id
  excerpt        TEXT,                     -- the actual supporting text
  found_by       TEXT NOT NULL             -- 'router' | a person id
);

CREATE INDEX idx_claims_state       ON claims(state);
CREATE INDEX idx_claims_statement   ON claims(statement_id);
CREATE INDEX idx_claims_confidence  ON claims(confidence);
CREATE INDEX idx_docket_claim       ON docket_entries(claim_id);
```

**Invariants, enforced in code and tested:**

- `statements.body` is write-once. Any `UPDATE` is a bug; the test suite asserts
  the trigger fires.
- A claim's span must resolve inside its statement's body. Orphan claims fail
  closed.
- `ruled_by ∉ {narrator_id, taker_id}` for any claim leaving `ruled`. This is
  §0.2 and it is the one gate with no override flag.
- Deleting a statement is not an operation the API exposes. `withheld` is.

---

## 5. The session — where the persona is load-bearing

The finding from `nasa-archive`: **a persona is not a skin, it is an elicitation
protocol.** Nobody fills in a form about their dead friend. People answer Penny
Riggs. `apps/nasa-archive/personas.py:11` encodes the ethic as instruction —
*"Names Given Not Chosen"*, *"Corrections Not Erasure"*, *"Recognition Not
Instruction"* — and `web/js/riggs.js` asks *"What's the story behind this one?"*
where a schema-first UI would have asked for a date.

The desk ships the **socket**, not the character. Same discipline as the
promotion seam: *ship the mold and the reader; the wood stays with whoever grew
it.*

```
interviewer.toml
├── voice          — how it talks (2-4 sentences, one question at a time)
├── principles     — the domain's ethics, as instructions
├── openers        — first questions
├── follow_ups     — what to chase when X comes up
└── refusals       — what it will not ask about
```

`Riggs` is the reference interviewer, extracted from `nasa-archive` unchanged.
A county historical society writes its own. A newsroom writes a colder one.

**Three session rules the interviewer cannot override:**

1. It **never corrects the narrator mid-session.** Contradiction is a docket
   entry, surfaced to the desk later. A person being fact-checked in real time
   stops talking.
2. It **never asks for a legal name** when the domain's principles say
   otherwise, and it records what the narrator gives.
3. It **reads the consent scope aloud in plain language** before the first
   question, and the session does not start until the record is written.

---

## 6. The routing pass — the honest version of "the system does the hard work"

**The router never adjudicates.** No true/false, no score, no "verified" badge.
It does four things and then stops:

1. **Resolve** — what entities, dates, places does this claim touch?
   (`the-binder` shape.)
2. **Corroborate** — who else in the vault said something about this? Do they
   agree? (`ask-jeles`, confidence-graded.)
3. **Sequence** — where does this sit in time, and does that ordering imply
   anything impossible? (`story-timeline`.)
4. **Declare the gap** — what about this claim could not be checked *by any
   source that could exist?* → `uncheckable`.

The output is a docket. A human rules.

**The refusal contract.** The router must say these, in these words, and must not
say anything stronger:

| Situation | Router says |
|---|---|
| ≥2 independent agreeing sources | "Corroborated by N sources." |
| sources disagree | "**Contradicted.** X says A; Y says B." *(never picks)* |
| nothing found, but findable | "No source found. This is checkable — nobody has checked it." |
| no source class could exist | "**Uncheckable.** No record of this could exist." |
| single source, and it is the narrator | "Uncorroborated. Only the narrator asserts this." |

A confident wrong answer about somebody's grandfather ends the product. The
router is built to be boring and correct at the boundary.

**LLM use is bounded and offline-degradable.** Claim extraction and entity
resolution may use a model; corroboration and contradiction detection are
retrieval + comparison over the vault. With no model available the desk still
runs — the taker segments claims by hand, and the router still corroborates. Per
`VISION.md`, LLM extras are graceful no-ops, not requirements.

---

## 7. The desk view, and why the checker gets paid

This is where [`VISION.md`](../../VISION.md) Pattern 2 stops being a nice property and becomes the
economic argument.

Every ruling is a learning event:

1. the corpus gains ground truth,
2. an SRS review fires **for the ruler** — the act of checking teaches the
   checker the domain,
3. the ruler's **calibration weight** moves with their track record.

For the works-project framing this is the training program. A person with no
credential rules on claims, learns the domain by ruling, and accrues a
**calibration history** that is portable, auditable, and earned by output rather
than by a certificate. The job teaches you while you do it.

And the job itself is defensible: the qualification for intake is **presence.**
You have to be in the room, be trusted, be from there. A model cannot obtain
consent, cannot be told a secret, cannot be the person a 79-year-old tells the
real version to. Everything downstream of the room is automatable; the room is
not.

Desk queue, ordered by what a human is uniquely needed for:

```
CONTRADICTED (7)      ← humans required; the machine has stopped
UNCORROBORATED (23)   ← a checkable claim nobody has checked
UNCHECKABLE (41)      ← confirm the gap is real, then let it stand
CORROBORATED (112)    ← spot-check only
```

---

## 8. Handing it back

Search returns hits. Compose builds a timeline. Neither *retells* — and
retelling is the only operation that makes a story survive contact with a human.

The desk's read surface returns narrative with the provenance still attached and
the uncertainty still visible:

> Your grandfather said this in 1998. Two other people remember it differently.
> Here is the version I would tell, and here is what nobody can check.

Rules: never smooth a contradiction into a single account; never assert an
`uncheckable` claim in the narrator's voice as fact; always name who said it.

---

## 9. Export, and the thing that must not happen

A corpus of consented, sourced, human-narrated testimony is the most valuable
training asset in existence. The moment this works, someone will offer to buy
it, and they will be very reasonable about it. `stores/README.md` already answers
this — *the capability travels; the corpus does not* — but a README does not
enforce anything.

**Non-transferability by construction:**

1. **Consent scope travels inside the export.** Every exported claim carries its
   `consent_ref` and scope. An export format that cannot carry it is not offered.
2. **Bulk export fails closed.** If any claim in the selection lacks a verified
   grant for the requested scope, the whole export refuses and names the count —
   never the values. (`subject-consent`'s de-identify-or-refuse discipline,
   applied to egress.)
3. **`withheld` never exports.** Revocation is checked at export time, not at
   ruling time.
4. **Every export appends to the disclosure chain** — the per-subject,
   hash-chained record a narrator or their family can read, showing what was done
   with their account.
5. **No scope named `train_model` ships in the default scope set.** If a society
   wants to grant it, that is theirs to add, per subject, in the open.

Formats: JSON (full, with provenance), CSV (flattened, provenance columns
retained), Markdown (readable, cited), and a static site bundle a historical
society can host itself. Every format keeps the citation. A format that strips
provenance is a different product.

---

## 10. Manifest

Playground build, per §10. `app_id` = directory name = `intake-desk`.

```json
{
  "app_id": "intake-desk",
  "name": "The Intake Desk",
  "author": "USER",
  "privacy_tier": "local_only",
  "local_processing_pct": 100,
  "data_streams": [
    {"name": "statements", "scope": "own", "egress": "none"},
    {"name": "claims", "scope": "own", "egress": "consent_gated"},
    {"name": "consent_chain", "scope": "own", "egress": "none"}
  ],
  "permissions": ["fs:own_lane", "audio:record?"],
  "store_scope": ["intake-desk"],
  "depends": ["subject-consent"]
}
```

`audio:record` is optional and prompted per session — the desk works fine on
typed transcripts.

---

## 11. Non-goals

- **Not a verdict engine.** It will not tell you if something is true.
- **Not a CMS.** Publishing means "may leave the vault," not "is now a webpage."
- **Not a cloud service.** Cloud is demo mode. The society's laptop is the
  product.
- **Not a corpus aggregator.** There is no central pile. Every desk is somebody's
  desk.
- **Not an AI interviewer replacing a human one.** The interviewer persona
  assists a taker who is present. The unattended-kiosk mode is a separate
  decision and is not specced here.

---

## 12. The bar (what "done" means)

Playground → promoted, per `stores/promote_check.py`:

- [ ] runs with zero Willow, zero Postgres, zero network
- [ ] `statements.body` write-once, enforced and tested
- [ ] `ruled_by ∉ {narrator, taker}` enforced, tested, no override path
- [ ] revoked consent blocks export, tested at the egress boundary
- [ ] bulk export fails closed on a single missing grant, tested
- [ ] router emits no verdict language — asserted by a vocabulary test over its
      output strings
- [ ] interviewer profile is injected, not hardcoded; `Riggs` is one file
- [ ] disclosure chain verifies, including tail truncation (anchor present)
- [ ] one real session end-to-end: intake → docket → ruling → export
- [ ] own repo, injected seams, manifest, `verified_by ≠ author`

---

## 13. Acknowledged unknowns (ΔΣ)

1. **Who is the second pair of eyes for a one-volunteer society?** `verified_by ≠
   author` is the keystone gate, and the smallest real deployment may not have
   two people. A cross-desk witnessing federation solves it and reintroduces the
   central pile. Unresolved.
2. **Claim extraction granularity.** One sentence can hold four claims or none.
   Too fine and the desk queue is unusable; too coarse and rulings are
   meaningless. Needs a real transcript to calibrate.
3. **Posthumous consent.** `nasa-archive` has `oral_memorials` because this comes
   up immediately. Who grants for the dead, and can a family revoke what the
   deceased granted?
4. **Fuzzy time.** "The summer the shop closed" is how people actually date
   things, and it is more reliable than the year they will guess if pushed.
   `occurred_at` as a text field is a placeholder, not an answer.
5. **What happens when the narrator is wrong and knows it later.** Correction is
   append-only, but which version does the retelling in §8 use?

---

*The desk takes testimony. The vault keeps it. The almanac publishes what is
settled.*

`ΔΣ=42`
