#!/usr/bin/env python3
"""stores/sap_gate.py — the signed-manifest gate (D4, docs/design/the-forge.md).

"signed -> allowed, tampered -> denied," made real. This is store-side
authority (D1 of the design doc): it decides whether a build's manifest is
trustworthy, using keys the store itself holds. That authority stays here
even after The Forge is promoted (D13) — the host imports the builder, never
the reverse, and the same direction holds for who gets to say yes to a
manifest. `apps/the-forge/` never imports this module; this module may
import from `the_forge` if it ever needs the builder's own data shapes, not
the other way around.

Custody is store-held and named honestly, not implied to be stronger than it
is (see the design doc's D4 "Key custody" section): a signature here proves
the *store* attested a manifest, not that a builder held a private key
independent of the store. Real custody should be the Fernet-keyed vault from
docs/design/safe-app-installer.md D7 — that vault isn't implemented in this
repo yet, so `KeyStore` is a Protocol with a filesystem-backed reference
implementation that says loudly it is NOT that vault, rather than quietly
pretending to be production-grade custody.

Static Ed25519 signing (the `cryptography` package — see stores/requirements.txt,
the one deliberate exception to this directory's stdlib-only convention),
format-equivalent to what cosign's `--key` static mode does, without shelling
out to cosign or depending on Fulcio/Rekor — matching the "static-keypair
mode, no new infrastructure" call in the design doc's Adopted dependencies.
Literal cosign/sigstore-python integration is a follow-on, not required to
make "signed -> allowed, tampered -> denied" real today.

Rotate vs. compromise (the gap the design doc's second review found and this
module exists to close): both are ledger EVENTS, not a separately-editable
state file — the same principal that holds the signing keys would otherwise
also hold the state used to judge whether a compromise happened, which is no
protection at all. `SigningLedger` derives key state from its own
tamper-evident event log, and its "externally-pinned tip" — `head()` /
`verify(expect_head=...)` — is what makes a store/vault compromise
detectable rather than silently rewriting its own history. Pin the head
somewhere this module's own compromise can't reach (an operator, a CI
artifact, `nestor.frank`-style mirroring) — that pinning is a practice this
module makes possible, not something code alone can force.

Usage:
    python stores/sap_gate.py keygen <builder_id>
    python stores/sap_gate.py sign <builder_id> <manifest.json> [--out signed.json]
    python stores/sap_gate.py verify <signed_manifest.json>
    python stores/sap_gate.py rotate <builder_id>
    python stores/sap_gate.py compromise <builder_id> --reason "..."
    python stores/sap_gate.py ledger-head
    python stores/sap_gate.py ledger-verify [--expect-head SHA]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

DEFAULT_KEY_ROOT = Path(__file__).resolve().parent / ".sap_gate_keys"
DEFAULT_LEDGER_PATH = Path(__file__).resolve().parent / ".sap_gate_ledger.jsonl"

# Same charset D11 requires for builder_id as a filesystem path component
# (promote_check.py's _APP_ID_PATTERN) — builder_id lands directly in a
# filename here, so this is not optional hygiene.
_BUILDER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

MANIFEST_BOUND_FIELDS = ("app_id", "permissions", "store_scope", "maker")


class GateError(Exception):
    """Fail-closed refusal — unsigned, tampered, unknown key, or a signature
    made after that key's recorded compromise. Every refusal in this module
    raises this; nothing here returns a bool a caller could forget to check."""


def _check_builder_id(builder_id: str) -> str:
    if not builder_id or not _BUILDER_ID_PATTERN.match(builder_id):
        raise GateError(f"builder_id {builder_id!r} fails the path-safety charset (D11)")
    return builder_id


def canonical_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    """The exact bytes a signature covers — only the fields D4 binds
    (app_id, permissions, store_scope, maker), sorted keys, no whitespace
    ambiguity. Any other manifest field is not part of what's signed."""
    bound = {k: manifest.get(k) for k in MANIFEST_BOUND_FIELDS}
    return json.dumps(bound, sort_keys=True, separators=(",", ":")).encode("utf-8")


# ── custody ──────────────────────────────────────────────────────────────────

class KeyStore(Protocol):
    """Where signing keys live. `get_or_create`/`public_key` are the whole
    surface — rotate/compromise state is NOT part of this Protocol, because
    it lives in the ledger (see module docstring), not in custody."""

    def get_or_create(self, builder_id: str) -> Ed25519PrivateKey: ...
    def public_key(self, builder_id: str) -> Ed25519PublicKey: ...


