# The Intake Desk

*Takes an unverified human account, keeps it whole, breaks out the claims
inside it, and refuses to publish anything on the word of the person who
filed it.*

Spec: [`docs/specs/intake_desk_spec.md`](../../docs/specs/intake_desk_spec.md).
Playground tier. Local-first SQLite — zero Willow, zero Postgres, zero network.

---

## What this is for

The store already had four organs of a memory system — `field-notes` →
`the-binder` → `ask-jeles` → `story-timeline` — and every arrow pointed *into*
the vault. Nothing took testimony from a person who is not the operator.
`nasa-archive` and `the-squirrel` each solve that for exactly one domain; this
is that capability with the domain injected.

Three audiences, one pipeline, three clocks: a historical society (decades), a
newsroom (days), a writer checking their own raw idea (whatever).

## The five nouns

- **Statement** — what a person actually said. Verbatim, whole, **write-once**.
- **Claim** — one checkable assertion, anchored to a character span *inside* a
  statement. There is no free-floating fact here.
- **Narrator** — whose account it is. Usually not the operator.
- **Taker** — who ran the session. A byline on the intake, not on the truth.
- **Docket** — evidence for and against. **Never a verdict.**

## The four invariants

They live in `schema.sql` as triggers, not only in `desk.py`, so they hold for
anything that opens the file:

1. **`statements.body` is write-once**, along with everything that decides
   whose account it is (`narrator_id`, `taker_id`, `consent_ref`, `session_id`).
   The in-row digest is a **checksum, not a witness** — body and digest sit in
   the same row, so anything that rewrites one rewrites the other.
   `file_statement` also writes the digest into the subject's hash-chained
   disclosure record and `verify_bodies(conn, store)` compares the two — but
   read that limit precisely. The chain is outside the *file*, not outside the
   *trust boundary*: one disk, one process, one set of permissions. **Two
   records agreeing proves only that one hand wrote both.** That catches a
   careless rewrite. See the anchor, below, for the careful one.
2. **Nothing is deleted.** `withhold` is the operation. Revocation stops the
   export and keeps the record.
3. **A claim's span, statement and assertion are frozen.** Refused on the way
   in *and* after — a ruled, published claim cannot be re-aimed at different
   words while keeping its witness. `quoted()` refuses rather than returning a
   silently wrong slice.
4. **`ruled_by ∉ {narrator, taker}`** — §0.2, proposing and ratifying never rest
   in the same hand. No override flag, on INSERT as well as UPDATE, compared on
   the **normalised** identity (`desk.identity`) so a capital letter is not a
   bypass.

Every gate is doubled on INSERT and UPDATE, and `connect()` sets
`PRAGMA recursive_triggers = ON` — without it `INSERT OR REPLACE` is a delete
that does not fire the delete triggers. `connect()` also refuses to open a
vault whose triggers have been removed or neutered.

## The anchor — the only thing that survives a careful rewrite

