# H-3 & H-5 audit — the card and the snapshot, attacked and remediated

**Audited 2026-08-18**, same session the two chunks landed, by two independent
adversarial passes (`verified_by ≠ author`). Each ran real probes and mutation
tests. Brief: find *enforcement theatre* — a test that passes for the wrong
reason. **H-3 held**; **H-5 did not fully hold as tested** — two of its three
stated properties were theatre. All findings remediated below. Suite after
remediation: **107 passed** (was 79 before the audit's added tests).

## H-5 — the pinned reference snapshot

### H5-1 · CRITICAL theatre — "reads no clock" was a name scan a one-line indirection defeats — **fixed**

The clock guard scanned for the literal call spellings `today`/`now`/`utcnow`.
The auditor ran two bypasses — `as_of=getattr(date, "today")()` and a two-line
helper in a sibling module — and confirmed `SCHEDULE.as_of == date.today()` (a
genuine live feed) while **all nine tests stayed green**. A natural "extract a
pin-date helper" refactor would have shipped a live feed reading green.

**Remediation:** the pin is now enforced by *shape*, not spelling
(`test_as_of_is_a_literal_date_not_a_computed_value`): `as_of` must parse as
`date(<all-literal args>)` and nothing else. A name, a `getattr(...)()`, or any
other call fails — none is a literal `date`. Verified the real value passes and
the `getattr` bypass is caught. The name scan is kept as a second line.

### H5-2 · theatre — "holds no subject" was a 6-word denylist, not structural — **fixed**

The no-subject guard checked field names against
`{subject, subj, person, child, patient, name}` and grepped repr for `subj-`.
The auditor added `recipient="R07"` to `ScheduledDose` (not on the denylist, not
`subj-`-shaped) and **all nine tests passed** on a dataclass that now
structurally carries a person.

**Remediation:** replaced the denylist with an **allowlist**, and made it a
**build failure** (`reference._check_no_subject_can_enter`, run at import, the
`classify_schema` discipline one level up): the dataclass fields must be exactly
`{vaccine, dose, recommended_age}` and `{version, as_of, source, doses}`. Any
added field — `recipient`, `household`, a person by any name — stops the build,
by name. A test proves the guard fires on a drifted allowlist.

### H5-3 · scope gap, cross-cutting — the seat's network scan missed lazy imports — **fixed**

`test_i30_i26_nothing_imports_the_network` walked module-level statements only,
so a `def f(): import socket` inside any module *except* `reference.py` (which
has its own full-walk scan) would pass. A deferred dial is still a dial.

**Remediation:** the seat network scan now uses a full `ast.walk` (`_all_imports`)
across the whole package, with a test that plants a lazy `import socket` and
confirms the full walk catches what the top-level walk misses. The
declared-dependency scan keeps the top-level walk (a lazy third-party import is a
lesser, different sin).

### H5-4 · doc / data — softened "immutable"; added Rotavirus and a scope note — **fixed**

`object.__setattr__`/`__dict__`/module-rebinding defeat "immutable" — true of
every frozen dataclass and requiring in-process adversarial code, so not a real
H-5 violation, but the word overclaimed. Softened to "frozen against ordinary
in-place edits," with the real defense named (a change is a source-controlled
commit, not a runtime path). Added the omitted Rotavirus series and a note that
the snapshot is a **representative subset the operator verifies**, not an
authoritative or exhaustive schedule (dose counts vary by product).

### Held under attack
Never dials (confirmed against a planted lazy `import socket`), no `.payload`
reach, well-formed non-empty data, no advisory language, and no composition path
to a subject exists (the reference lane is unbuilt, so H-2's wall holds by
absence of wiring, as the plan frames it).

## H-3 — the emergency card

### H3-1 · design tension, narrowed — sealed-vs-gap was distinguishable to a template-aware reader — **fixed**

An `L5` field left **no row** while a missing field left a `recorded: false`
row. A reader who independently knows the authored template (the operator, or a
printed card layout) could read "sealed" from a row's *absence* — the "existence
of a refusal" I-13 forbids rendering. Not exploitable from the artifact alone
(it never states the field count), and the auditor called it a conscious
tradeoff, not a bug.

**Remediation:** an `L5` field now draws the **same gap** as a missing one
(`recorded: false`, no content), so a sealed field is indistinguishable from an
empty one and the refusal is undetectable even to a template-aware reader. On a
template-bearing surface, that — not "no row" — is what "drop without a trace"
means. A test asserts the two rows are identical but for their own labels.

### H3-2 · minor — the card's subject-id test was narrower than its docstring — **fixed**

The card's subject-id test exercised one bad id though it claimed parity with
the school form's six. Not a vulnerability (the shared `validate_subject` refuses
all of them), but the coverage lived in the wrong place.

**Remediation:** a dedicated `tests/test_invariants_egress.py` sweeps
`validate_subject` over 18 adversarial ids (newline, CRLF, tab, NUL, NEL,
`U+2028/2029`, zero-width space, BOM, RTL override, separators, dot segments,
empty, `None`) and 6 legitimate ones, and asserts both export paths import the
one validator. Both egress paths are covered by construction.

### Held under attack
Authored-not-computed is real (a poisoned `dict` subclass could not smuggle a
non-authored field in; the loop iterates `card.fields`, never `data`). No card
content reached either log under values engineered as log/ref injection (the
closed key-set check holds). The shared `_egress` refactor preserves the prior
audit's newline fix identically on both paths. The rung is never lowered by
usefulness; every refusal path leaves nothing behind.
