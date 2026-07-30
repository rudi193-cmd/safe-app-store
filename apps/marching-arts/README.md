# marching-arts

**Placeholder name.** The app has not been named yet; this directory is
descriptive so that renaming it costs one `git mv` and a catalog edit.

Authorization core for a marching-program platform — the thing a corps, a
drumline or a high-school band would run to hold roster, craft and schedule
information without any of it leaving the building.

This is **P1 and P2** of [`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md):
storage and the authorization resolver, then identity, roles and consent. They
ship nothing a user sees, and they are first on purpose. Everything else depends
on them — including the sync spine, which is this same component wearing a
different hat. A device receives only what its holder may see, so the filter
that decides a query is the filter that decides a sync. Build it once.

---

## The idea

> Every guarantee is a mechanism or it is a wish.

A constraint that is stated will be violated. A constraint that is structural
cannot be. So none of the promises below are enforced by discipline:

| Promise | Mechanism |
| --- | --- |
| Hidden rows never appear in a count | `COUNT(*)` runs in SQLite under the authorization predicate. A test traces the connection and fails if more than one statement reaches the table. |
| A fact always carries its source | `CHECK (length(trim(source)) > 0)` in migration 001. SQLite rejects the insert; no caller can forget. |
| Only a human seals a grant | `CHECK (state != 'sealed' OR sealed_by IS NOT NULL)`. A grant nobody signed is a grant the system invented, and the schema will not store one. |
| Refusal is invisible | A subject you may not see returns byte-identical results to a subject who does not exist. Tested as indistinguishability, not as absence. |
| Roles grant nothing on their own | Authorization comes only from a grant naming the principal individually. A director with every role sees no health band. |
| The core cannot reach the network | An AST walk over every module, plus a check that importing it pulls in no third-party package. |
| A minor does not consent for themselves | A trigger refuses any sealed grant on a minor that is not signed by a *registered* guardian. Migration 002, not a validator a caller can skip. |
| Guardian access does not outlive childhood | The resolver honours `granted_via = 'guardian'` only while a birthdate says the subject is under eighteen. Nothing is scheduled, so nothing can fail to run. |
| Consent is never obtained by whoever benefits | The beneficiary may be neither `requested_by` nor `sealed_by`. One carve-out — a registered guardian of that subject — and it expires like all the rest. |
| A deleted disclosure log cannot pass as a clean one | The chain carries a head anchor with a **count**. Truncating the tail still links perfectly and still fails verification. |
| A boundary crossing proves its scrub | `deidentify()` removes named identifiers and then *verifies* the removal, raising an error that carries neither the identifier nor the text. |

## P2 — identity, roles, consent

`libs/subject-consent` is the canonical consent primitive, and it lands here on
the connection P1 already opened. Grants, the hash-chained consent and
disclosure logs, and the roster are one SQLite file, so a corps backs up all of
them or none of them. A consent record restorable out of step with the data it
governs will eventually authorize something nobody agreed to.

```python
from marching_arts import Band, Store
from marching_arts.consent import ConsentedRoster

roster = ConsentedRoster(Store("corps.db"))
roster.register_member("tan", "2009-03-14", "2026 registration")
roster.register_guardian("guardian:tan", "tan", "child", "2026 registration")
roster.seal("tan", "delacroix", Band.CRAFT, "guardian:tan", "consent form",
            requested_by="hayes")     # not requested_by="delacroix"
```

Two consent layers, deliberately not merged, because a single "consented?"
boolean would have to answer both wrong:

* **band grants** — *who may see which row, to what band*. Per record, because
  every leader is also a member. Compiled into the one SQL predicate.
* **use-class consent** — subject-consent's `local_only`, `process_analysis`,
  `kb_promotion`, `person_inference`: *whether this subject's data may be put to
  this kind of use at all*. Hash-chained and tamper-evident. A coordinate is not
  a diagnosis, and the platform may hold the first without ever being allowed to
  derive the second.

**Silent revocation** deletes the grant rather than flagging it, so the resolver
sees no residue and a grantee cannot discover that they *used to* have access
from the shape of what they can no longer see. The disclosure chain keeps the
history, it is the subject's record and not the grantee's, and the delete and
the ledger row commit as one transaction.

**Refusal stays invisible, now including guardians.** A member whose guardian
declined, a member whose guardian revoked, and a member who turned eighteen are
each byte-identical to a member who was never enrolled — across the rows, the
count, the subject list and the disclosure log. If any one of the four differed,
declining would be the signal and every family that exercised the choice would
be marked by exercising it.

`marching_arts.consent` is the only module that imports the consent library, and
`marching_arts/__init__.py` does not import it — so the core still pulls in
nothing but the standard library.

## Authentication — who is asking, and the proof

Everything above was conditional on a claim nothing checked.
`Principal("delacroix")` was an unverified string, and a perfect predicate over an
unauthenticated principal is theatre: anything that can construct a `Principal`
can construct any `Principal`.

**The gate is at the read, not at the login.** A login function returning a plain
dataclass closes the honest-mistake case and nothing else — the next feature to
need a principal constructs one inline and it works. So a `Principal` carries a
`proof`, an HMAC over its identity, its roles and an expiry, and `predicate()`
verifies it. That is the one method every read already went through, so `count`,
`visible` and `subjects` are gated by a single line and a fourth read added later
inherits it.

```python
store.auth.enroll("delacroix", "correct horse battery staple", "roster-import")
store.count(Principal("delacroix"))          # AuthError — nobody proved this
who = store.auth.authenticate("delacroix", "correct horse battery staple")
store.count(who)                             # resolves, exactly as before
store.count(replace(who, roles=frozenset({"director"})))   # AuthError
```

Three decisions carry the weight:

- **No key at rest.** The signing key is generated per `Authenticator`, held in
  memory and gone when the process exits. A key beside the data it authenticates
  is a key an attacker with the file can use to mint any principal they like. The
  price is that tokens do not survive a restart, which is right for an app with no
  server — there is no session to resume, only a file to reopen.
- **Arming is a one-way latch.** "Require proofs if credentials exist" makes
  `DELETE FROM credentials` a privilege escalation, so arming lives in its own
  table behind a trigger refusing `1 → 0`. Delete every credential and the corps
  is locked out of their own database rather than let in. That is the correct
  direction to fail.
- **PBKDF2, not scrypt.** `hashlib.scrypt` is in the standard library and is not
  in WebCrypto, and the browser half has to agree with this one by differential.
  Portability, not taste.

**What it does not do.** It does not make the file confidential. Anyone holding it
opens it with `sqlite3` and reads every row — including L4 — with no credential
and no proof. This gates the resolver, not the file. A test asserts that, so the
limit cannot quietly stop being said; the day it fails is the day encryption at
rest arrives, and that needs a cipher this project does not have.

**And roles are still a claim.** Asked for at authenticate time, checked against
nothing, because there is no roles table. Signing them stops them being added to
an issued token; it does not make them true. Survivable only while the default
policy grants nothing on a role, which
`test_a_role_still_buys_nothing_in_the_default_policy` exists to notice.

## Corrections, and why migration 005 was wrong about them

*Corrections land beside the record, never on top of it* is one of this project's
own rules. Migration 005 shipped a table that structurally could not keep it:
`rationale.topic` is `UNIQUE` and there was no supersedes column, so a correction
could not be a second row — and amending the existing one **overwrote** the text
it replaced. A log that quietly overwrites its own mistakes can confirm the
current answer and cannot be used to check whether the reasoning was sound. 005
was built to ship reasoning and made exactly that mistake.

Migration 007 splits the two. `rationale` stays one row per topic — the *current*
guarantee, deep-linkable, existing API untouched. `rationale_correction` is the
history: append-only, many rows per topic, because a guarantee can be wrong more
than once.

**The keeping is a trigger, not a convention.** Rewriting a shipped answer records
the text being replaced in the same transaction, whether or not the writer has
heard of the rule — a convention would have been enough for a careful caller, and
a careful caller was never the problem. The row lands as `draft` carrying a stub,
because the database can see *that* the text changed and cannot know *what was
wrong*; a human fills that in and seals it.

**And the candour claim is a query.**

```python
store.corrected_topics()      # every guarantee that has ever been wrong
```

That one line is why 007 is a table and not prose in `answer`. "We disclose what
we got wrong" is a guarantee like any other, so it needs a mechanism or it is a
wish — and buried in text, a guarantee with a clean history and one that was wrong
for six months read identically.

**What ships is a discriminator, not taste.** Does the mistake change what a
reader should believe about a current guarantee? A tripwire that could not fail
means the guarantee was unprotected for its whole life — that ships. A
contaminated test baseline or a stale count in a README is a fact about how the
work is done — internal, where a maintainer finds it and a customer does not. A
**live** defect stays internal in every case, which is 005's rule unchanged.

Three refusals come from the schema: a shipped correction must name what makes the
guarantee true *now* (`"we fixed it"` is not a mechanism), must be signed, and may
not ship ahead of the guarantee it corrects — disclosing a defect in work nobody
has seen is disclosure with none of the benefit.

What the schema cannot check is whether a human classified honestly. `sealed_by`
is the whole answer to that, and no test stands in for a name.

## Bands

`L0 SELF · L1 ROSTER · L2 CRAFT · L3 ACCOMMODATION · L4 HEALTH · L5 SAFEGUARDING · L6 FAMILY`

Two of these behave differently from the rest, and both are decisions rather
than defaults:

**L3 and above: derive the instruction, do not forward the fact.** A section
leader is told *rotate this member out of the block every twenty minutes*. They
are not told why. The payload is replaced with `NULL` in the SELECT list, so the
underlying fact never leaves the database — the row is still visible and the
instruction still readable, because a leader does need to know there is an
instruction to follow.

**L5 is never served, to anyone, under any grant.** Safeguarding concerns are
routed to the people whose job it is to receive them. In every
leadership-implicating case on the public record, surfacing was external; an
intake here would digitise a broken path rather than repair it. A grant that
reaches L5 does not open it, because the deny applies to the union of the
allows.

## The precedence rule

The resolver compiles to exactly one predicate:

```
(allow₁ OR allow₂ OR …) AND NOT (deny₁ OR deny₂ OR …)
```

Denies negate the **union** of the allows. Drop the parentheses around the
joined denies and only the first term binds — the rest silently stop applying,
nothing raises, and every row they were meant to withhold becomes visible. That
is the single most likely way to rebuild the leak this app exists to prevent, so
it has its own regression test.

A principal with no allow rules gets `0`, not `1`. Fail closed.

## Layout

```
marching_arts/
  bands.py     the classification scale, and the two bands that behave differently
  rules.py     Rule, Effect, and the compiler. Knows nothing about people.
  policy.py    who may see what. The only file that decides anything.
  schema.py    001 band and source · 002 people, guardianship, the chain tables
               and the triggers · 003 the guardian rule over the chain itself ·
               004 one consent chain per subject · 005 shipped rationale ·
               006 credentials, and the arming latch · 007 corrections beside
               the record, and the trigger that keeps the superseded text
  auth.py      who is asking, and the proof. Verified inside predicate(), not at
               a front door a caller can walk past
  store.py     authorized reads. There is no second path.
  consent.py   P2's binding: libs/subject-consent on this store's connection
tests/
  test_gate.py        count · filter · sort · empty state
  test_consent.py     P2's gate: guardians · majority · silent revocation ·
                      coercion · the count anchor · de-identify-or-refuse
  test_provenance.py  the schema's own guarantees, and per-record resolution
  test_rules.py       precedence, tested directly
  test_no_egress.py   the AST walk
  test_auth.py        the proof: fabricated · borrowed · edited · expired ·
                      re-enrolled · and the latch that will not disarm
  test_corrections.py 007: the prior text survives an amendment, and "what we
                      got wrong" is a query rather than a paragraph
  test_rationale.py   005's two gates: draft never ships, shipped names a
                      mechanism
  test_migratability.py
                      what has to hold before a corps puts a season in the file:
                      forward migration on populated data · 150 members and a
                      season, plan-checked rather than timed · two processes on
                      one file · backup and restore, including the partial ones
docs/
  BUILD_PLAN.md       all five phases, each with its gate, and the refusals
tools/
  caption_dimensionality.py   reproduces the figures the plan's evidence rests on
```

The plan and the analysis behind it travel with the build on purpose. The
correlations in `docs/BUILD_PLAN.md` are the evidence for a decision the whole
design turns on — that the tool never produces a number competing with a caption
score — and a table of numbers in a markdown file is a claim. The script is the
mechanism:

```bash
python3 tools/caption_dimensionality.py path/to/dci_scores.db
```

Its docstring records why it ranks within sheet rather than residualising on the
composed total: that earlier method forces negative correlation by construction
and reported a judge-independence finding that does not exist.

## Run it

```bash
python3 -m pytest tests -q      # 221 passed
python3 app.py                  # a walkthrough on synthetic data
```

Stdlib only. Python 3.10+. No install step, no server, no ports. `consent.py`
resolves `libs/subject-consent` from the repo when it is not already installed;
migration 003 needs SQLite's JSON1, which has been on by default since 3.38 and
is present in the `sqlite-wasm` build the browser host will use.

Every guarantee above was verified by breaking it. Twenty-one mutations — drop
the expiry clause, defang each trigger, make `append_row` commit on its own,
turn the count anchor back into a plain head hash, let `disclose_text` skip the
scrub — and each one turns this suite red. Two of them turned it red for the
wrong reason and found real bugs: a `CHECK` that evaluated to NULL (and
therefore passed) on a malformed birthdate, and a backend that reported an
emptied chain as an absent one.

`test_auth.py` is held the same way, twenty-five more mutations — stop verifying
the proof, leave identity out of the signed message, parse the expiry before
checking the signature, make an expired token distinguishable from a forged one,
derive arming from the credentials table so deleting them reopens the door, write
the signing key into the file. One of them found a test that could not fail: the
tripwire meant to force a roles table compared what a decorated principal sees
against what a plain one sees, and the fixture had no row the principal could not
already see, so a blanket `admin` allow changed nothing. The fixture now carries a
row nobody can reach.

`test_migratability.py` was built the same way, sixteen more mutations, and the
run corrected two claims rather than confirming them. A rename of the consent
chain's subject hash was invisible to every assertion in the module, because the
fixture writes the chain with the function the test reads it with — so the stored
name is now pinned to a literal, the way the migration names are. And
`test_tail_truncation_is_detected_only_because_of_the_count_anchor` overstates
its own title: that scenario is caught by the anchor's *hash*: the `count` field
earns its keep against a directly edited anchor, which two other tests cover.
The correction is recorded in that test's docstring beside the claim.

## Why Python, when the plan says browser

The browser host reimplements these rules against `sqlite-wasm` on OPFS. This
core is where the rules are *decided* and where the gate tests live, and it is
dependency-light and import-pure precisely so the port is a port rather than a
rewrite of a dependency tree. The differential-testing pattern from the acoustic
kernel applies: two implementations, one reference suite.

That is also the promotion bar — injected seams, own tests green, a manifest, an
import-pure core — so this build is shaped for extraction from the day it is
written.

## Status

Playground. Contested tier, not canonical, not promoted. Scoped to its own SOIL
collection (`marching_arts_*`) with no fleet-store writes.

P2 adds three data streams the app manifest does not yet declare — `people`
(birthdates), `guardianships`, and `consent_chain` / `consent_anchor` (the
hash-chained consent and disclosure logs). A birthdate is L1 roster data and a
guardianship names a second person who is not a member at all, so both belong in
the manifest before this leaves the playground.