> A hash chain vouches for every line except the newest. The close is a head
> recorded somewhere the chain's writer cannot reach.
> — willow-mcp `governance_ledger` (#280)

```bash
python app.py anchor --save pinned.json     # then keep pinned.json OFF this machine
python app.py anchor --expect pinned.json   # "is this the same chain it was yesterday?"
```

Rewrite the body, its digest, and the whole consent chain consistently and
every record inside the box still agrees. The pinned head does not:

```
MOVED      slappy  anchored 8a0c6745459b4168… now bcedbdcd43dca45a…
```

`verify_chains()` reports **tampered** (broken or truncated) separately from
**moved** (verifies cleanly, is not the chain you anchored). The second is what
an edit-plus-repair looks like from outside, and it must not read as ordinary
corruption. An honest append moves the head too — which is why re-pinning is a
deliberate act, not an automatic refresh.

## Consent

Bound to [`libs/subject-consent`](../../libs/subject-consent/) — the axis built
for a subject who is *not* the operator, which is every interview. Two scopes,
and granting one never implies the other:

| Scope | Means | Required for |
|---|---|---|
| `local_only` | may be kept on this device | filing a statement |
| `testimony_publication` | may leave, **attributed** | export |

`testimony_publication` is deliberately not `kb_promotion`: that scope is
de-identified structure crossing into a shared index, and an oral-history desk
publishes the opposite — the naming *is* the record ("Names Given Not Chosen").

**Export fails closed.** One claim in the selection without a verified grant
refuses the whole export and names the count — never the values, because
naming who withheld consent is itself a disclosure. Withheld claims never
export. Every export appends to the disclosure chain a narrator or their family
can read.

## The interviewer is injected

The finding this app is built on: **a persona is not a skin, it is an
elicitation protocol.** Nobody fills in a form about their dead friend; people
answer Riggs.

`interviewers/riggs.toml` ships as the reference profile, lifted from
`nasa-archive`. A county historical society writes its own; a newsroom writes a
colder one. *Ship the mold and the reader; the wood stays with whoever grew it.*

Three session rules are enforced in `interviewer.py`, not left to the profile:
the consent scope is read aloud before the first question and the session
refuses to open without a recorded grant; the interviewer never corrects the
narrator mid-session (a person being fact-checked in real time stops talking);
contradiction is a docket entry, surfaced later.

## Running it

```bash
pip install -e ../../libs/subject-consent

python app.py consent grant-keeping --narrator slappy --by operator
python app.py file --narrator slappy --taker penny --body-file interview.txt
python app.py claim --statement <id> --span 0:41 --assertion "They pushed the bike four miles." --occurred-at 1998
python app.py route --all
python app.py docket --claim <id> --relation contradicts --source-kind vault --source-ref claim:other
python app.py rule --claim <id> --by wrench --confidence conflicting
python app.py queue
python app.py consent grant-publication --narrator slappy --by operator
python app.py export --format markdown --out testimony.md
```

```bash
python -m pytest tests/ -q      # 78 passed
```

## The router hands you candidates and stops

`router.py` does four things: **resolve** the entities a claim touches,
**retrieve** other claims about the same things, **sequence** the dated accounts,
and **declare the gap**. The output is a docket. A human rules.

**There is no sentence for agreement, and that is the most important thing
about this module.** There was one — `Corroborated by N sources.` — and an
adversarial pass measured it wrong on **89%** of the corroborations it produced
over a realistic corpus. Entity overlap is the whole relatedness test, and
entity overlap cannot see negation:

```
[the-colonel] Miller's Bar never had a back room.
[slappy]      Miller's Bar had a back room.
              -> "Corroborated by 2 sources."      # the old behaviour
              -> "Related claims found: 1. Read them."   # now
```

Retrieval can honestly say *these are about the same things*. It cannot say
*they agree*. Only a person can promote a candidate to agreement.

| Situation | It says |
|---|---|
| dated accounts cannot all be right | `Contradicted. {every account, named}.` |
| the same narrator dated it two ways | `The narrator dated this two ways: …` |
| other claims about the same things | `Related claims found: N. Read them.` |
| related, but only the same narrator | `Uncorroborated. Only the narrator asserts this.` |
| nothing related found | `No source found. This is checkable — nobody has checked it.` |
| first-person interior state | `Uncheckable. No record of this could exist.` |
| no entity could be resolved | `Nothing to look up: no entity could be resolved…` |

`Contradicted` names **every** dissenting account, not the first two — the old
truncation hid two of four and showed whichever row SQLite returned first,
which is picking. Narrator-supplied text is sanitised before it enters a
sentence, and `verdict_language()` now runs **at write time**, not only in the
test suite where it used to live.

## A model may propose. Only a person may verify

Spec §4.1. Every other rule here says what the *system* refuses; this one says
what a **model** may never do, and it is the rule the router shipped without.

> A model may propose. It may never verify, rule, seal, publish, or say that
> something is agreed.

No model-reachable path writes `ruled_by`, `ruled_at` or `confidence`, or moves
a claim to `ruled`, `published` or `uncheckable`. The refusal contract has no
sentence for agreement and `corroborated` is a forbidden word. Anything a model
produces enters at the lowest tier labelled with the standard that produced it,
never with a tier it chose for itself — Nestor's model surface (`nestor.serve`)
is documented as *structurally unable to seal*, and this is the desk's version
of that sentence.

**A machine may say what it found. Only a person may say what is so.**

Three things it cannot do, by construction:

- **It never rules.** Nothing writes `ruled_by`, `confidence`, or a terminal
  state. `uncheckable` is *proposed* and confirmed by a person.
- **It never uses a human's judgement as its own evidence.** `withheld` and
  confirmed-`uncheckable` claims are excluded from retrieval.
- **It never says anything about the vault it did not check.** A claim with no
  resolvable entity returns `unresolved`, not "no source found".

Bare years are not entities (a year related a school burning down to somebody
buying a truck). Dates resolve to **intervals**, so an honest `1998-2001` no
longer contradicts someone who said `2001`. Retrieval joins a persisted entity
index rather than re-extracting over the whole table — the old version was
quadratic and took 139 seconds for a 500-claim sweep.

## Not built yet

The retelling surface (§8) — search returns hits and compose builds a timeline,
but nothing hands the story *back*, and retelling is the only operation that
makes a story survive contact with a human.

And the second-eyes problem for a one-volunteer society (§13.1). `ruled_by ∉
{narrator, taker}` is the keystone gate, the smallest real deployment may not
have two people, and every answer so far reintroduces the central pile this
design exists to avoid.

`ΔΣ=42`
