"""Tests for stores/sap_gate.py — the signed-manifest gate (D4).

Same loading pattern as tests/test_promote_check_record.py: load the module
directly from stores/, no package install. Every test builds its own
key-store/ledger under tmp_path — nothing here ever touches the real
stores/.sap_gate_keys or stores/.sap_gate_ledger.jsonl.
"""
import importlib.util
import sys
import time
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("sap_gate", _REPO / "stores" / "sap_gate.py")
sap_gate = importlib.util.module_from_spec(_spec)
# dataclasses' own typing introspection looks the module up in sys.modules
# while exec_module is still running - it has to be registered first.
sys.modules["sap_gate"] = sap_gate
_spec.loader.exec_module(sap_gate)


def _manifest(**overrides):
    m = {
        "app_id": "widget",
        "permissions": ["file_write"],
        "store_scope": ["widget_*"],
        "maker": "alice",
    }
    m.update(overrides)
    return m


def _gate(tmp_path):
    ks = sap_gate.FilesystemKeyStore(tmp_path / "keys")
    ledger = sap_gate.SigningLedger(tmp_path / "ledger.jsonl")
    return ks, ledger


# ── sign / verify ─────────────────────────────────────────────────────────────

def test_sign_then_verify_round_trips(tmp_path):
    ks, ledger = _gate(tmp_path)
    signed = sap_gate.sign_manifest(_manifest(), builder_id="alice", keystore=ks, ledger=ledger)
    sap_gate.verify_manifest(signed, keystore=ks, ledger=ledger)  # no raise = allowed


def test_tampered_manifest_after_signing_is_denied(tmp_path):
    ks, ledger = _gate(tmp_path)
    signed = sap_gate.sign_manifest(_manifest(), builder_id="alice", keystore=ks, ledger=ledger)
    tampered = sap_gate.SignedManifest(
        manifest=_manifest(permissions=["file_write", "network_read"]),  # widened after signing
        builder_id=signed.builder_id, signature=signed.signature, signed_at=signed.signed_at,
    )
    with pytest.raises(sap_gate.GateError, match="does not verify"):
        sap_gate.verify_manifest(tampered, keystore=ks, ledger=ledger)


def test_unknown_builder_id_is_denied(tmp_path):
    ks, ledger = _gate(tmp_path)
    signed = sap_gate.sign_manifest(_manifest(), builder_id="alice", keystore=ks, ledger=ledger)
    forged = sap_gate.SignedManifest(
        manifest=signed.manifest, builder_id="mallory",
        signature=signed.signature, signed_at=signed.signed_at,
    )
    with pytest.raises(sap_gate.GateError):
        sap_gate.verify_manifest(forged, keystore=ks, ledger=ledger)


def test_signature_from_a_different_builders_key_is_denied(tmp_path):
    ks, ledger = _gate(tmp_path)
    signed = sap_gate.sign_manifest(_manifest(), builder_id="alice", keystore=ks, ledger=ledger)
    # bob has a real key too — his signature must not verify against alice's manifest
    ks.get_or_create("bob")
    forged = sap_gate.SignedManifest(
        manifest=signed.manifest, builder_id="bob",
        signature=signed.signature, signed_at=signed.signed_at,
    )
    with pytest.raises(sap_gate.GateError, match="does not verify"):
        sap_gate.verify_manifest(forged, keystore=ks, ledger=ledger)


def test_manifest_missing_bound_field_is_refused_at_sign_time(tmp_path):
    ks, ledger = _gate(tmp_path)
    incomplete = {"app_id": "widget", "maker": "alice"}  # no permissions/store_scope
    with pytest.raises(sap_gate.GateError, match="missing bound field"):
        sap_gate.sign_manifest(incomplete, builder_id="alice", keystore=ks, ledger=ledger)


