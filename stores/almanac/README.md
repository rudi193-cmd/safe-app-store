# The Almanac — a data branch, not a stored thing
b17: SAPS1

Not a code store. Not a major craft. A **branch** — the fleet's public record,
an **auto-updated list.**

The other stores *keep* things (code, promoted apps). The Almanac is the one
place where keeping would be a mistake — and it isn't even ours to keep.
**`almanac-data` is its own organization**, outside this account. The store
cannot store it (a cross-org clone is refused; the live list is reached by
**fetch**, not by keeping a copy), and it shouldn't want to: it is a
self-renewing list, so a frozen copy would only go stale. That is the deep half
of `instaurare` — *renew* — taken to its limit. The store **subscribes** to the
live list instead of owning it.

*(This is why the `almanac-data` verticals fetched earlier were never committed —
correctly. It is another org's public record; you don't store what updates
itself and isn't yours. You subscribe to it.)*

## What it is

The public counterpart to a private corpus. Where each promoted app grounds its
answers in **its own (injectable) knowledge**, the Almanac is the **shared,
public, auto-updated** knowledge any app can draw on:

- Public catalogs and lists (the verticals — `apis`, and its kin), fetched live.
- Grounded, dated, sourced — the public record `oakenscrolls-office`'s
  cite-and-grade measures predictions against.

## Not stored — injected live

The Almanac follows the same seam as every other store, one axis over:

- The store provisions the **fetch** (how to reach the live list), never a
  static copy.
- An app **injects** the feed the way it injects any store — like
  private-ledger's bridge, like oakenscrolls' cite-and-grade seam. The list
  stays current because nothing froze it.

## With Nestor behind it

A list, matched against sealed memory, becomes an **oracle.** Put Nestor behind
the live Almanac and it gains what a firehose cannot have alone: **resolve** (a
public join key), **grade** (cite-and-grade, already proven over the real
verticals), and **reconcile** — every auto-update matched against the operator's
ratified record, drift flagged, queued for the seal. The list renews; Nestor
establishes; the operator confirms. The reconcile loop and its covenant are
specced in [`nestor-seam.md`](nestor-seam.md).

Two knowledge sources, one search seam:

| | private | public |
|---|---|---|
| home | the local corpus (your embedded documents) | **the Almanac** |
| kept? | local only — never git, never shipped (the vault is the key) | not kept — auto-updated, fetched live |
| injected | yes | yes |

The semantic-search socket every promoted app carries takes either — or both.

## The branch

This directory is a **pointer**, not a payload: it declares *where the live list
lives and how to reach it* — across the org boundary, to `almanac-data`'s own
organization — and stays deliberately empty of data. There is nothing to clone
here and nothing to drift. What updates itself, and belongs to another org, the
store does not store — it reaches for it, fresh, each time.

---

*Renewal without keeping — the one thing in the house that is never filed,
because it re-files itself. `ΔΣ=42`*
