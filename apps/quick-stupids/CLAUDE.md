# quick-stupids — operating rules for this app's own work

The playground has its own operating law. These are the maxims that
govern how a maker in this app writes code, ships a test, or files a
correction. `qstupid.py` reads the section below and files each maxim as
a jeles nugget so a claim in review can be checked against them without
scrolling.

Quick, stupid one-liners. The load-bearing ones usually are.

## Rules that DO apply here

**Every guarantee is a mechanism or it is a wish.** Say what enforces
the promise. A test in CI, a schema constraint, a monotonic counter, a
hash chain. If there's no mechanism, the promise is a wish — write it
that way.

**A gate that cannot fail is not a gate.** A required check that always
passes is decoration. Prove the gate by making the condition it guards
false and watching it turn red before you claim it protects anything.

**Coverage is a claim about the harness, not about the code.** A green
required check tells you the harness ran and returned zero. It does not
tell you the code is right. Read what the check actually asserted.

**State the aggregation whenever you quote a statistic.** "Latency
dropped 40%" is not a claim. p50 over ten runs on the staging box on a
warm cache is a claim. Bare percentages travel across meetings and
mislead everyone they meet.

**A test that does not run in CI is not a test.** A file in `tests/`
that the CI harness doesn't collect is documentation of intent, at
best. If a maker has to remember to run it, it will not run.

**Provenance is a state, not a score.** Where an input came from is
categorical (`sealed`, `draft`, `asserted`, `contested`). Reducing that
to a confidence number collapses the distinction the categories were
built to preserve.

**Absence is a recorded value, not a missing row.** A field that could
be empty must have a value that means "we asked and it was empty" and a
value that means "we never asked". A null that could mean either is a
bug waiting for someone to guess.

**Corrections land beside the record, never on top of it.** Rewriting
history discards the reason the wrong thing looked right at the time.
The corrected version and the original both stand; the audit reads them
together.

**The failure is never in the step you are watching.** The bug is one
frame up, or two systems over, or in the assumption that made the
current step look reasonable. If the step you're watching is guilty,
you'd have caught it the first time you read it.
