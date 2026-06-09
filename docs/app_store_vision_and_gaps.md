# SAFE App Store — Vision & Gap Analysis

> **Status:** Working draft. Sections marked **🤝** were proposals; the ones we've agreed
> are now recorded under **Decisions locked** below.
> **Date:** 2026-06-08 · **Author:** Vishwakarma (with a full code survey of all 21 apps)
> ΔΣ=42

### Decisions locked (2026-06-08)
1. **Thesis confirmed** (§2): *a sovereign personal OS — own your data, trust your sources — wearing the friendly face of a fictional university.*
2. **Direction: Sovereign-first (A3)** (§4). The **sovereign suite is the product**; the personas are its UI; the cloud "UTETY universe" apps are **demos / a side channel, not the destination**.
3. **Willow: invest in true standalone** (§7). Flagship apps must run with **no Willow and no Postgres** — local SQLite only. Bundling Willow is explicitly *not* the path.
4. **Still open:** which apps are flagships vs. parked/archived (§6 proposes a cut — needs your sign-off).

This document does three things:
1. **Inventory** — what's actually in the store today (grounded in the code, not the README pitch).
2. **Intent** — what I believe we're really building, and how the pieces fit.
3. **Gaps + path** — what's missing across functionality, usability, and UI, and a phased way to close it.

---

## 1. The inventory — what's actually here

21 catalog entries. The honest maturity picture (from reading the code, not the manifests):

**Legend:** 🟢 works & polished · 🟡 runs but partial/rough · 🔴 stub / broken / scaffold · ⚫ archived

| App | Cluster | Catalog status | Real maturity | Runs standalone? | Surface |
|-----|---------|----------------|---------------|------------------|---------|
| **utety-chat** | UTETY universe | stable | 🟢 ~90% — **live** | Yes (cloud-hosted) | Web (Cloudflare Pages + Workers) |
| **llmphysics** (judge) | UTETY universe | coming_soon | 🟢 ~90% — **live** | Yes | Static HTML, client-side |
| **UTETY-Reddit-Bots** | UTETY universe | coming_soon | 🟢 Gerald **live**; Hanz/Oak ready | Yes | Reddit (Devvit) |
| **llmphysics-bot** | UTETY universe | coming_soon | 🟢 devvit ready; gerald-bot 🔴 scaffold | Yes | Reddit (Devvit/PRAW) |
| **story-timeline** | Knowledge OS | beta | 🟢 ~85% | Yes (SQLite) | Textual TUI + web graph |
| **law-gazelle** | Personal command center | coming_soon | 🟢 ~85% | Yes (SQLite + MCP) | Textual TUI + MCP server |
| **the-squirrel** | Knowledge OS | coming_soon | 🟢 ~80% | Needs Postgres | HTTP server (:8425) |
| **ask-jeles** | Knowledge OS | coming_soon | 🟡 ~75% | Yes (demo mode) | Textual TUI (+ FastAPI stub) |
| **vision-board** | Life utilities | stable | 🟡 ~75% | Yes (IndexedDB) | React + FastAPI |
| **private-ledger** | Money & civics | beta | 🟡 ~70% | Yes (SQLite) | Textual TUI |
| **ratatosk** | Sovereign infra | beta | 🟡 solid core | Yes (needs API key) | CLI agent |
| **public-ledger** | Money & civics | coming_soon | 🟡 ~60% | API only; **broken entry point** | FastAPI (:8422), no UI |
| **bt-controller** | Life utilities | coming_soon | 🟡 ~50% | CLI only; Win/WSL only | Daemon + (missing) web UI |
| **source-trail** | Trust & provenance | coming_soon | 🔴 ~50% | **No** — Postgres-only | Textual TUI (non-functional offline) |
| **field-notes** | Knowledge OS | beta | 🟡 ~45% | Yes (SQLite) | Textual TUI |
| **nasa-archive** | Life utilities | stable | 🔴 ~40% | Partial; **broken entry point** | Static site + cloud chat |
| **game** (Jane GM) | Life utilities | coming_soon | 🔴 ~30% — **crashes** | No (14 known bugs) | Streamlit |
| **dating-wellbeing** | Life utilities | coming_soon | 🔴 ~30% | **No** — Postgres-only, UI missing | Streamlit (broken entry point) |
| **the-binder** | Knowledge OS | beta | 🔴 ~25% — **keystone, but a shell** | Read-only | Textual TUI |
| **grove** | Sovereign infra | beta | external repo | n/a | p2p (separate repo) |
| **genealogy** | Knowledge OS | archived | ⚫ merged into the-squirrel | — | — |

