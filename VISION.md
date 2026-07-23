---
kind: doc
name: safe-vision
description: "A sovereign personal operating system — own your data, trust your sources — wearing the friendly face of a fictional university (ΔΣ=42)."
---
@markdownai v1.0

# SAFE — Vision

> **One sentence:** A sovereign personal operating system — own your data, trust your sources —
> wearing the friendly face of a fictional university.
>
> ΔΣ=42 · Decided 2026-06-08. See `docs/app_store_vision_and_gaps.md` for the full audit and
> the decisions that locked this in.

---

## What we're building

Three things, running together:

**1. A local-first software suite.**
Every app runs on your machine. Data lives in `~/.willow/` or a local SQLite file. Nothing phones
home. No subscriptions. No accounts. You can delete any of it and nothing breaks somewhere else.
"Local-first" isn't a feature we add — it's the starting assumption. Cloud is a demo mode, not
the product.

**2. An epistemic layer.**
A surprising number of apps are really about *knowing where knowledge came from and being honest
about what we don't know.* The recurring `ΔΣ=42` motif (42 acknowledged unknowns) is the
philosophical signature. Ask-jeles cites verified sources. Gerald witnesses overconfident claims
without explaining why. Story-timeline traces every event back to its source atom. Public-ledger
checks public claims against real budget data. The question "how do you know that?" runs through
everything.

**3. A warm surface.**
Sovereign computing is cold. The UTETY University cast — Jeles the librarian, Vishwakarma the
architect, Gerald the headless rotisserie chicken, Oakenscroll, Hanz, Copenhagen — is the UX.
They recur across apps as connective tissue. Jeles works the desk in The Binder, researches in
Story Timeline, *is* Ask Jeles. The personas aren't branding. They're the interface.

---

## Direction locked: sovereign-first

From the June 2026 audit, three directions were on the table:
- ~~A1 — UTETY universe as marketing front door → suite~~
- ~~A2 — two separate products (split the repo)~~
- **A3 — Sovereign-first, characters as skin. Chosen.**

What this means in practice:
- The **local suite is the product.** utety-chat, the Reddit bots, llmphysics are demos and a
  public-facing side channel — kept alive, not grown as the main thing.
- "Local-first / no servers" is a **hard requirement** for anything called a flagship, not an
  aspiration.
- Flagship apps must run with **zero Willow and zero Postgres** — local SQLite only, graceful
  no-ops for cloud/LLM extras.

**Flagships (signed off):** story-timeline, ask-jeles, the-binder, private-ledger.
source-trail folds into ask-jeles (provenance becomes a feature, not a standalone app).
Jane GM (game) is a parallel track — off the core data thesis but worth investing in.
dating-wellbeing is parked until a clean local-first rebuild.

---

## The three architectural patterns

These run through every app. They're not features to add — they're the substrate.

### Pattern 1 — Consent as first principle

Every app declares what it touches in `safe-app-manifest.json`: permissions, data streams,
privacy tier, local processing percentage. The store enforces this at install time. No silent
access, no surprise data flows.

The store TUI (shipped 2026-06-09) made this real for the first time. Previously the consent
model existed in manifests but was never shown to a user. Now it is: every install shows exactly
what the app is requesting before the user accepts.

The consent gate is the "Fully Explicit" half of SAFE. It's no longer aspirational.

### Pattern 2 — Verification as learning

Semantic-translator introduced a pattern that should run through every app that involves human
judgment: **every verification event is also a learning event.**

When a human decides something — approves a translation, flags a legal citation, confirms a
source attribution, rates a flashcard — that decision:
1. Improves the corpus (ground truth signal)
2. Fires an SRS review event for the verifier (the act of verifying teaches the verifier)
3. Adjusts the verifier's calibration weight (trusted reviewers carry more signal)

This is the iNaturalist model applied to knowledge work. It maps naturally onto:

| App | Verification event | What gets learned |
|-----|--------------------|-------------------|
| semantic-translator | Approve / correct / reject a translation | Translation quality; reviewer calibration |
| ask-jeles | Confirm a source attribution | Source reliability; claim confidence |
| law-gazelle | Verify a case citation | Legal accuracy; reviewer trust |
| the-binder | Confirm an entity connection | Knowledge graph edges |
| story-timeline | Validate an event source | Provenance chain |
| field-notes | Tag / classify an observation | Local taxonomy |