class FilesystemKeyStore:
    """DEV-ONLY reference implementation. Private keys are written to disk
    unencrypted under `root`, 0600. This is NOT the D7 vault — it exists so
    this module has something real to run and be tested against before that
    integration lands, and it says so loudly rather than pretending to be
    production custody."""

    def __init__(self, root: Path = DEFAULT_KEY_ROOT):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _key_path(self, builder_id: str) -> Path:
        return self.root / f"{_check_builder_id(builder_id)}.ed25519.pem"

    def get_or_create(self, builder_id: str) -> Ed25519PrivateKey:
        path = self._key_path(builder_id)
        if path.exists():
            return serialization.load_pem_private_key(path.read_bytes(), password=None)
        key = Ed25519PrivateKey.generate()
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        path.write_bytes(pem)
        path.chmod(0o600)
        return key

    def public_key(self, builder_id: str) -> Ed25519PublicKey:
        """Strict lookup — does NOT create a key. `verify_manifest` calls
        this for a `builder_id` it doesn't control (the claim comes off the
        thing being verified); auto-creating on lookup meant verifying a
        manifest for an unknown builder_id minted a real private key as a
        side effect of checking it, and let anyone seed key files on disk
        just by submitting a signed-manifest claim for a name that had
        never signed anything. `sign_manifest` still calls `get_or_create`
        directly — creation only ever happens on the signing path, which
        the caller actually controls."""
        path = self._key_path(builder_id)
        if not path.exists():
            raise GateError(f"no key exists for builder_id={builder_id!r}")
        return serialization.load_pem_private_key(path.read_bytes(), password=None).public_key()


# ── the signing-event ledger — tamper-evident, its own instance (D10) ────────

class SigningLedger:
    """Append-only, hash-chained signing-event log — its OWN instance, not
    D12/Nestor's pedagogy ledger (D10 keeps them distinct). Modeled on
    Nestor's ledger.py: `prev = sha256(previous raw line)`, refuses a
    symlinked or non-regular-file path, refuses to extend a chain that
    doesn't already verify.

    Key state (active / rotated / compromised) is DERIVED from this log, not
    stored separately — the same principal holding the signing keys would
    otherwise also hold a freely-editable state file, which is no protection
    against exactly the compromise this exists to detect.
    """

    def __init__(self, path: Path = DEFAULT_LEDGER_PATH):
        if path.is_symlink():
            raise GateError(f"refusing to use a symlinked ledger path: {path}")
        self.path = path
        self._verified_once = False

    def _raw_lines(self) -> list[str]:
        if not self.path.exists():
            return []
        if not self.path.is_file():
            raise GateError(f"ledger path exists and is not a regular file: {self.path}")
        return [line for line in self.path.read_text().splitlines() if line.strip()]

    def _parse_line(self, line: str, index: int) -> dict[str, Any]:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as e:
            raise GateError(f"ledger is corrupt: entry {index} is not valid JSON: {e}") from e
        for required in ("prev", "builder_id", "event", "timestamp"):
            if required not in entry:
                raise GateError(f"ledger is corrupt: entry {index} is missing {required!r}")
        return entry

    def _entries(self) -> list[dict[str, Any]]:
        return [self._parse_line(line, i) for i, line in enumerate(self._raw_lines())]

    def head(self) -> str | None:
        raw = self._raw_lines()
        return hashlib.sha256(raw[-1].encode()).hexdigest() if raw else None

    def verify(self, *, expect_head: str | None = None) -> tuple[bool, str]:
        raw = self._raw_lines()
        prev_hash: str | None = None
        for i, line in enumerate(raw):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                return False, f"entry {i} is not valid JSON"
            if entry.get("prev") != prev_hash:
                return False, f"chain broken at entry {i}"
            prev_hash = hashlib.sha256(line.encode()).hexdigest()
        if not raw:
            return True, "empty — nothing to verify"
        if expect_head is not None and prev_hash != expect_head:
            return False, f"head mismatch: computed {prev_hash} != expected {expect_head}"
        return True, f"intact — {len(raw)} entries"

    def append(self, *, builder_id: str, event: str, manifest_hash: str | None = None,
               timestamp: float | None = None, reason: str | None = None) -> None:
        if not self._verified_once:
            ok, msg = self.verify()
            if not ok:
                raise GateError(f"refusing to extend a broken ledger: {msg}")
            self._verified_once = True
        raw = self._raw_lines()
        prev_hash = hashlib.sha256(raw[-1].encode()).hexdigest() if raw else None
        entry = {
            "prev": prev_hash,
            "builder_id": _check_builder_id(builder_id),
            "event": event,
            "manifest_hash": manifest_hash,
            "timestamp": timestamp if timestamp is not None else time.time(),
            "reason": reason,
        }
        with self.path.open("a") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")

    def has_sign_entry(self, *, builder_id: str, manifest_hash: str, timestamp: float) -> bool:
        return any(
            e["event"] == "sign" and e["builder_id"] == builder_id
            and e.get("manifest_hash") == manifest_hash and e["timestamp"] == timestamp
            for e in self._entries()
        )

    def compromised_at(self, builder_id: str) -> float | None:
        """The timestamp of the LAST compromise event for this builder_id,
        or None if it's never been marked compromised. A later `rotate`
        does not clear a compromise — rotation retires a key going forward;
        it does not un-happen a compromise of the key being retired."""
        at = None
        for e in self._entries():
            if e["builder_id"] == builder_id and e["event"] == "compromise":
                at = e["timestamp"]
        return at


