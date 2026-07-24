# The Almanac — a data branch, not a stored thing
b17: SAPS1

Not a code store. Not a major craft. A **branch** — the fleet's public record,
an **auto-updated list.**

The other stores *keep* things (code, promoted apps). The Almanac is the one
place where keeping would be a mistake: it is a self-renewing list, so the store
**does not store it.** That is the deep half of `instaurare` — *renew* — taken
to its limit. A copy in the tree would only go stale. The store points at the
live list instead.

*(This is why the `almanac-data` verticals fetched earlier were never committed:
correctly. You don't store what updates itself. You subscribe to it.)*

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

Two knowledge sources, one search seam:

| | private | public |
|---|---|---|
| home | the local corpus (your embedded documents) | **the Almanac** |
| kept? | local only — never git, never shipped (the vault is the key) | not kept — auto-updated, fetched live |
| injected | yes | yes |

The semantic-search socket every promoted app carries takes either — or both.

## The branch

This directory is a **pointer**, not a payload: it declares *where the live list
lives and how to reach it*, and stays deliberately empty of data. An auto-updated
list has no resting copy here to drift. What updates itself, the store does not
store.

---

*Renewal without keeping — the one thing in the house that is never filed,
because it re-files itself. `ΔΣ=42`*
