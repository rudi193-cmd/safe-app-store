# terpsi-chat — design record

The chat portion of the terpsi-music org app. Written from a design
conversation, before the implementation that already exists had been read.
Every statement below about integration is a proposal, not a description.

> **Landing note — the assumption above has since been checked, and much of it
> lost.** `rudi193-cmd/terpsi-music`'s records core was read after this was
> written. Its W-1/W-3 lane model, crossing envelope and bitemporal edges solve
> most of what follows, more strictly. **[`../README.md`](../README.md) carries
> the per-mechanism table of what survived**, and it governs: where that table
> and this document disagree, the table is right and this is the historical
> record of how the reasoning got there.
>
> The short version. Live: the witness constraint making a private adult–minor
> channel unrepresentable, filed natively as terpsi-music issue #20. Defective
> and not to be ported: `guardian_links`, which conflates standing with
> reachability. Everything else is superseded, redundant with an existing
> refusal, or — in the case of concentrating enforcement on the write path —
> the wrong emphasis, since §7.2 gates the export rather than the glance.
>
> This document is deliberately **not** rewritten to match. A design record
> edited to look like it was right all along cannot be used to check whether
> the reasoning was sound.

---

## Architecture this assumes

Stated in conversation, not verified against the existing implementation:

- LAN-served, everyone in the org on the local network.
- One outbound connection to home base.
- Guardians receive an SMS saying something is waiting for them in the portal.
- Two separate identity spaces, adults and minors.

The org context is doing enormous work here and it is worth being explicit
about why. A consumer messenger for minors has to solve age assurance and
guardian verification itself, and there is no good mechanism for either. An org
app inherits both from an enrolment record established offline by a process
with a name on it. That is the single largest advantage this design has and it
is architectural, not clever.

## The three channel classes

The core structural decision. Adults and minors being separate tables means a
channel table's foreign keys decide who can appear in it, so the classes differ
in kind rather than by a flag.

| Class | Privacy | Retention | Why |
| --- | --- | --- | --- |
| `peer_channels` — minor↔minor | E2EE, device-local, family key custody | **Not retained by the org** | The org should not be custodian of children's private chat. |
| `staff_channels` — adult→minor | Not private. Witnessed, retained, readable by a named safeguarding lead | **Retained, deliberately long** | Organisational record, not correspondence. |
| `adult_channels` — adult↔adult | Ordinary org comms | Ordinary | No special handling. |

**Do not let staff retention generalise to peer channels.** Someone will argue
for consistency. The justification for retaining adult→minor is the power
asymmetry and the safeguarding duty, and two fifteen-year-olds do not have it
between them.

## Decisions taken

**Safety lives in the contact graph, not in content inspection.** Constrain who
can open a channel and you eliminate a large risk surface without reading a
message. Once you can read messages to moderate them, you can read them.

**No private adult-minor channel exists in the schema.** `witness_adult_id` is
`NOT NULL` and must differ from the sender, so a two-party adult-minor channel
has no representable form. This is two-deep leadership, which the org already
practises offline. It is the one constraint I would refuse to ship without.

**Retention on the staff class is preventive before it is evidentiary.** Both
parties know the channel is recorded at the time they write. Grooming requires
privacy; a visibly and permanently recorded channel is not usable for it. The
evidence is the fallback for when prevention failed.

**Data minimisation is actively wrong for the staff class.** Disclosure of
abuse routinely happens years to decades later, so a tidy expiry is in practice
a mechanism that destroys the relevant records on schedule. Disposal is
therefore not blocked but made loud — an authorised `retention_disposals` row
must exist first, and it survives the deletion.

**Guardian sees structure, never content, with no exception.** A guardian and a
court are different actors. One content-unlock mechanism serving both becomes
the guardian's ordinary path within a year, because "required by law" is a claim
anyone can make about their own situation. Legal process runs against the
family's own device-local store, not against the org.

**Symmetry is what separates safety from surveillance.** Whatever the guardian
sees, the young person sees — including that the guardian looked, and when.
Age band is then a default on *scope*, so the junior→senior transition is a
value change rather than a migration.

**A decision records what the decider was looking at, or it is not a record.**
`guardian_approved_at` was a bare timestamp: it said an approval happened and
nothing about what the guardian was shown. Approval is now the evidence row
itself — counterparty as displayed, their roster provenance and band at that
instant, how well the org knew the guardian binding, and the `min()` of those
stored rather than derived. A guardian who approved on an `assumed` roster
entry that later turned out wrong made a reasonable decision on thin evidence;
without the snapshot that becomes indistinguishable from negligence, or from
foresight, depending on which way the correction went. Both tables are
append-only, so a correction lands beside the record rather than on top of it.