# ── sign / verify ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SignedManifest:
    manifest: dict[str, Any]
    builder_id: str
    signature: str  # hex
    signed_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest": self.manifest,
            "builder_id": self.builder_id,
            "signature": self.signature,
            "signed_at": self.signed_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SignedManifest":
        return cls(manifest=d["manifest"], builder_id=d["builder_id"],
                    signature=d["signature"], signed_at=d["signed_at"])


def sign_manifest(manifest: dict[str, Any], *, builder_id: str, keystore: KeyStore,
                   ledger: SigningLedger) -> SignedManifest:
    _check_builder_id(builder_id)
    for field_name in MANIFEST_BOUND_FIELDS:
        if field_name not in manifest:
            raise GateError(f"manifest missing bound field {field_name!r} — refusing to sign")
    if manifest.get("maker") != builder_id:
        raise GateError(
            f"manifest 'maker' ({manifest.get('maker')!r}) does not match "
            f"signing builder_id ({builder_id!r}) — refusing to sign"
        )
    if ledger.compromised_at(builder_id) is not None:
        raise GateError(f"builder_id={builder_id!r} key is compromised — refusing to sign")

    key = keystore.get_or_create(builder_id)
    payload = canonical_manifest_bytes(manifest)
    signature = key.sign(payload)
    signed_at = time.time()
    manifest_hash = hashlib.sha256(payload).hexdigest()
    ledger.append(builder_id=builder_id, event="sign", manifest_hash=manifest_hash, timestamp=signed_at)
    return SignedManifest(manifest=manifest, builder_id=builder_id,
                           signature=signature.hex(), signed_at=signed_at)


def verify_manifest(signed: SignedManifest, *, keystore: KeyStore, ledger: SigningLedger,
                     expect_ledger_head: str | None = None) -> None:
    """Fail-closed. Raises GateError on any problem. Returns None on
    success, on purpose — a caller can't mistake a forgotten bool check for
    "verified".

    `expect_ledger_head` is the externally-pinned tip the module docstring
    describes — pass it when the caller holds one (an operator, a CI
    artifact) to catch a rewritten ledger even if the rewrite kept the
    internal chain self-consistent from entry 0. Without it, this still
    checks the chain is internally intact (see below) — just not against
    anything outside the ledger file itself.
    """
    try:
        pub = keystore.public_key(signed.builder_id)
    except Exception as e:
        raise GateError(f"no known key for builder_id={signed.builder_id!r}: {e}") from e

    payload = canonical_manifest_bytes(signed.manifest)
    try:
        pub.verify(bytes.fromhex(signed.signature), payload)
    except InvalidSignature:
        raise GateError("signature does not verify — tampered manifest or wrong key") from None
    except (ValueError, TypeError) as e:
        raise GateError(f"malformed signature: {e}") from None

    # The ledger's own tamper-evidence is worthless if the decision that
    # depends on it never actually checks the chain — a corrupted or
    # rewritten ledger must deny, not just fail to find what it's looking
    # for. This was found missing entirely in the 2026-08-01 audit: nothing
    # here called ledger.verify() before trusting has_sign_entry()/
    # compromised_at()'s answers.
    ok, msg = ledger.verify(expect_head=expect_ledger_head)
    if not ok:
        raise GateError(f"ledger does not verify, refusing to trust its answer: {msg}")

    manifest_hash = hashlib.sha256(payload).hexdigest()
    if not ledger.has_sign_entry(builder_id=signed.builder_id, manifest_hash=manifest_hash,
                                  timestamp=signed.signed_at):
        raise GateError("no matching signing-event ledger entry — signature is not attested")

    compromised_at = ledger.compromised_at(signed.builder_id)
    if compromised_at is not None and signed.signed_at >= compromised_at:
        raise GateError(
            f"builder_id={signed.builder_id!r} key was compromised at {compromised_at} "
            f"— this signature (signed_at={signed.signed_at}) is after that and is not trusted"
        )


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cmd_keygen(args: argparse.Namespace) -> int:
    ks = FilesystemKeyStore(Path(args.key_root))
    ks.get_or_create(args.builder_id)
    print(f"key ready for builder_id={args.builder_id!r} under {args.key_root}")
    return 0


