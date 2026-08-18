# Promotion recon — willow-gate seal recipe for `homestead-health`

**Scout:** promotion-readiness pass · **Date:** 2026-08-18 · **Candidate:** `apps/homestead-health`
**willow-gate source read:** `rudi193-cmd/willow-gate` @ `9e75137` (PR #30 merged), cloned `GIT_LFS_SKIP_SMUDGE=1 --depth 1`.

---

## TL;DR — the one answer that matters

**The cryptographic seal is NOT required to promote `homestead-health`. The string floor suffices, and it is what you should use.**

Per `stores/promote_check.py:_witnessed()` (lines 197–298), the `witnessed [M]` gate has two tiers:

- **FLOOR (always runs, stdlib-only):** `verified_by` is set and `verified_by != author`. That is *all a promotion needs by default* — the module docstring says so verbatim (lines 37–39: "Its FLOOR is the string check … and that is all a promotion needs by default").
- **SEAL (opt-in, fail-closed):** declared *only* by adding a `trust` block to `promotion.json`. The moment that block exists, the gate stops accepting the name and demands a verified cryptographic ratification. **A claimed seal that cannot be verified is a FAILURE — it never falls back to the floor** (lines 42–44, 235–237).

So a `trust` block is a strictly higher bar you opt into, not a requirement. For `homestead-health`, **do not add a `trust` block** — see "Why not, right now" below. Satisfy the floor: set `author` and a *different* `verified_by` (§0.2 — proposing and ratifying never rest in the same hand).

---

## Why not the seal, right now (the blocking finding)

The seal path is imported lazily and needs **four** packages present at the gate end (`promote_check.py` lines 259–267):

```python
from willow_gate.custody import ChainError, CustodyLedger   # willow-gate
from forge.trust import witnessed as trust_witnessed        # the-forge  (NOT willow-gate)
from nestor.keyring import get_keyring                       # nestor
from nestor.signing import _verifies_with                    # nestor
```

**None of these are installed in `safe-app-store`.** Verified in-repo:

```
$ python3 -c "import forge.trust"      → ModuleNotFoundError
$ python3 -c "import nestor.keyring"   → ModuleNotFoundError
$ python3 -c "import willow_gate.custody" → ModuleNotFoundError
$ echo "$NESTOR_KEYRING"               → (unset)
```

Consequences if you add a `trust` block today:

1. The `import` fails → `_witnessed()` returns **FAIL** with `"seal declared but the cloud seam … is not installed at this end (fail-closed)"` (lines 264–267).
2. Even with the packages installed, `get_keyring()` returns `None` unless `NESTOR_KEYRING` is set → **FAIL** (lines 269–272).

**Net: declaring a seal for `homestead-health` today would break an otherwise-passing promotion.** The floor is not a downgrade here — it is the correct and only viable tier until the forge/nestor/willow-gate seam is installed and a keyring is provisioned.

Also note the seam boundary the task framed: **willow-gate does *not* own the seal.** willow-gate supplies exactly one piece of it — the custody ledger primitive (`CustodyLedger` + `checkpoint`/`verify_checkpoint`). The verdict function `forge.trust.witnessed()` lives in **the-forge**, and the keyring/signature-verify helpers live in **nestor**. willow-gate is a dependency of the seal, not the seal.

---

## What willow-gate actually provides

### `willow_gate.custody` — the custody ledger (the piece promote_check consumes)

Read: `src/willow_gate/custody.py`, spec `docs/custody-ledger-spec.md`, tests `tests/test_custody.py`.

An append-only, hash-chained event log, built in four tiers. The seal uses Tier 1 (the chain) and Tier 4 (the signed checkpoint):

- **`CustodyLedger`** (`custody.py:283`) — `append(event)` is the only write; `verify()` recomputes the chain; `head_hash` is the current head. Events are canonicalized (sorted keys, NFC, no floats, `sig` excluded, nulls omitted, ASCII-escaped — `canonicalize()`, line 241) before hashing, so the chain is byte-stable.
- **`CustodyLedger.load(path)`** (`custody.py:377`) — rebuilds from a JSONL file **and re-verifies it, fail-closed**: a tampered/truncated/secret-carrying/illegal-kind file raises **`ChainError`** rather than loading. This is exactly what `promote_check._witnessed()` calls at line 286, catching `ChainError` → FAIL.
- **`ChainError`** (`custody.py:109`) — raised on any load-time integrity failure.
- **`checkpoint(ledger, signer)`** (`custody.py:822`) — Tier 4 sealing. Signs *the chain head hash itself* and appends a system-only `checkpoint` event carrying `{"kind":"checkpoint", "covers_to_seq": <int>, "head_hash": <hex>, "sig": <str>}`. The head commits to the whole prefix through the chain, so one signature seals everything before it.
- **`verify_checkpoint(ledger, checkpoint_event, signer)`** (`custody.py:837`) — recomputes the head over `events[0..covers_to_seq]`, fails if the chain is broken there, if the recomputed head ≠ the claimed `head_hash`, or if `signer.verify(head, sig)` is false. This is the function that catches a re-derived-chain forgery that bare Tier-1 `verify()` cannot (`tests/test_custody.py:932`).

**The signer contract** (custody is signer-agnostic — `custody.py:788–794`, spec lines 172–175):

```python
sign(data: bytes) -> str          # a detached signature (hex/ASCII-armored)
verify(data: bytes, sig: str) -> bool
```

Production signer is `GpgSigner` (`custody.py:903`, python-gnupg detached ASCII sigs, imported lazily). Tests drive it with a deterministic HMAC signer (`tests/test_custody.py:906 _HmacSigner`). `promote_check` supplies its **own verify-only signer**, `_KeyringVerifier` (`promote_check.py:279–283`), whose `.verify()` calls `nestor.signing._verifies_with(entry.kind, entry.key, data, sig)` against the **public** key pulled from the keyring — it never signs.

### `willow_gate` (the gate itself) — trust tiers and the HMAC header

Read: `src/willow_gate/__init__.py`, `tests/test_signing_encoding.py`.

The task asked about "Rookie/Steady/Veteran" trust tiers — those are **`TRUST_LEVELS`** (`__init__.py:77`), a 5-rung ladder, not part of the promotion seal but the context the fleet's word "witnessed" comes from:

| Lvl | Name | entry? | read-only | write/export | tools | max_fail | min_pass |
|----|---------|--------|-----------|--------------|-------|----------|----------|
| 0 | Exiled  | no  | yes | no  | ()                                   | —  | —  |
| 1 | Rookie  | yes | yes | no  | read                                 | 5  | 0  |
| 2 | Steady  | yes | no  | yes | read, write                          | 3  | 3  |
| 3 | Veteran | yes | no  | yes | read, write, query, execute          | 2  | 11 |
| 4 | Elder   | yes | no  | yes | read, write, query, execute, admin   | 1  | 50 |

Key hardening properties (all cited from the module docstring, `__init__.py:1–41`): trust is **bound, not self-reported** — the 64-hex `signature` header field is an **HMAC-SHA256 over the canonical header** (`canonical_header_bytes`, `__init__.py:98`) keyed by a per-agent secret the gate holds out-of-band (`_authenticate`, line 250); a claimed `trust_level` is capped at the agent's registered `max_trust`. Drift/fail budgets *tighten* as trust rises. Rungs are *earned* (gate-witnessed check-outs accrue a tally) rather than typed into a header, when `WILLOW_GATE_ENFORCE_EARNED_RUNGS` is on (`__init__.py:200–219`).

### "signed → allowed, tampered → denied" — where it actually lives

The task attributed sap-gate's `signed → allowed, tampered → denied` to willow-gate. Clarification from reading both:

- **The sap-gate that signs *app manifests* is in THIS repo**, `stores/sap_gate.py` — Ed25519 (`cryptography` pkg) over four bound fields `("app_id","permissions","store_scope","maker")` (`sap_gate.py:75, 90`), attested by a hash-chained `SigningLedger` with rotate/compromise events. `verify_manifest()` (`sap_gate.py:301`) is fail-closed: raises `GateError` on tamper, unknown key, un-attested signature, or a signature made after a recorded compromise. **It is not invoked by `promote_check.py` at all** — it is a separate, build-attribution gate.
- **willow-gate's own "signed→allowed" surfaces** are two: (a) the HMAC 13-field check-in header above, and (b) the Tier-4 **checkpoint signature** (`verify_checkpoint`). The promotion seal uses (b), not (a), and not sap-gate's Ed25519.

(One incidental note if manifest-signing is ever wanted for `homestead-health`: its `safe-app-manifest.json` currently has `app_id` and `permissions` but **no `store_scope` and no `maker`** — both are `MANIFEST_BOUND_FIELDS` that `sap_gate.sign_manifest` requires, and `maker` must equal the signing `builder_id`. Out of scope for `promote_check`, listed only so the gap is on record.)

---

## The recipe — a valid `trust` block, end to end

This is what `promote_check._witnessed()` demands once a `trust` block is present (`promote_check.py:238–298`). Provide it **only** after the forge/nestor/willow-gate seam is installed at the gate and `NESTOR_KEYRING` is provisioned; otherwise use the floor.

### Files & fields the `trust` block must supply

In `apps/homestead-health/promotion.json`:

```json
{
  "app_id":       "homestead-health",
  "author":       "USER",
  "verified_by":  "rudi193",
  "repo_url":     "https://github.com/rudi193-cmd/homestead-health",
  "host":         "homestead",
  "core_module":  "homestead_health",
  "semantic_seam":"homestead_health.<module>:<Symbol>",
  "host_repointed": true,
  "major":        "python",
  "trust": {
    "custody":     "trust/custody.jsonl",
    "checkpoint":  "trust/checkpoint.json",
    "author_id":   "agent:vishwakarma",
    "verifier_id": "rudi193"
  }
}
```

Hard constraints the gate enforces (fail-closed) before it ever touches crypto:

1. **Floor still applies:** `author` set, `verified_by` set, `author != verified_by` (line 240–242). `verified_by == author` fails even with a perfect seal.
2. **`trust.verifier_id` MUST equal `verified_by`** (line 246–249) — "the hand named in the seal is the hand recorded as verifier". Here both are `rudi193`.
3. **`trust.author_id` must be non-empty** (line 250–251) — the actor who provisionally sealed, i.e. the ledger actor that appended the provenance events.
4. **`custody` and `checkpoint` are candidate-relative paths that may not escape the candidate dir** (`_within`, lines 181–194) — keep them under `apps/homestead-health/trust/`.

### Step-by-step: producing the two trust files

**Who signs what:** the **author** (`agent:vishwakarma`) *builds* the custody ledger of the app's provenance; the **verifier** (`rudi193`) *signs the checkpoint* with their private key. The verifier's **public** key is what the gate resolves from `NESTOR_KEYRING` — never anything the candidate ships (lines 269–277). Author proposes, verifier ratifies — §0.2 made cryptographic.

1. **Author builds the custody ledger** — persisted to `apps/homestead-health/trust/custody.jsonl`:

   ```python
   from willow_gate.custody import CustodyLedger, session_check_in, session_record_action
   led = CustodyLedger(path="apps/homestead-health/trust/custody.jsonl")
   # record the provisional-seal provenance under the AUTHOR as actor:
   session_check_in(led, session_id="promote-homestead-health", actor="agent:vishwakarma",
                    declared={"tools": ["read"]}, ts="2026-08-18T00:00:00Z")
   session_record_action(led, "promote-homestead-health", "agent:vishwakarma",
                         "promote", ts="2026-08-18T00:00:01Z")
   # (any faithful record of the extraction is fine; the point is a verifiable chain
   #  whose actor == author_id. Do NOT put secrets in it — append() is fail-closed on
   #  credential-shaped values.)
   ```

   `CustodyLedger.load()` at the gate will re-verify this file and raise `ChainError` on any tamper, so it must be a genuine, unedited chain.

2. **Verifier seals the head** — `checkpoint()` signed with `rudi193`'s **private** key, written to `apps/homestead-health/trust/checkpoint.json`:

   ```python
   from willow_gate.custody import checkpoint
   verifier_signer = GpgSigner(rudi193_fingerprint, gnupghome=...)   # or nestor's signer
   cp = checkpoint(led, verifier_signer)     # {"kind":"checkpoint","covers_to_seq":N,
                                             #  "head_hash":"<hex>","sig":"<detached>"}
   import json, pathlib
   pathlib.Path("apps/homestead-health/trust/checkpoint.json").write_text(json.dumps(cp))
   ```

   `checkpoint()` also appends the checkpoint event into the ledger; make sure the `custody.jsonl` you ship is the one that includes it (or that `covers_to_seq` still resolves against the shipped chain — `verify_checkpoint` recomputes the head over `events[0..covers_to_seq]`).

3. **Register the verifier's PUBLIC key in the fleet keyring** and point the gate at it:

   ```
   export NESTOR_KEYRING=/path/to/fleet/keyring     # get_keyring() reads this
   ```

   The keyring must have a trusted (non-revoked) verifying entry for `verifier_id="rudi193"` — `ring.verifying_entry("rudi193")` must return an entry, or the gate fails "not trusted in the keyring" (lines 273–277).

4. **Install the seam at the gate end** so the lazy import at `promote_check.py:259` resolves: `willow_gate`, `forge.trust`, and `nestor` (keyring + signing) all importable in the environment running `promote_check.py`.

### What the gate then does (so you can predict PASS/FAIL)

`_witnessed()` (lines 285–298):

1. `CustodyLedger.load(custody.jsonl)` → hash-verifies the chain (`ChainError` → FAIL).
2. `json.loads(checkpoint.json)` → the checkpoint event.
3. `get_keyring()` → resolve `verifier_id`'s **public** key → wrap in `_KeyringVerifier` (verify-only).
4. `forge.trust.witnessed(led, checkpoint_event, _KeyringVerifier(), author_id=<author_id>, verifier_id=<verifier_id>, app_id=<app_id>)` → this is the-forge's verdict function; from the call shape and the willow-gate primitives it wraps, it verifies the checkpoint (via `verify_checkpoint`) is signed by the verifier's key and that the author's provisional seal sits in the verified chain. Returns an object with `.ok` and `.reason`.
5. `w.ok` → PASS (`"sealed: <reason>"`) else FAIL (`"seal rejected: <reason>"`).

> **Caveat on step 4:** `forge.trust.witnessed()` is in **the-forge**, which is not present in `safe-app-store` or `willow-gate`, so its exact internal checks could not be read directly — the description above is reconstructed from its call signature in `promote_check.py:295–296` and the willow-gate primitives it must be built on (`CustodyLedger`, `verify_checkpoint`). Confirm against the-forge before relying on the precise semantics of `author_id`/`app_id` binding.

---

## Recommendation

1. **Promote on the floor.** Give `homestead-health` a `promotion.json` with `author` and a distinct `verified_by`, and **omit the `trust` block entirely.** The gate stays stdlib-only and passes the `witnessed` gate on the string check.
2. **Do not declare a seal** until: (a) `willow_gate`, `forge.trust`, and `nestor` are installed where `promote_check.py` runs; (b) `NESTOR_KEYRING` is provisioned with a trusted verifying entry for the verifier; (c) the verifier (≠ author) actually holds the private key and signs the checkpoint. Until all three hold, a `trust` block converts a passing promotion into a fail-closed rejection.
3. The floor already encodes the real §0.2 guarantee (`verified_by != author`) and is independently re-checked on the `--record` write path (`record_promotion`, `promote_check.py:522–526`), so a floor-tier promotion is not "unwitnessed" — it is witnessed by a named, distinct hand, just not cryptographically sealed.

---

### Sources read

- **This repo:** `stores/promote_check.py` (`_witnessed`, `_within`, `record_promotion`, lazy seam imports), `stores/sap_gate.py` (Ed25519 manifest signing, `SigningLedger`, `verify_manifest`), `apps/homestead-health/safe-app-manifest.json`.
- **willow-gate @ `9e75137`:** `src/willow_gate/custody.py` (`CustodyLedger`, `ChainError`, `checkpoint`, `verify_checkpoint`, signer contract, `GpgSigner`, `CustodyLedger.load`), `src/willow_gate/__init__.py` (`TRUST_LEVELS`, `WillowGate`, `canonical_header_bytes`, HMAC binding), `docs/custody-ledger-spec.md` (tiers, canonicalization, the Tier-4 boundary), `tests/test_custody.py` (`_HmacSigner`, `checkpoint`/`verify_checkpoint` gates), `tests/test_signing_encoding.py` (canonical header golden vector).
- **Confirmed absent in this repo:** `forge.trust`, `nestor.keyring`, `nestor.signing`, `willow_gate` (import checks), and `NESTOR_KEYRING` (unset).