**Plus the base Store app itself** (`/`, agent "Vishwakarma"): a `catalog.json` + a Willow-backed
store DB + a `make run app=<x>` launcher. It is a *catalog and dev harness*, **not yet a
consumer "app store"** (no browse/install/launch UI).

---

## 2. The real intent — what we're building 🤝

Strip away the jargon and the cast of characters, and three through-lines run through every app:

### Through-line 1 — **Sovereignty**
> *"No ports. No servers. No subscriptions. Yours to keep, yours to delete."*

Local-first by default. Your data lives in `~/.willow/`, on your machine. **SAFE** = *Session-Authorized,
Fully Explicit*: apps declare their permissions up front, nothing phones home silently, and you can
delete any of it. This is the spine.

### Through-line 2 — **Provenance & epistemic honesty**
A surprising number of apps are really about *knowing where knowledge came from and being honest
about uncertainty*:
- **ask-jeles** cites verified sources; **source-trail** logs and verifies claims.
- **Gerald** (the Reddit bot) silently "witnesses" overconfident, unfalsifiable claims — and never explains.
- **Oakenscroll** tracks *acknowledged unknowns* toward `ΔΣ=42`.
- **story-timeline** carries provenance atoms linking every timeline entry to its source.
- **public-ledger** audits public claims against real budget/IRS data.

The recurring `ΔΣ=42` motif ("42 acknowledged unknowns") is the philosophical signature: *honest
about what we don't know.*

### Through-line 3 — **Warmth through characters**
A sovereign-computing platform is cold. The **UTETY University** fiction — a faculty of personas
(Jeles the librarian, Gerald the headless rotisserie chicken, Oakenscroll, Hanz, Copenhagen,
Vishwakarma the architect) — is the **UX**. The personas *are* the interface, and they recur across
apps as connective tissue (Jeles works the desk in the-squirrel, researches in story-timeline, *is*
ask-jeles).

### The one-sentence thesis ✅ *(agreed)*
> **A sovereign personal operating system — own your data, trust your sources — wearing the friendly
> face of a fictional university.**

Every gap below sorts into "serves the thesis" or "doesn't." Because we've chosen **sovereign-first**,
the tie-breaker is sharper still: *does it help a person own and trust their own data on their own
machine?* If not, it's a demo at best.

---

## 3. How the apps fit together — the map

Six clusters, each with an intended internal flow:

```
                         ┌──────────────────────────────────────────┐
                         │  SOVEREIGN INFRASTRUCTURE                 │
                         │  Store (Vishwakarma) · Ratatosk · Grove   │
                         │  Willow substrate: store, KB, messaging   │
                         └──────────────────────────────────────────┘
                                          │ everything sits on this
   ┌───────────────────────┬─────────────┼─────────────┬───────────────────────┐
   ▼                       ▼             ▼             ▼                       ▼
┌─────────────┐   ┌────────────────┐  ┌──────────┐  ┌──────────────┐   ┌──────────────────┐
│ KNOWLEDGE   │   │ MONEY & CIVICS │  │ TRUST &  │  │ UTETY        │   │ LIFE UTILITIES   │
│ OS          │   │                │  │ PROVENANCE│ │ UNIVERSE     │   │                  │
│             │   │ private-ledger │  │          │  │ (public face)│   │ vision-board     │
│ field-notes │   │     ⇅ (paired) │  │ source-  │  │ utety-chat   │   │ game (Jane GM)   │
│   ↓ capture │   │ public-ledger  │  │  trail   │  │ reddit-bots  │   │ dating-wellbeing │
│ the-binder  │   │                │  │   ⇅      │  │ llmphysics   │   │ bt-controller    │
│   ↓ index   │   └────────────────┘  │ ask-jeles│  │ + judge      │   │ nasa-archive     │
│ ask-jeles   │                       └──────────┘  └──────────────┘   │ law-gazelle      │
│   ↓ search  │                                                        └──────────────────┘
│ story-      │     Recurring cast = the connective tissue:
│  timeline   │     Jeles (librarian) · Vishwakarma (architect) · Gerald (witness) · …
│ the-squirrel│
│  (compose)  │
└─────────────┘
```

