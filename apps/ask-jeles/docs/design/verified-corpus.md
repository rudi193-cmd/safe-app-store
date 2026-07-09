# Design: Verified-Nugget Corpus, Its Own MCP Server, and the Fleet Gap Backlog

Status: **SHIPPED** — PR #27 (`claude/ask-jeles-6itnz7` → `master`).
Companion: `willow-mcp`'s gap-backlog design doc —
`docs/design/gap-backlog.md` in `rudi193-cmd/willow-mcp` (PR #54) — the
system this corpus forwards its gaps into.

## 1. Problem statement

The original toy spec for Ask Jeles described a much smaller thing than
the app that existed: a chatbot answering from a curated corpus of
verified `{question, answer, sources, verified_by, verified_at, tags}`
nuggets, checking that corpus first, and — critically — saying "I don't
know yet" *and logging the question* on a miss, rather than just failing
silently. None of that existed. Ask Jeles already had a much richer
live-search machinery (KB soil scan, open web, institutional sources,
MCP), but no persisted layer of *settled* answers sitting in front of it,
and no memory of what it had been asked and couldn't answer.

## 2. Design principles

1. **The corpus sits in front of live search, it doesn't replace it.** A
   confident nugget match answers instantly — no search, no LLM call.
   Everything else falls through to the existing federated search+LLM
   path unchanged.
2. **`corpus.py` stays pure.** Storage and ranking have no MCP, no
   network, no side effects beyond SQLite — reusing willow-mcp's own SOIL
   `Store` schema (`WILLOW_STORE_ROOT/ask_jeles_corpus/store.db`) so
   nuggets are *also* visible to the existing local-KB soil scan for
   free, no extra wiring. Everything MCP-shaped wraps this module; it
   never depends on anything MCP-shaped itself. This is what keeps
   `corpus.py`'s own tests fast and network-free.
3. **The corpus is its own standalone MCP server, on purpose.** Rather
   than only being reachable through Ask Jeles's TUI, `corpus_server.py`
   is a small FastMCP server any stdio client can run directly
   (`python -m askjeles.corpus_server`) — mirroring willow-mcp's shape
   (`app_id` on every tool) without depending on willow-mcp or being
   willow-specific. Registered as a zero-config "built-in" MCP entry
   (path computed from `__file__`, so it's discoverable regardless of
   where the repo is cloned) alongside the existing Willow entry.
4. **Two different kinds of "ask," two different gap-logging rules.**
   `search_stacks()` (background/passive — every keystroke-driven search)
   checks the corpus but never logs a gap on a miss; that would flood the
   backlog with incidental noise. `synthesize_answer()` (deliberate —
   the `a` key / "ask Jeles a question") is the one place a miss is
   assumed to be a real gap worth tracking. Only the deliberate path logs.
5. **Local is the source of truth; the fleet backlog is additive.**
   `corpus.log_gap()` (synchronous, local SQLite) always runs first and
   is what makes Ask Jeles fully functional offline. `willow_mcp_client
   .forward_gap()` is a *best-effort* copy into willow-mcp's fleet-wide
   backlog (`docs/design/gap-backlog.md` in that repo) — fire-and-forget,
   never blocks, never raises, and resolves "willow-mcp isn't installed"
   in milliseconds. See §4 for a bug this principle caught.
6. **Consent for a surprise must disclose scope even when it hides
   content.** See §5.

## 3. Ranking and the "exact" threshold

Nugget search scores question-token overlap highest (exact question match
≫ partial ≫ mere answer-text overlap), with a `MIN_ASK_SCORE` floor below
which `ask_corpus()` refuses to call something a confident answer — a
weak overlap (e.g. two nuggets both mentioning "color") must not be
mistaken for actually answering the question, and instead correctly
falls through to a logged gap. `search_nuggets()` (the passive path) has
no such floor — a loosely-relevant nugget is still fine to *surface* in
a ranked hit list, just not fine to *answer with*.

In `search_stacks()`'s merge, a corpus hit outranks even the local KB
soil scan (`+0.9` vs `+0.65`) — a human-verified nugget should always win
over an unverified soil hit on the same query.

## 4. Forwarding to the fleet backlog — the retry bug

`willow_mcp_client.py` mirrors `mcp_client.py`'s lazy-session pattern
(background asyncio loop + thread, `ensure_started()`), located via
`WILLOW_MCP_CMD` override → `willow-mcp` on `PATH` → `python -m
willow_mcp` against the current interpreter. No hardcoded paths.

First version had a real bug, caught in review rather than in production:
`ensure_started()` cached its event loop permanently once created, so a
single failed connection attempt (willow-mcp not running yet at Ask
Jeles's boot, any transient failure) silently disabled forwarding for
the rest of a long TUI session — even after willow-mcp came online.
"Best effort" had quietly become "one effort." Fixed with a 30s retry
cooldown: a stale failure gets retried, but not on every single
`forward_gap()` call while willow-mcp stays down.

Verified end-to-end against a real willow-mcp subprocess (not just
mocked) — a forwarded gap from both `synthesize_answer()` and
`corpus_server.py`'s `corpus_ask` tool was confirmed to land correctly
in willow-mcp's SOIL-backed backlog under the `ask-jeles-corpus` topic.

## 5. The 13th-question seed offer — a consent design correction

Originally proposed as: on some periodic usage count, a popup says
"I'm going to plant a seed, would you like me to?" without disclosing
what, and saying yes *also* grants a standing "automatic edge creation"
capability.

That shape was rejected during design, not built: bundling an
undisclosed action with a silently-granted standing write capability
behind one vague consent click is the exact pattern willow-2.0's own
`human_required.check_write_gate()` exists to prevent — `edge_write`
requires its own named, disclosed consent there, never folded into an
unrelated "yes." Willow-mcp's README states the general principle
plainly: "an agent may request egress and may never grant it to itself."

What shipped instead, after design conversation converged: `milestones
.py` fires **exactly once, ever** — the literal 13th question asked to
Jeles, not every 13th — with a message that discloses scope honestly
while keeping only the *content* a surprise: *"I'd like to plant
something in your corpus — a single nugget. I won't tell you what it is
until you look. May I?"* Saying yes writes exactly one nugget via the
same `corpus.put_nugget()` path every other nugget already uses — no new
permission, no standing capability, nothing "automatic." The mystery is
about what gets written, never about what saying yes means.

`SeedOfferModal` (`overlays.py`, mirroring `TriviaModal`'s shape) makes
the confirm/decline a real, explicit user action in the TUI — declining
(`n`/Escape/dismiss) writes nothing.

## 6. Open questions (not yet decided)

- Should other apps in the store grow their own corpora feeding the same
  willow-mcp backlog, or does this stay ask-jeles-specific for now?
- Auto-drafting candidates for high-`asked_count` gaps (a "gap-
  anticipation loop") — see willow-mcp's design doc §6. Nothing here
  generates a draft today; `gap_promote`/`corpus_put` are both entirely
  hand-authored acts.
- `seed_easter_egg.py` (manual script, nugget id `"42"`) predates the
  milestone system and still exists standalone — fold into it, or keep
  both as separate, independent surprises?
- Local gaps (`ask_jeles_corpus_gaps`) and the fleet backlog
  (`gaps`/topic `ask-jeles-corpus`) can drift — a gap resolved locally
  isn't reflected in willow-mcp, and vice versa. No reconciliation exists
  yet.
