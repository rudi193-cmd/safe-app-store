# Agent instructions — ai-game-master (the campaign-vault blueprint)

You are in a **blueprint repo**, not a campaign. Read `README.md` for the shape
and `docs/DECISION.md` for the settled decisions before proposing anything.

Two lines stay here because they are the whole point, and everything else is
downstream of them:

- **The machine proposes. The machine does not confirm.** No schema, script, or
  agent in this repo may write a `SEALED` or `REJECTED` canon row, or attribute
  a seal to a machine/persona/agent id. Only a **named human** at the head of
  the table seals canon (`schema/02_canon.sql`; enforced by
  `bootstrap/verify_ledger.py --canon`). This is the fleet covenant Nestor,
  terpsi-music, and willow-mcp all carry — do not weaken it here.

- **Repo = blueprint, never data.** No `campaign.db`, no `*.ledger.jsonl`, no
  grown `corpus/`, no signing `keys/`, no real player's name may ever be
  committed. A campaign is data and lives in a private **box** (the way the
  Vander game lives in `sean-data-vault`). The `.gitignore` is a safety
  guarantee, not a convenience — if populated data shows up in `git status`,
  stop.

## Operating rules

- **Prove the gate before you claim it.** A guard that cannot be shown to fail
  has not been shown to work. Every schema CHECK and every verifier refusal has
  a test that attempts the forbidden act and asserts the refusal
  (`bootstrap/verify_ledger.py --self-test`; the CHECK-bite tests). Add one when
  you add a guard.
- **Port, don't copy; attribute in the header.** The owned schemas are
  pattern-ports of Nestor / terpsi-music / Jeles organs — same shape, this
  repo's idiom, no verbatim code, and the source named in the file header with
  its pin. Keep it that way.
- **Reuse tier vs inject tier is a licence wall.** SRD text is CC-BY 4.0 and
  every such corpus row MUST carry its attribution (the CHECK enforces it). A
  campaign's canon, house rules, and guests are inject tier — DATA, never shared.
- **Corrections land beside the record, never on top of it.** A ruling
  supersedes an earlier one (`supersedes_id`); the old row stays, dated out. Do
  not overwrite history — the point of the chain is that no one can.
- **Absence is a value, not a missing row.** A verifier that cannot check
  signatures (no crypto lib) reports "unknown / unsigned counts", never a false
  "all good".

## Where the campaign lives

The played Vander campaign — its canon, its ledger, its guests (Bill Cipher and
friends) — is DATA. It lives in the private box, not here. This repo only knows
how to build the box it lives in.