Taken from the ad-breaks paper, which is now landed beside `playgate` in
`safe-app-store` — this is that argument applied to a different decision.

**Guardian is a named person, never a role.** Role-shaped guardianship is how a
new partner or a controlling relative inherits visibility nobody consciously
granted. Same for the safeguarding lead reading the staff archive.

**Recovery splits into two keys.** Identity key (guardian-recoverable, in the
family vault) restores the account. Content keys (device-held, not in the
vault) are not recoverable — lose the device without a healthy backup and you
lose history. A messaging app for minors having permanently recoverable history
is itself a hazard. This is what stops a guardian-administered vault from
silently becoming a content-access path.

**SMS is a pointer, never a payload.** Unencrypted, carrier-visible,
lock-screen-visible, and visible to whoever holds the phone — including in the
household the design cannot see into.

## Mechanisms and their gates

Every row is enforced by the schema and checked by `test_gates.py`, and every
gate is checked by `test_mutation.py`, which removes the mechanism and asserts
the gate goes red.

| Claim | Mechanism | Gate |
| --- | --- | --- |
| No message outside an accepted relationship | FK `peer_messages.channel_id → peer_channels` | `test_message_into_nonexistent_channel_is_refused` |
| A channel requires the full approval set | `BEFORE INSERT` trigger over `peer_channel_requests` | `test_peer_channel_needs_a_completed_request` |
| Junior band additionally requires guardian approval | Band clause in the same trigger | `test_junior_band_additionally_requires_guardian_approval` |
| No private adult-minor channel | `witness_adult_id NOT NULL` + `CHECK (witness <> adult)` | `test_witness_is_mandatory`, `test_adult_cannot_witness_themselves` |
| Peer content is never stored in plaintext | No plaintext column exists in `peer_messages` | `test_no_plaintext_column_outside_the_allowlist`, `test_schema_surface_is_unchanged` |
| Guardian surface is structure only | `guardian_visible_structure` view | `test_guardian_view_exposes_structure_only` |
| Staff records are not silently disposed of | `BEFORE DELETE` trigger requiring an authorised disposal | `test_silent_disposal_is_refused` |
| Identity migration cannot strand peer edges | FKs into `minors` | `test_minor_with_live_peer_edges_cannot_be_removed` |
| Absence ≠ no capability | `observation_capability` with a `CHECK`ed enum | `test_an_unsupported_capability_value_is_refused` |
| Approval cannot exist without evidence | No `guardian_approved_at`; the trigger consults `guardian_approval_evidence` | `test_approval_cannot_be_recorded_without_evidence` |
| The snapshot is frozen, not a join | Values stored at decision time; append-only triggers block resync | `test_evidence_is_frozen_not_a_join` |
| Evidence and reads cannot be rewritten | `BEFORE UPDATE`/`BEFORE DELETE` triggers | `test_evidence_cannot_be_edited_or_withdrawn`, `test_a_read_record_cannot_be_edited_or_withdrawn` |
| An archive read states what it saw | Three `NOT NULL` snapshot columns | `test_an_archive_read_must_say_what_was_in_front_of_it` |
| "I could not tell" stays sayable | `archive_state` admits `unknown` | `test_unknown_completeness_stays_sayable` |
| SMS cannot carry content | `render_notice` takes only a template key | `test_render_notice_has_nowhere_to_put_content` |

Two findings from building the harness, kept because they are the point of
having one:

- `test_self_edge_and_duplicate_pair_are_unrepresentable` (as originally
  written) survived deletion of the ordering `CHECK`. It was passing because
  the approval trigger rejected the insert first — it looked like a gate on the
  `CHECK` and was a gate on something else. Split into three tests, one of
  which (`test_reversed_pair_cannot_duplicate_a_relationship`) is attributable
  to the `CHECK` alone. Without it, one relationship can hold two channel rows,
  and blocking — a `DELETE` from that table — would remove only one.
- `peer_channel_requests` also references `minors`, so a *pending request* is an
  unresolved edge during identity migration. A migration routine sweeping only
  `peer_channels` would be refused by the database. Not something the design
  had accounted for; the constraint caught it rather than the author.
- The archive-read gate first omitted all three snapshot columns in one insert
  and passed while only one of them was still mandatory — it would have gone
  green with two of the three made optional, because the surviving `NOT NULL`
  was doing all the work. Now checked per column. Third time this exact shape
  has appeared in this file: a gate that looks like it covers a mechanism and
  is actually being satisfied by a neighbouring one. It is worth assuming it is
  present anywhere a test asserts one failure that several constraints could
  produce.

## Provenance: what is NOT sourced

**Read this before quoting anything from the conversation this came out of.**

