"""The `witnessed [M]` gate's SEAL tier — real cryptographic verification.

Skips unless the cloud seam is installed (forge.trust + willow-gate + nestor),
because these drive the actual two-tier flow the seam implements:

    enroll  — the author provisionally seals the promotion THROUGH the gate,
              under its own identity, into a hash-chained custody ledger;
    ratify  — a DIFFERENT hand (the verifier's ed25519 key) checkpoints the
              chain head;
    witness — promote_check resolves the verifier's PUBLIC key from the fleet
              keyring by name and demands forge.trust.witnessed() pass.

The point being proved: with a `trust` block, `verified_by` is no longer a
string. A valid seal passes; a tampered ledger, an unknown verifier, a missing
author seal, and a missing keyring each FAIL closed — none falls back to the
name check.
"""
import importlib.util
import json
import os
from pathlib import Path

import pytest

pytest.importorskip("willow_gate")
pytest.importorskip("forge.trust")
pytest.importorskip("nestor.keyring")

from willow_gate import WillowGate
from willow_gate.custody import CustodyLedger
from forge.trust import enroll, ratify
from nestor import keyring as keyring_mod
from nestor.signing import _sign_with

_REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("promote_check", _REPO / "stores" / "promote_check.py")
promote_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(promote_check)

AUTHOR_ID = "agent:vishwakarma"
VERIFIER = "loki"


class _EdSigner:
    """The verifier's home key — signs the ratifying checkpoint with the ed25519
    PRIVATE half. promote_check verifies with the PUBLIC half from the keyring."""
    def __init__(self, private: bytes):
        self._private = private

    def sign(self, data: bytes) -> str:
        return _sign_with("ed25519", self._private, data)


def _fresh_keyring_env(tmp_path, monkeypatch, *, verifier=VERIFIER):
    """Install a keyring with one ed25519 verifier and point NESTOR_KEYRING at it.
    Returns the verifier's private key (for ratifying). Resets the module cache so
    each test's unique path is actually re-read."""
    ring = keyring_mod.Keyring()
    entry = ring.add(verifier, kind="ed25519")
    kpath = tmp_path / "keyring.json"
    ring.save(str(kpath))
    monkeypatch.setenv("NESTOR_KEYRING", str(kpath))
    # get_keyring() caches by path; a fresh tmp path re-reads, but clear the
    # injected/global cache defensively so tests never bleed into each other.
    keyring_mod.set_keyring(None)
    keyring_mod._from_env = None
    keyring_mod._loaded_from = None
    return entry.private


def _seal_candidate(tmp_path, private, *, app_id="widget", seal_app=None,
                    author_id=AUTHOR_ID, verifier=VERIFIER):
    """Build a candidate dir carrying a real provisional seal + ratifying
    checkpoint. `seal_app` (default app_id) is the app the author actually sealed
    — set it different from app_id to model 'no seal for THIS promotion'."""
    cand = tmp_path / app_id
    trust_dir = cand / "trust"
    trust_dir.mkdir(parents=True)

    gate = WillowGate(base_dir=str(tmp_path / "gate"), require_pgp=False)
    secret = os.urandom(32)
    gate.register_agent(author_id, secret, max_trust=2)

    led = CustodyLedger(path=str(trust_dir / "custody.jsonl"))
    promotion = {"app_id": seal_app or app_id, "author": "vishwakarma",
                 "verified_by": verifier, "repo_url": "https://github.com/x/widget"}
    enroll(gate, author_id, secret, custody=led, promotion=promotion, trust_level=1)
    cp = ratify(led, _EdSigner(private))
    (trust_dir / "checkpoint.json").write_text(json.dumps(cp))

    (cand / "promotion.json").write_text(json.dumps({
        "app_id": app_id, "author": "vishwakarma", "verified_by": verifier,
        "trust": {"custody": "trust/custody.jsonl", "checkpoint": "trust/checkpoint.json",
                  "author_id": author_id, "verifier_id": verifier},
    }))
    return cand


def _run(cand):
    att = json.loads((cand / "promotion.json").read_text())
    return promote_check._witnessed(cand, att)


def test_valid_seal_passes(tmp_path, monkeypatch):
    priv = _fresh_keyring_env(tmp_path, monkeypatch)
    cand = _seal_candidate(tmp_path, priv)
    gate, ok, detail = _run(cand)
    assert gate == "witnessed [M]" and ok is True, detail
    assert detail.startswith("sealed:")


def test_unknown_verifier_denied(tmp_path, monkeypatch):
    # keyring holds 'someone_else', but the promotion is verified_by 'loki'
    priv = _fresh_keyring_env(tmp_path, monkeypatch, verifier="someone_else")
    cand = _seal_candidate(tmp_path, priv)  # sealed/ratified as loki
    _, ok, detail = _run(cand)
    assert ok is False and "not trusted in the keyring" in detail


def test_no_keyring_configured_denied(tmp_path, monkeypatch):
    priv = _fresh_keyring_env(tmp_path, monkeypatch)
    cand = _seal_candidate(tmp_path, priv)
    monkeypatch.delenv("NESTOR_KEYRING", raising=False)
    keyring_mod.set_keyring(None)
    keyring_mod._from_env = None
    keyring_mod._loaded_from = None
    _, ok, detail = _run(cand)
    assert ok is False and "no fleet keyring" in detail


def test_tampered_custody_denied(tmp_path, monkeypatch):
    priv = _fresh_keyring_env(tmp_path, monkeypatch)
    cand = _seal_candidate(tmp_path, priv)
    led = cand / "trust" / "custody.jsonl"
    lines = led.read_text().splitlines()
    # flip a field in the first event — the hash chain no longer verifies on load
    first = json.loads(lines[0])
    first["actor"] = "agent:someone-else"
    lines[0] = json.dumps(first)
    led.write_text("\n".join(lines) + "\n")
    _, ok, detail = _run(cand)
    assert ok is False and "failed to load/verify" in detail


def test_no_provisional_seal_for_this_promotion_denied(tmp_path, monkeypatch):
    # the author sealed 'other-app', but the promotion is for 'widget'
    priv = _fresh_keyring_env(tmp_path, monkeypatch)
    cand = _seal_candidate(tmp_path, priv, app_id="widget", seal_app="other-app")
    _, ok, detail = _run(cand)
    assert ok is False and "seal rejected" in detail
