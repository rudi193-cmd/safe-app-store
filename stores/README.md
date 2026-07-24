# The Stores
b17: SAPS1

*A store, in the oldest sense — not a shop, a **provision-house.** From Latin
`instaurare`: to establish, and to renew. A place where work-in-becoming is
**kept**, **provisioned**, and — when it is ready — **promoted** into a full,
standing SAFE app.*

The SAFE App Store is not one store. It is a store **per major** — one home for
each craft people build in. Someone wants to build an Obsidian plugin; someone a
Node CLI; someone a C++ tool; someone a Textual TUI. Each gets provisioned from
the same forge, under the same law, and graduates by the same bar.

Open. Apache-2.0. Build in your own local space or in a repo under the account;
it stays yours until it's promoted.

## The two tiers

Every store holds work at one of two stages:

- **Stored** — provisional, incubating. A held piece: local, or a loose repo.
  Low bar. Not yet established.
- **Promoted** — a full SAFE app: **its own repo · injected seams (host imports
  it, never the reverse) · its own tests green · a manifest · a
  dependency-light / import-pure core · MCP-shaped or library-clean · a
  semantic-search seam over its own (injectable) knowledge · host repointed as a
  consumer.** Established and renewed.

*Nestor and Jeles are the worked examples of promotion — each lifted from inside
a host into its own repo with injected storage and its own tests.* The scaffold
in each store is the enrollment; those two are the graduation.

## The majors

| Store | Craft | Scaffold / starter |
|---|---|---|
| [`python/`](python/) | Textual · Rich · CLI | the generic TUI scaffold |
| [`node/`](node/) | Node.js · Ink · Electron · CLI | — |
| [`rust/`](rust/) | Ratatui · crossterm | — |
| [`go/`](go/) | Bubble Tea · Charm | — |
| [`cpp/`](cpp/) | C++ tools & apps | — |
| [`obsidian/`](obsidian/) | Obsidian plugins & vaults | — |

The list is open — a store is added when someone brings a craft to build in. The
`tui-design` skill (`.agents/skills/tui-design`) already carries per-ecosystem
guidance for the terminal ones (Go/Rust/Python/TS).

## The Almanac — a branch, not a store

One node here is a different kind: [`almanac/`](almanac/) is **not** a code
store and holds no `stored/`/`promoted/` tiers. It is the fleet's public record —
an **auto-updated list** — and the whole point is that *the store does not store
it.* A self-renewing list needs no keeping; a frozen copy only goes stale. So the
Almanac is a **pointer to a live feed**, injected the same way a corpus is. It is
the `renew` half of `instaurare`, standing alone.

## The one seam every store shares

A promoted app comes with **its knowledge, semantically reachable** — the
scaffold ships the **semantic-search socket**; the document store is
**injected**. The capability travels; the corpus does not. *Ship the mold and
the reader; the wood stays with whoever grew it.* (The vault is the key.)

---

*The head of this house is the architect, not a shopkeeper. `ΔΣ=42`*
