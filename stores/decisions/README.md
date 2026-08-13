# The Decision Record
b17: SAPS1

*The store-side half of N9's third chokepoint (`nestor:docs/decision-memory.md`):
the fleet's ratified decisions, kept where a cold agent finds them at boot.
The cold-agent failure is not a wrong answer — it is a proposal that felt
obviously right, so nobody queried for objections. This directory is the
objection, pre-loaded.*

## What `fleet.json` is

The **keeping record** of the fleet's sealed decisions and standing
rejections — human-readable, git-tracked, diffable in review like any other
law. Not a database: the signed store (an `apps/aristarchus`-shaped SQLite
db with HMAC seals and a hash-chained ledger) lives in the operator's vault
and is rebuilt from this seed; the seal key never enters git, so this file
carries the *content* of the law while the vault carries its *signatures*.
Same split as everything else in the house: ship the reader, the corpus
stays with whoever grew it — here, the record travels and the keys stay home.

## The shape, and why each field exists

- Every **decision** carries `reason` — the why behind the yes, which is
  what a future proposal must argue against (N4).
- Every **rejection** carries `reason` and `reopen_when`. Empty
  `reopen_when` means **never**, and empty is a deliberate act — an
  unexplained or accidentally-permanent rejection is the Aristarchus bug,
  eighteen centuries of it (N5).
- Every entry names `verified_by`, and it differs from `author` — proposing
  and ratifying never rest in the same hand (§0.2).

`tools/decisions_boot.py` renders this at session boot and validates the
covenant; `tests/test_fleet_decisions.py` is the CI gate that keeps the
record well-formed. A violation fails the build: a malformed law is worse
than no law, because it is *reassuring*.

## Consulting Nestor — the MCP wiring (2026-08-13 give-back)

CLAUDE.md rule 11 says to check `Nestor` before writing a mechanism — *"has a
human checked this — seal, durable rejection, ledger."* Until this give-back
that was prose only: `.mcp.json` had no `nestor` entry and nothing read from
it. Two pieces close the gap, and both keep the covenant this directory
states above — the machine may ask and propose; it may never seal.

- **`.mcp.json`'s `"nestor"` entry** runs `nestor serve` (the real Nestor MCP
  server, `nestor/serve.py` — stdlib-only, JSON-RPC 2.0 over stdio) keyed to
  `--source-lang decision --target-lang decision`, so a model in this repo
  can ask `nestor_ask`/`nestor_check`/`nestor_provenance`/
  `nestor_ledger_verify`/`nestor_propose` about a decision by its question
  text without passing domain tags on every call. It is **not** started
  `--read-only`: `nestor_propose` (queue a draft for a human) is meant to be
  reachable from here. No sealing tool is ever exposed — that is `serve.py`'s
  own `WITHHELD` set, not a flag this repo could accidentally flip.
  Requires the `nestor` console script on `PATH`, pinned:
  `pip install "nestor @ git+https://github.com/rudi193-cmd/Nestor@v0.2.0"`
  (Nestor is not on PyPI — see `stores/requirements.txt`'s own note for
  `stores/checkpoint_memory.py`, a sibling, unrelated consumer of the same
  package). The server's db/ledger live under `stores/decisions/.nestor/`,
  gitignored — the operator's local vault, not repo content, same as
  `stores/.principals/` and its siblings.
- **`tools/decisions_boot.py`'s best-effort cross-check** (`_consult_nestor`)
  spawns that same `nestor serve` subprocess and asks it, over the literal
  MCP protocol, whether each live decision in this file is already known to
  the operator's Nestor vault — a second, independent read of "has a human
  checked this," alongside this file's own `verified_by` field. It is
  **fail-open by construction**: no `nestor` on `PATH`, no response inside
  the timeout, or a malformed reply all report `unknown` — never a false
  "clean," and never a build failure. `--strict`'s covenant gate (the
  `question`/`commitment`/`reason`/`verified_by`/`reopen_when` checks above)
  does not depend on Nestor being reachable at all; the cross-check is an
  additional signal printed alongside the render, not a new way to fail CI
  (this directory's own decision: *"May the decision gate fail builds
  fail-closed? no - warn-mode only"*). Skip it with `--no-nestor` for a
  faster/offline run.

## How to change it

- A new decision: append with reason, author, verifier. The verifier is not
  the author.
- Changing a decision: **supersede, don't edit** — new entry, old one gains
  `"superseded_by": "<date or record>"` and stays. The lineage is reasons,
  not just rows.
- Reopening a rejection: only by its own `reopen_when` coming true. Resolve
  by making the decision, not by editing the rejection to make it disappear
  (`stores/pending.json`'s rule, applied to law).

---

*The machine proposes; the operator seals; the record is what stores/ stores.
`ΔΣ=42`*