Two research agents were dispatched for the empirical and legal base. Both
found outbound egress blocked at CONNECT (`403 host not permitted`) — the
container reaches package registries and GitHub only. Neither retrieved a
single document, and both correctly declined to substitute recalled figures.

So every empirical claim underpinning this design is currently **`assumed`**:

- That harm to minors is predominantly by known/trusted persons rather than
  strangers — the premise for "the closed graph is strong against the wrong
  threat". Asserted in conversation, **unsourced**.
- That intrafamilial harm is a meaningful share — the premise for excluding
  guardians from content. **Unsourced.**
- That disclosure latency is years to decades — the premise for the retention
  stance, which is the claim most likely to be challenged on minimisation
  grounds. **Unsourced.**
- Peer-to-peer prevalence, monitoring-software efficacy, age-assurance bypass
  rates. **Unsourced**, and on the last two there was no sign of a top-tier
  primary collector in the search index at all beyond one Australian trial —
  which may be a genuine evidence gap rather than a retrieval failure. Cannot
  be distinguished from inside a blocked container.

When egress returns: BJS/NIBRS is law-enforcement administrative data with a
reported-to-police universe; the Crimes against Children Research Center
material is general-population youth self-report. They will disagree by
construction and must never be pooled. State the aggregation with any figure
that comes out of this.

The legal question to answer first, because it is narrow and load-bearing:
**does any retention duty fall on the operator rather than permitting
device-local retention by the family, and how does a deliberately long staff
retention sit against minimisation duties?**

## Open decisions

- **Whether the count of shielded edges is visible to the guardian.** The view
  currently excludes shielded rows entirely; exposing the count is a signal,
  and so is a gap where a count should be. No good answer, needs picking.
- **What happens to `guardian_links`, `guardian_observations` and
  `observation_capability` on identity migration.** The FKs force a decision;
  the decision has not been made.
- **Whether the young person holds a real share of any archive threshold, or a
  nominal one.** If a guardian can compel a child to produce their share, the
  threshold is not a threshold and the delay plus notification are doing all
  the work. Worth knowing which you are relying on.
- **Where the "route, never receive" report actually goes.** Org staff are
  plausibly mandated reporters, which makes the destination real and
  accountable in a way a consumer app cannot match — but the route has not been
  specified and a route to nowhere is worse than no button.

## Gaps with no mechanism

Named because they have none, not because they are unimportant.

- **Peer-to-peer harm is invisible to everything here.** Bullying, coercion,
  sextortion between minors — all inside accepted edges, all in content nobody
  can read. Volume and timing show; valence does not. The only routes are
  recipient-initiated: good blocking, easy exit from group threads, a
  "this is happening to me" action that routes outward.
- **Metadata is not innocuous.** The existence of an edge is itself a
  disclosure — a new contact can out a young person. `shielded_by_minor` is a
  partial mitigation and a compromise, not a solve.
- **Screenshots and the receiving end.** E2EE protects transit and storage and
  does nothing about the person on the other side.
- **The org is now the operator.** Home base holds nothing, which is good; the
  LAN box holds everything and is administered by volunteers with physical
  access, no offboarding process, and no key rotation. Whoever set it up still
  has access three years later. This is the normal end state, not a
  hypothetical.
- **Every mechanism here is dual-use.** Blocking is also the primitive for
  isolating a child from anyone who might help them. Mandatory notification of
  archive access protects against covert reads and, in a violent household,
  triggers retaliation. These cannot be designed out — only chosen between,
  and the choice must not be silent.
- **The roster's errors are inherited.** Guardian binding is `measured` exactly
  as well as the enrolment record is. If that is a spreadsheet a booster parent
  maintains, custody arrangements and protective orders are the entries most
  likely to be stale and most consequential when they are.

## What this suite structurally cannot see

- **Everything device-side.** Content, key custody, the vault backend ladder,
  the sealed archive. The gates cover the server schema, which is the easy
  half. Anything device-side that cannot run in CI has, in practice, never
  executed.
- **Whether the FK pragma is set in production.** SQLite enforces foreign keys
  only when `PRAGMA foreign_keys = ON`, per connection, off by default. Several
  guarantees above are foreign keys. `test_fk_pragma_is_the_whole_ballgame`
  demonstrates the unenforced case accepting an orphan row. The suite cannot
  tell you what the running app does — that requires a single connection
  factory and a check that nothing else opens a connection.
- **Whether the application uses the schema as designed.** Nothing stops
  service code from reading `peer_messages.ciphertext` and shipping it
  somewhere. The FK binds writes into this database; the first background job,
  analytics sink, or search index that gets its own copy of message data is
  where the guarantee quietly stops being one.
- **Any empirical or legal claim.** See provenance above.