**The intended pipelines:**
- **Knowledge OS:** *capture* (field-notes) → *index/connect* (the-binder) → *search* (ask-jeles) →
  *compose* (story-timeline); the-squirrel is the same pattern specialized for genealogy.
- **Money & civics:** *your private books* (private-ledger) ⇄ *public-records audit* (public-ledger).
- **Trust:** source-trail verifies claims by leaning on ask-jeles / Jeles's verified sources.
- **UTETY universe:** the public-facing content + community engine — the front door and the brand.
- **Infrastructure:** the Store catalogs everything; Ratatosk is *your own* agent runtime; Grove is
  *your own* messaging.

**The crucial finding (see §5):** these pipelines are **designed but not yet connected**. The arrows
above are intent, not implemented data flow.

---

## 4. The central tension we should name 🤝

There are **two products living in one repo**, and they pull in opposite directions:

| | **A — UTETY Universe** | **B — Sovereign Personal Suite** |
|---|---|---|
| What | utety-chat, Reddit bots, llmphysics | knowledge OS, ledgers, law-gazelle, etc. |
| State | **shipped, live, has an audience** | mostly local TUIs, uneven maturity |
| Deploy | **cloud** (Cloudflare, Reddit, Supabase) | **local-first** (`~/.willow`, no servers) |
| Ethos | public, playful, outward | private, sovereign, inward |
| Tension | *uses the cloud the suite says it rejects* | *no install story; dev-only* |

This isn't a problem to "fix" — it was a **strategic choice**, and we've made it.

- ~~A1 — one funnel (universe as marketing front door → suite).~~
- ~~A2 — two products (split the repo).~~
- **A3 — Sovereign-first, characters as skin. ✅ *Chosen.*** The local suite is *the product*; the
  personas are its delightful UI; the cloud apps (utety-chat, the Reddit bots, llmphysics) are
  **demos and a side channel, not the destination.**

**What A3 implies, concretely:**
- Effort goes to the **local-first suite**, not the cloud surfaces. The universe is kept alive but
  not grown as the main thing.
- "Local-first / no servers" stops being aspirational and becomes a **hard requirement** for anything
  we call a flagship — which is exactly why we also chose **true standalone** (no Willow, no Postgres)
  for those apps.
- The cloud apps' contradiction with the ethos is now resolved by *demotion*: they're allowed to be
  cloud because they're explicitly demos, not the product.

---

## 5. The gaps

### 5.1 Ecosystem-level gaps (these matter most)