def _cmd_sign(args: argparse.Namespace) -> int:
    ks = FilesystemKeyStore(Path(args.key_root))
    ledger = SigningLedger(Path(args.ledger))
    manifest = json.loads(Path(args.manifest_file).read_text())
    try:
        signed = sign_manifest(manifest, builder_id=args.builder_id, keystore=ks, ledger=ledger)
    except GateError as e:
        print(f"sign refused: {e}", file=sys.stderr)
        return 1
    out = json.dumps(signed.to_dict(), indent=2)
    if args.out:
        Path(args.out).write_text(out)
    print(out)
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    ks = FilesystemKeyStore(Path(args.key_root))
    ledger = SigningLedger(Path(args.ledger))
    signed = SignedManifest.from_dict(json.loads(Path(args.signed_file).read_text()))
    try:
        verify_manifest(signed, keystore=ks, ledger=ledger, expect_ledger_head=args.expect_ledger_head)
    except GateError as e:
        print(f"DENIED: {e}", file=sys.stderr)
        return 1
    print("ALLOWED: signature verifies, ledger intact and attested, key not compromised at signing time")
    return 0


def _cmd_rotate(args: argparse.Namespace) -> int:
    ledger = SigningLedger(Path(args.ledger))
    ledger.append(builder_id=args.builder_id, event="rotate", reason=args.reason)
    print(f"rotated: builder_id={args.builder_id!r} (past signatures remain trusted)")
    return 0


def _cmd_compromise(args: argparse.Namespace) -> int:
    ledger = SigningLedger(Path(args.ledger))
    ledger.append(builder_id=args.builder_id, event="compromise", reason=args.reason)
    print(f"compromised: builder_id={args.builder_id!r} — signatures from now on are untrusted")
    return 0


def _cmd_ledger_head(args: argparse.Namespace) -> int:
    ledger = SigningLedger(Path(args.ledger))
    head = ledger.head()
    print(head if head else "(empty ledger)")
    return 0


def _cmd_ledger_verify(args: argparse.Namespace) -> int:
    ledger = SigningLedger(Path(args.ledger))
    ok, msg = ledger.verify(expect_head=args.expect_head)
    print(msg)
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sap_gate.py")
    p.add_argument("--key-root", default=str(DEFAULT_KEY_ROOT))
    p.add_argument("--ledger", default=str(DEFAULT_LEDGER_PATH))
    sub = p.add_subparsers(dest="command", required=True)

    kg = sub.add_parser("keygen"); kg.add_argument("builder_id"); kg.set_defaults(func=_cmd_keygen)

    sg = sub.add_parser("sign")
    sg.add_argument("builder_id"); sg.add_argument("manifest_file")
    sg.add_argument("--out"); sg.set_defaults(func=_cmd_sign)

    vf = sub.add_parser("verify")
    vf.add_argument("signed_file")
    vf.add_argument("--expect-ledger-head", default=None)
    vf.set_defaults(func=_cmd_verify)

    rt = sub.add_parser("rotate")
    rt.add_argument("builder_id"); rt.add_argument("--reason"); rt.set_defaults(func=_cmd_rotate)

    cp = sub.add_parser("compromise")
    cp.add_argument("builder_id"); cp.add_argument("--reason"); cp.set_defaults(func=_cmd_compromise)

    sub.add_parser("ledger-head").set_defaults(func=_cmd_ledger_head)

    lv = sub.add_parser("ledger-verify")
    lv.add_argument("--expect-head"); lv.set_defaults(func=_cmd_ledger_verify)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
