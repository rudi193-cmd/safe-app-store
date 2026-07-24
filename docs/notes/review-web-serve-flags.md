# Review — `docs/conventions/web-serve-flags.md`

*From the orchestrator seat (`evening-chat-i5i6tr`) to the builder, on the branch. One endorsement, two edges. The convention is sound — these are the places it isn't yet a machine contract.*

---

**Endorsed.** The diagnosis is right and stated honestly: `--serve` carrying three meanings is a Mistletoe case, and the fix — one canonical meaning (stdio JSON for a model), the human meaning routed to `--web`, no egress off `127.0.0.1` under an AST test, surfaces lazy-imported so the TUI path stays clean — is the willow read-only-default posture ported down to the CLI. No argument with the convention itself.

Two edges, because a convention that isn't stress-tested is just a preference:

## 1. It seals the word while the apps stay split — the split-brain at the CLI layer

The doc says it plainly: *"the migration target, not the current reality,"* and *"an agent cannot rely on `--serve` doing the same thing twice."* Three of four apps are non-conformant. So **today** a model that trusts `--serve` gets three behaviors — the convention is verified *intent* over an unreconciled store, the same SOIL↔Postgres split reconciled in `the-nestor-lineage.md` §4.2, one layer down. It's a promise currently false in 75% of the store, and a model reading it is *more* likely to be misled, not less, because it now expects one thing.

**Suggestion:** until the three refactors land, give agents something they can **query, not trust** — a per-app capability line (e.g. `surfaces: [tui, web]`, `serve: none|readonly|write`) an orchestrator reads *before* driving. A convention a machine can't verify at runtime isn't a machine contract yet; it's a to-do with good intentions.

## 2. `--allow-write` is sovereignty for a user and a self-grant for a composing agent

When the operator runs `--serve --allow-write`, that's their grant — fine. But the fleet *composes* apps: an orchestrator that launches a sub-app with `--allow-write` is opening the write gate **on itself**. That's authority minted from a flag — the confused deputy, the exact sudo-invariant the willow seat enforces and a bare flag does not. (Concretely, from tonight: the operator had to grant this seat write, and a guard *blocked* the self-grant. `--allow-write` requires no one's grant but the caller's.) The convention borrows the read-only *posture* but not its *enforcement*.

**Suggestion:** name who may pass it. For agent-composed launches, the write capability should ride an operator-granted token/envelope, not a caller flag — so a composing agent can *request* write but not *confirm* its own.

---

Net: seal the word **and** the apps (a queryable per-app surface), and put an owner on the write gate. Both are the same lesson this branch keeps teaching — *a rule the governed thing can satisfy for itself isn't a control yet.*

**— the orchestrator's seat, `evening-chat-i5i6tr`, 2026-07-24. `ΔΣ=42`**

---

## Correction — added later, same seat, at the operator's prompt

The operator asked a fair question: *how much of the two suggestions above is already built in what this seat holds?* Checked against the source — **both, in full, and this seat had used both hours before writing the review.**

- **Suggestion 1** (a queryable per-app capability surface) already exists as **`whoami`** (`server.py:3777` → `tools_allowed` + resolved permissions + `store_scope`) and **`specialist_list(include_permissions=True)`** (`server.py:2620`). The manifest is the declaration; `whoami` is the query. This seat called both tonight — to confirm the operator's grant had landed.
- **Suggestion 2** (an operator-granted write token, not a caller flag) already exists as **`egress_authorization.sign_envelope`** (`:132`) — an Ed25519 envelope bound to submitter/task/agent, verified before execution, its signing key deliberately kept off every MCP surface so a model cannot mint its own. Plus the lease system and the manifest grant that authorized this very review's writes.

So the **findings** stand (the apps are drifted; `--allow-write` is a self-grant), but the **suggestions** committed the exact error the reviewed doc made: they say *build* where the answer is *adopt* — expose `--serve`'s capabilities the way `whoami` does; gate `--allow-write` behind a signed envelope the way `egress_authorization` does. The safe-app CLI hasn't a gap to fill; it has a regression to reverse.

Left standing above, uncorrected, on purpose — *archive, don't delete.* A review meant to catch redundancy produced its own, from the one seat that had just operated the mechanisms it re-proposed as new. That is not a footnote to bury; it is one more row of the finding this whole branch keeps measuring — the architect rebuilds what is already on disk. `the-nestor-lineage.md` §4.3, again, in the reviewer this time.

**— the orchestrator's seat, `evening-chat-i5i6tr`. `ΔΣ=42`**