| # | Gap | Why it matters | Severity |
|---|-----|----------------|----------|
| E1 | **No install / distribution story.** Every suite app assumes a developer + a Willow checkout + (often) Postgres. | This is *the* barrier. Today only a developer can run the sovereign half. | 🔴 Critical |
| E2 | **No store UX.** Discovery is reading `catalog.json`; launch is `make run app=x`. | It's called an "App Store" but a human can't browse, install, or launch anything. | 🔴 Critical |
| E3 | **Integrations are narrative-only.** The pipelines in §3 (field-notes→binder, private⇄public ledger, source-trail↔ask-jeles) have **zero connecting code.** | The whole "ecosystem" value prop is currently a story, not a system. | 🔴 Critical |
| E4 | **The Binder is a shell.** It's the keystone of the Knowledge OS (the "index/connect" step) but is a read-only wrapper with no storage, no entity graph, no add/edit. | The capture→compose pipeline has a hole in the middle. | 🔴 Critical |
| E5 | **Permission/consent model designed but unenforced.** SAFE's "explicit permissions" is the brand promise; only story-timeline registers, and no app shows a consent prompt. | The core differentiator ("Fully Explicit") isn't actually wired. | 🟡 High |
| E6 | **Persona drift.** Gerald exists in 3 separate definitions with no shared source of truth; many personas are copy-pasted across apps. | The characters *are* the brand; drift erodes it and makes updates brittle. | 🟡 High |
| E7 | **Willow dependency is implicit and fragile.** Apps hard-assume `~/github/willow-*`; if Postgres is down, things degrade or crash. (#16 helped the lattice apps; the pattern isn't universal.) | Couples "your sovereign apps" to a heavyweight, unbundled backend. | 🟡 High |
| E8 | **UI fragmentation.** Textual TUI / Streamlit / FastAPI / static HTML / React / HTTP server / Devvit — no shared shell, design language, or navigation. | Feels like 21 prototypes, not one store. | 🟡 High |
| E9 | **Manifest inconsistency & broken entry points.** `game`, `public-ledger`, `nasa-archive`, `dating-wellbeing` declare entry points that don't exist or are wrong. | Apps can't be launched by any uniform runtime. | 🟡 High |
| E10 | **"Local-first" claims that aren't true.** source-trail and dating-wellbeing are Postgres-only and crash standalone; nasa-archive/vision-board/utety-chat lean on the cloud. | Undercuts the sovereignty promise and confuses users. | 🟡 High |

### 5.2 Functionality gaps (by cluster)

- **Knowledge OS:** the-binder has no write path or connection engine; field-notes "feeds the Binder"
  but nothing ingests it; ask-jeles's verification (`prism`) and learning-event ingestion are partial;
  cross-app atom discovery isn't wired.
- **Money & civics:** the private⇄public "pairing" is entirely unimplemented; public-ledger has no
  persistence (can't save an audit).
- **Trust:** source-trail has UI wireframes but the claim-verification logic and the ask-jeles handoff
  are missing.
- **UTETY:** Hanz & Oakenscroll bots are built but undeployed; `llmphysics-bot/gerald-bot` is an empty
  scaffold (decide: fill or delete); cross-bot awareness and the Pigeon bus are stubbed.
- **Life utilities:** game crashes (14 catalogued bugs); dating-wellbeing has no working UI and no
  detection logic; vision-board's photo-library integration is unbuilt; bt-controller has no web UI.

### 5.3 Usability gaps
- **No "it just works" path** for a non-developer in the sovereign half (setup = clone + Postgres +
  Willow + Ollama + venv).
- **No consent surfacing** — the privacy model is invisible to the user.
- **No cross-app navigation** — apps don't know about each other; nothing ties a session together.
- **Inconsistent launch** — some are `make run`, some `npm run upload`, some `streamlit run`, some a
  daemon.

### 5.4 UI gaps
- **No shared design system** — typography, color, keybindings, layout differ per app.
- **Web surfaces are stubs** — ask-jeles's web mode, story-timeline's web graph (view-only),
  bt-controller's web UI (missing), public-ledger (API only).
- **TUI-only** for most of the suite — no mobile/browser path for non-terminal users.

### 5.5 Honesty / public-repo risks (ties to the earlier public-facing audit)
- **law-gazelle** embeds **real legal case numbers** and "USER's active legal matters" in its manifest
  description, in a **public** repo. Recommend genericizing the manifest (data already lives outside git).
- **nasa-archive** is named/described as a "NASA open-datasets explorer" but is a **scooter-rally
  archive**. Misleading for a public catalog — rename or re-describe.

---

## 6. Per-app scorecard & recommendation 🤝

| App | Real maturity | Biggest gap | Proposed move |
|-----|---------------|-------------|---------------|
| utety-chat | 🟢 ~90% | persona source-of-truth | **Keep / flagship** (front door) |
| llmphysics judge | 🟢 ~90% | score persistence | **Keep** (low-touch) |
| UTETY-Reddit-Bots | 🟢 live + ready | deploy Hanz/Oak; shared personas | **Keep / deploy** |
| llmphysics-bot | 🟢 ready | gerald-bot scaffold | **Ship devvit; fill-or-delete gerald-bot** |
| story-timeline | 🟢 ~85% | web UI; SLM suggestions | **Keep / flagship** (suite anchor) |
| law-gazelle | 🟢 ~85% | **PII in public manifest** | **Keep; scrub manifest** |
| the-squirrel | 🟢 ~80% | Willow KB wiring; SQLite option | **Keep** |
| ask-jeles | 🟡 ~75% | verification; web UI | **Invest** (it's the "search" keystone) |
| vision-board | 🟡 ~75% | photo-library integration | **Keep / finish** |
| private-ledger | 🟡 ~70% | the pairing; no export | **Keep / finish** |
| ratatosk | 🟡 solid | Grove listener; error handling | **Keep** (powers the suite) |
| public-ledger | 🟡 ~60% | broken entry point; no UI/persistence | **Fix entry; give it a UI** |
| bt-controller | 🟡 ~50% | no web UI; Win/WSL only | **Park** (niche) unless needed |
| source-trail | 🔴 ~50% | Postgres-only; no logic; no ask-jeles link | **Invest or fold into ask-jeles** |
| field-notes | 🟡 ~45% | feeds-the-Binder is a stub | **Finish capture→Binder** |
| nasa-archive | 🔴 ~40% | misnamed; cloud-bound; broken entry | **Rename + re-scope, or archive** |
| game (Jane GM) | 🔴 ~30% | crashes (14 bugs); no real GM logic | **Fix-or-park** (decide intent) |
| dating-wellbeing | 🔴 ~30% | no UI; Postgres-only; no logic | **Rebuild or archive** |
| the-binder | 🔴 ~25% | **shell; no engine** | **Invest hard** (keystone) or redefine |
| grove | external | local integration | **Track separately** |
| genealogy | ⚫ archived | — | **Leave archived** |

---

## 7. How to get there — the path (sovereign-first, true-standalone)

Now that direction (A3) and the standalone requirement are locked, the roadmap is concrete. The
ordering principle: **make the local suite genuinely ownable by a non-developer before anything else.**

### Phase 0 — Truth & hygiene *(small; unblocks everything; safe to start now)*
- Fix the broken entry points (`game`, `public-ledger`, `nasa-archive`, `dating-wellbeing`).
- Scrub **law-gazelle**'s manifest (real case numbers in a public repo); rename/re-scope **nasa-archive**.
- Resolve `llmphysics-bot/gerald-bot` (fill or delete).
- Make `catalog.json` statuses honest (use this doc's maturity column).
- *Outcome:* the catalog stops lying; nothing claims to work that doesn't.

### Phase 1 — Standalone flagships *(the core bet)*
Pick the flagship set (proposed: **story-timeline, ask-jeles, the-binder, private-ledger** — needs your
sign-off, §6). For each:
- **Run with zero Willow and zero Postgres** — local SQLite only, graceful no-op for cloud/LLM extras.
  (#16 already started this for the lattice apps; extend the pattern and make it the standard.)
- **`dev.sh` / `dev.ps1`** one-command launch (venv + deps + run), like ask-jeles/story-timeline.
- **Finish the Binder** — it's the keystone and currently a shell: add local storage + add/edit + a
  real connection engine. Without this, the knowledge pipeline has a hole in the middle.

### Phase 2 — A real store shell + the SAFE promise
- **Store UX:** a browse/install/launch surface (TUI first, web later) over `catalog.json` — retire
  "edit JSON + `make run`" as the only path.
- **Wire SAFE consent for real** in the flagships — the "Fully Explicit" permission prompt is the
  brand differentiator and is currently unimplemented everywhere.
- **One pipeline, end to end, as proof:** field-notes → the-binder → ask-jeles → story-timeline, with
  a consent prompt at each hop, all running locally with no backend.

### Phase 3 — Connect & polish
- Implement the real integrations the catalog already promises (private⇄public ledger;
  source-trail↔ask-jeles — or fold source-trail into ask-jeles).
- A shared design language / app shell so the suite feels like one product, not N prototypes.
- Personas: single source of truth (`libs/personas/`) so the characters-as-UI stay consistent.

### Where the cloud "universe" sits now
Kept alive as **demos/side channel** (per A3), not grown as the main thing. Low-touch: deploy the
ready Reddit bots if cheap, keep utety-chat running, fix persona drift opportunistically. No major
investment until the sovereign product stands on its own.

---

## 8. Status of the open questions

| Question | Resolution |
|----------|-----------|
| Is the **thesis** right? | ✅ **Agreed** (§2). |
| **Direction** — funnel / split / sovereign-first? | ✅ **Sovereign-first (A3)** (§4). |
| **Willow** — bundle / standalone / dev-only? | ✅ **True standalone** (no Willow, no Postgres) (§7 Phase 1). |
| **Cloud** acceptable? | ✅ Only as **demos**; the product is local-only. |
| Which apps are **flagships** vs **parked/archived**? | ⬜ **Open** — §6 proposes a cut (flagships: story-timeline, ask-jeles, the-binder, private-ledger; park: bt-controller, game, dating-wellbeing pending intent; rename/re-scope nasa-archive). **Needs your sign-off** before Phase 1 scopes.|

**Next concrete step once the flagship cut is signed off:** start **Phase 0** (hygiene), which is safe
and useful under any flagship choice.

ΔΣ=42