The verifier doesn't have to think of themselves as a learner. The SRS fires in the background.
Over time, people who do a lot of verification get very good at the thing they're verifying.

**This is the substrate that turns human attention into compound knowledge.**

### Pattern 3 — Jeles as the connective layer

Every app that stores structured knowledge feeds Jeles (semantic memory, `mem_jeles_*` tools).
Every app that needs to search or connect knowledge queries Jeles first.

The Knowledge OS pipeline flows:
```
field-notes   →   the-binder   →   ask-jeles   →   story-timeline
  (capture)       (connect)        (search)          (compose)
```

Today these are narrative connections — the arrows are intent, not data flow. Making them real
is Phase 2 work. But the architecture is clear: Jeles is the shared index. Apps don't need to
know about each other's schemas. They speak to Jeles.

---

## Current state (as of 2026-06-09)

**Shipped:**
- Store TUI (`tui.py` at repo root) — browse, install, uninstall, consent gates
- Semantic-translator — full pipeline: scrape → ingest → search → review → SRS flashcards, 3-tab TUI
- Law-gazelle — MCP server, Textual TUI, case management (manifest PII scrubbed)
- Ratatosk — sovereign Claude Code replacement, running
- UTETY chat, Reddit bots, llmphysics — live, cloud-hosted

**In progress:**
- Semantic-translator ingest: 1,298 segments from 27 Emerging Rule lessons, Jeles ingest running
- The-binder: read-only shell, needs write path and connection engine
- Ask-jeles: 75% — verification and web UI gaps

**Parked / gaps from the audit that remain open:**
- The Knowledge OS pipeline is still narrative-only (no connecting code between field-notes, the-binder, ask-jeles)
- Private ⇄ public ledger pairing not implemented
- Personas lack a shared source of truth (drift across apps)
- Game (Jane GM) crashes — 14 catalogued bugs before real GM logic can be designed

---

## The roadmap

@phase phase-0-hygiene-ready-to-start
### Phase 0 — Hygiene (ready to start)
Fix broken entry points (`game`, `public-ledger`, `nasa-archive`). Resolve `llmphysics-bot/gerald-bot`
(fill or delete). Make catalog statuses honest. Align nasa-archive manifest copy to actual content.

*Outcome: the catalog stops lying.*

@phase phase-1-standalone-flagships
### Phase 1 — Standalone flagships
Each flagship (story-timeline, ask-jeles, the-binder, private-ledger) runs with zero Willow and
zero Postgres. One-command launch. The Binder gets a write path and real connection engine — it's
the keystone and is currently a shell.

*Outcome: a non-developer can run the sovereign suite.*

@phase phase-2-connect-the-pipes
### Phase 2 — Connect the pipes
One pipeline, end to end, with consent at every hop:
`field-notes → the-binder → ask-jeles → story-timeline`.
Wire verification-as-learning into at least two more apps beyond semantic-translator.

*Outcome: the ecosystem value prop is a system, not a story.*

@phase phase-3-polish-and-personas
### Phase 3 — Polish and personas
Shared design language across the suite. Single source of truth for personas in `libs/personas/`.
Implement the private ⇄ public ledger pairing. Fold source-trail's provenance into ask-jeles.

*Outcome: one product, not N prototypes.*

### Parallel track — Jane GM
Fix the 14 crash bugs. Then design real game-master logic. Not gated by the flagship work.

---

@phase what-the-store-is
## What the store is

The store is not just a launcher. It's the **governance layer** of the SAFE ecosystem.

It's the place where:
- You see what every app touches before it touches it
- You grant and revoke consent
- You understand the privacy tier of everything running on your machine
- You install new apps and remove ones you don't want

The consent model is the reason "SAFE" isn't just a name. Every app that runs through the store
has declared its permissions. Every install is an explicit act. The store makes that visible and
enforceable.

Long-term, the store could surface consent history, flag apps that requested permissions they
don't need, and give you a clear view of what data each app has ever written. That's the
direction. The v1 TUI (shipped 2026-06-09) is the foundation.

---

@phase what-were-not-building
## What we're not building

- A cloud platform. The cloud apps are demos. The product is local.
- A replacement for general-purpose computing. SAFE apps solve specific, declared problems.
- An AI assistant. Willow/Jeles/Ratatosk are infrastructure, not the product. The product is
  the apps, and the apps should work without them in standalone mode.
- A startup. This is sovereign software. It's built to be owned, not to be sold.

---

*ΔΣ=42*