def test_maker_mismatch_is_refused_at_sign_time(tmp_path):
    ks, ledger = _gate(tmp_path)
    with pytest.raises(sap_gate.GateError, match="does not match"):
        sap_gate.sign_manifest(_manifest(maker="bob"), builder_id="alice", keystore=ks, ledger=ledger)


def test_signature_with_no_ledger_entry_is_denied(tmp_path):
    ks, ledger = _gate(tmp_path)
    signed = sap_gate.sign_manifest(_manifest(), builder_id="alice", keystore=ks, ledger=ledger)
    # a signature claiming a signed_at that was never actually ledgered
    replayed = sap_gate.SignedManifest(
        manifest=signed.manifest, builder_id=signed.builder_id,
        signature=signed.signature, signed_at=signed.signed_at + 1,
    )
    with pytest.raises(sap_gate.GateError, match="not attested"):
        sap_gate.verify_manifest(replayed, keystore=ks, ledger=ledger)


# ── path-safety (D11's charset, reused here since builder_id is a filename) ──

@pytest.mark.parametrize("bad_id", ["../../etc/passwd", "", "a b", "a/b"])
def test_bad_builder_id_is_refused(tmp_path, bad_id):
    ks, ledger = _gate(tmp_path)
    with pytest.raises(sap_gate.GateError):
        sap_gate.sign_manifest(_manifest(maker=bad_id), builder_id=bad_id, keystore=ks, ledger=ledger)


# ── rotate / compromise — the actual fix the second review asked for ─────────

def test_rotate_keeps_past_signatures_trusted(tmp_path):
    ks, ledger = _gate(tmp_path)
    signed = sap_gate.sign_manifest(_manifest(), builder_id="alice", keystore=ks, ledger=ledger)
    ledger.append(builder_id="alice", event="rotate", reason="routine hygiene")
    sap_gate.verify_manifest(signed, keystore=ks, ledger=ledger)  # still allowed


def test_compromise_denies_signing_going_forward(tmp_path):
    ks, ledger = _gate(tmp_path)
    ledger.append(builder_id="alice", event="compromise", reason="vault breach")
    with pytest.raises(sap_gate.GateError, match="compromised"):
        sap_gate.sign_manifest(_manifest(), builder_id="alice", keystore=ks, ledger=ledger)


def test_backdated_compromise_denies_a_real_ledgered_signature(tmp_path):
    """Exercises the timing-comparison branch specifically, not masked by
    the ledger-attestation check: this signature IS in the ledger for real —
    it's denied because the compromise timestamp precedes it, not because
    it's unattested."""
    ks, ledger = _gate(tmp_path)
    signed = sap_gate.sign_manifest(_manifest(), builder_id="alice", keystore=ks, ledger=ledger)
    ledger.append(builder_id="alice", event="compromise", reason="backdated",
                   timestamp=signed.signed_at - 1)
    with pytest.raises(sap_gate.GateError, match="is not trusted"):
        sap_gate.verify_manifest(signed, keystore=ks, ledger=ledger)


def test_compromise_denies_verification_of_signatures_made_after_it(tmp_path):
    ks, ledger = _gate(tmp_path)
    signed_before = sap_gate.sign_manifest(_manifest(), builder_id="alice", keystore=ks, ledger=ledger)
    sap_gate.verify_manifest(signed_before, keystore=ks, ledger=ledger)  # fine, pre-compromise

    ledger.append(builder_id="alice", event="compromise", reason="vault breach",
                   timestamp=signed_before.signed_at + 100)

    # verifying the SAME pre-compromise signature must still succeed —
    # compromise is not retroactive against signatures that predate it
    sap_gate.verify_manifest(signed_before, keystore=ks, ledger=ledger)

    # a signature stamped as having happened AFTER the compromise timestamp
    # is denied even if the crypto itself is valid, e.g. a forged ledger
    # entry or clock skew a store compromise could exploit
    forged_after = sap_gate.SignedManifest(
        manifest=signed_before.manifest, builder_id="alice",
        signature=signed_before.signature, signed_at=signed_before.signed_at + 200,
    )
    with pytest.raises(sap_gate.GateError, match="not attested"):
        # (also fails the ledger-attestation check first, since nothing was
        # ever signed at signed_at+200 — belt and suspenders, both refuse)
        sap_gate.verify_manifest(forged_after, keystore=ks, ledger=ledger)


