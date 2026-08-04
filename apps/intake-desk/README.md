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

1. **`statements.body` is write-once.** "Corrections not erasure" is only true
   if the original cannot move. `desk_db.verify_bodies()` catches a body
   rewritten by something that bypassed the trigger.
2. **Nothing is deleted.** `withhold` is the operation. Revocation stops the
   export and keeps the record.
3. **A claim's span must resolve inside its statement.** A claim that cannot
   point back at the words it came from is refused by the database.
4. **`ruled_by ∉ {narrator, taker}`** — §0.2, proposing and ratifying never rest
   in the same hand. The one gate with no override flag.

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
python app.py claim --statement <id> --span 0:41 --assertion "They pushed the bike four miles."
python app.py docket --claim <id> --relation contradicts --source-kind vault --source-ref claim:other
python app.py rule --claim <id> --by wrench --confidence conflicting
python app.py queue
python app.py consent grant-publication --narrator slappy --by operator
python app.py export --format markdown --out testimony.md
```

```bash
python -m pytest tests/ -q      # 38 passed
```

## Not built yet

The router (spec §6) is not here. That is on purpose — the honest build order
is **discipline first, assistance second**. Strip the automation and what
remains is the invention; the router is most of the code and the least of the
value. A desk where a human does all the checking is still the thing.

When it lands it must **never adjudicate** — resolve, corroborate, sequence,
declare the gap, then stop — with the refusal vocabulary of §6 held by a test
over its output strings. `uncheckable` is a successful terminal state.

Also outstanding: the retelling surface (§8), and the second-eyes problem for a
one-volunteer society (§13.1), which is the keystone gate and has no answer yet
that doesn't reintroduce a central pile.

`ΔΣ=42`
