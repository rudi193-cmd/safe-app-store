# Law Gazelle — Mission & Scope

*One-pager for partner, funder, and contributor conversations. Draft.*

## The problem

In most U.S. family courts, the majority of parties have no attorney. A
self-represented parent in an ongoing custody or co-parenting matter is managing
court orders, correspondence, evidence, and response deadlines alone — usually
out of a shoebox and an email inbox. Missing one deadline or losing one document
has consequences measured in time with their children. The tools that exist
either end when a form is filed, or demand the case be uploaded to someone
else's cloud.

## What Law Gazelle is

A **local-first case command center** for people navigating a legal matter
without a lawyer — the thing you use *between* filings:

- **An urgent queue** driven by real deadlines: what needs a response, what's
  overdue, what's next.
- **Evidence-linked facts**: every claim ties back to a source document, with
  explicit `[VERIFY]` / `[FACT NEEDED]` flags. The tool never authors facts.
- **Drafting context, not drafted conclusions**: it assembles the user's own
  facts, citations, and chronology so a person (or a supervised AI) can write —
  and flags every gap.
- **A gated agent surface**: AI assistance runs through
  [WillowGate](https://github.com/rudi193-cmd/willow-gate) — every tool call is
  authorized against a trust ceiling, exports are gated, and everything is
  ledgered to a key only the user holds.

The user's case data lives on the user's machine, in files the user owns.
There is no server. There is no account.

## Who it serves

**Wedge:** self-represented parents in ongoing co-parenting and custody
matters, one jurisdiction at a time. **Channel:** legal aid organizations,
court self-help centers, and law school clinics — advocate-assisted first,
direct-to-litigant as the tooling matures.

## Principles

1. **Local-first, user-owned.** Case data never leaves the user's device by
   default. The canonical record is the user's, in open formats (SQLite, JSON,
   Markdown).
2. **Information, not advice.** Law Gazelle organizes the user's own matter.
   It does not apply law to facts, recommend strategy, or predict outcomes.
3. **Verify everything.** Computed dates and extracted facts are always
   presented for human confirmation against source documents — permanently,
   not just in v1. A missed deadline here is not a bug ticket; it is harm.
4. **Agents are guests, not owners.** AI access is opt-in, least-privilege,
   and fully audited. A denied call never runs.
5. **Open source, nonprofit posture.** MIT-licensed, built in public with
   synthetic data only, aligned with the access-to-justice community
   (docassemble / Suffolk LIT Lab ecosystem) rather than competing with it.

## What it will never do

- Give legal advice or predict case outcomes.
- Author, infer, or silently modify case facts.
- Treat a computed deadline as authoritative.
- Send case data off-device by default, or monetize it ever.

## Where this goes

1. **Demo** anyone can run in five minutes on synthetic data: `make demo`
   (done — see below).
2. **Pilot partner**: one legal aid org or self-help center, one jurisdiction;
   user #2 comes from them.
3. **Intake**: guided-interview front end (docassemble integration) that turns
   a shoebox of documents into a structured, human-confirmed case file — the
   biggest build, and the most defensible.
4. **Fiscal sponsorship and grants** (state bar foundations,
   access-to-justice commissions, LSC TIG via partner orgs) once a pilot
   exists.

## Status

Working today: Textual TUI, MCP tool surface for supervised AI sessions,
WillowGate enforcement, deadline/urgent-queue engine, sidecar state — running
on real (private, off-repo) case data for user #1. Public repo contains code,
tests, and synthetic examples only.

**Try it:** `make demo` from the repo root — zero configuration, synthetic
case data, nothing touches your real files.

*License: MIT · Contact: via GitHub issues*