# ── the ledger itself: tamper-evidence and fail-closed extension ─────────────

def test_ledger_verify_on_empty_ledger(tmp_path):
    ledger = sap_gate.SigningLedger(tmp_path / "ledger.jsonl")
    ok, msg = ledger.verify()
    assert ok
    assert "empty" in msg


def _corrupt_first_entry(ledger_path):
    """Flip a character in entry 0's manifest_hash and rewrite the line —
    entry 0's own content isn't literally readable text (only its hash is
    stored), so this is the actual way to simulate a rewritten history,
    not a text substitution against content that was never in the line."""
    import json as _json

    lines = ledger_path.read_text().splitlines()
    entry = _json.loads(lines[0])
    h = entry["manifest_hash"]
    entry["manifest_hash"] = ("0" if h[0] != "0" else "1") + h[1:]
    lines[0] = _json.dumps(entry, sort_keys=True)
    ledger_path.write_text("\n".join(lines) + "\n")


def test_ledger_detects_a_rewritten_entry(tmp_path):
    ks, ledger = _gate(tmp_path)
    sap_gate.sign_manifest(_manifest(), builder_id="alice", keystore=ks, ledger=ledger)
    sap_gate.sign_manifest(_manifest(app_id="other"), builder_id="alice", keystore=ks, ledger=ledger)

    ok, _ = ledger.verify()
    assert ok

    _corrupt_first_entry(ledger.path)  # simulate the store rewriting its own history

    ok, msg = ledger.verify()
    assert not ok
    assert "broken" in msg


def test_append_refuses_to_extend_an_already_broken_chain(tmp_path):
    ks, ledger = _gate(tmp_path)
    # a lone entry's own corruption is invisible to the walk (nothing points
    # back at it yet — the same "newest entry is unverifiable" property
    # Nestor's own ledger has); need a second entry for the first one's
    # corruption to actually break something the walk can see.
    sap_gate.sign_manifest(_manifest(), builder_id="alice", keystore=ks, ledger=ledger)
    sap_gate.sign_manifest(_manifest(app_id="other"), builder_id="alice", keystore=ks, ledger=ledger)
    _corrupt_first_entry(ledger.path)

    fresh_ledger = sap_gate.SigningLedger(ledger.path)  # unverified in this process yet
    with pytest.raises(sap_gate.GateError, match="broken ledger"):
        fresh_ledger.append(builder_id="alice", event="rotate")


def test_ledger_refuses_a_symlinked_path(tmp_path):
    real = tmp_path / "real.jsonl"
    real.write_text("")
    link = tmp_path / "link.jsonl"
    link.symlink_to(real)
    with pytest.raises(sap_gate.GateError, match="symlink"):
        sap_gate.SigningLedger(link)


def test_ledger_head_and_expect_head(tmp_path):
    ks, ledger = _gate(tmp_path)
    assert ledger.head() is None
    sap_gate.sign_manifest(_manifest(), builder_id="alice", keystore=ks, ledger=ledger)
    head = ledger.head()
    assert head is not None

    ok, _ = ledger.verify(expect_head=head)
    assert ok

    ok, msg = ledger.verify(expect_head="0" * 64)
    assert not ok
    assert "mismatch" in msg


# ── canonical bytes — only the bound fields are covered ──────────────────────

def test_canonical_bytes_ignore_unbound_fields():
    a = sap_gate.canonical_manifest_bytes(_manifest(version="1.0.0"))
    b = sap_gate.canonical_manifest_bytes(_manifest(version="9.9.9"))
    assert a == b  # version isn't a D4-bound field, so it can't change the signature
