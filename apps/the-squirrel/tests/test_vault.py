"""
Vault tests — the Squirrel's box, per the willow-data-vault blueprint.

Invariants pinned:
  - provision() stands up a 0700 box with 0600 vault.db + vault.key
  - write/read round-trips through Fernet
  - vault.db without vault.key is a hard stop, not a re-init
  - the ciphertext is unreadable under a different key
  - the gate resolves its operator PGP fingerprint env-first, then vault
"""
import os
import sqlite3
import stat

import pytest

from sap.core import vault


def _mode(p):
    return stat.S_IMODE(os.stat(p).st_mode)


def test_provision_stands_up_the_box(tmp_path):
    box = vault.provision(tmp_path / "box")
    assert _mode(box) == 0o700
    assert (box / "willowgate").is_dir()
    assert _mode(box / "vault.db") == 0o600
    assert _mode(box / "vault.key") == 0o600


def test_provision_is_idempotent(tmp_path):
    box = vault.provision(tmp_path / "box")
    key_before = (box / "vault.key").read_bytes()
    vault.provision(box)
    assert (box / "vault.key").read_bytes() == key_before  # never regenerated


def test_write_read_roundtrip(tmp_path):
    v = vault.Vault(tmp_path / "vault.db", tmp_path / "vault.key")
    v.init()
    v.write("willowgate_key_fpr", "ABCDEF0123456789")
    assert v.read("willowgate_key_fpr") == "ABCDEF0123456789"
    assert v.has("willowgate_key_fpr")
    assert v.list_keys() == ["willowgate_key_fpr"]
    assert v.delete("willowgate_key_fpr")
    assert v.read("willowgate_key_fpr") is None


def test_value_is_ciphertext_on_disk(tmp_path):
    v = vault.Vault(tmp_path / "vault.db", tmp_path / "vault.key")
    v.init()
    v.write("name", "oscar-mann-secret")
    raw = sqlite3.connect(str(tmp_path / "vault.db")).execute(
        "SELECT value FROM secrets").fetchone()[0]
    assert b"oscar-mann-secret" not in raw


def test_db_without_key_is_a_hard_stop(monkeypatch, tmp_path):
    monkeypatch.setenv("SQUIRREL_HOME", str(tmp_path))
    vault.default_vault()  # creates both
    (tmp_path / "vault.key").unlink()
    with pytest.raises(FileNotFoundError):
        vault.default_vault()
    # and the best-effort reader refuses too — damage, not absence
    with pytest.raises(FileNotFoundError):
        vault.read_secret("anything")


def test_wrong_key_cannot_decrypt(tmp_path):
    from cryptography.fernet import Fernet, InvalidToken
    v = vault.Vault(tmp_path / "vault.db", tmp_path / "vault.key")
    v.init()
    v.write("name", "value")
    (tmp_path / "vault.key").write_bytes(Fernet.generate_key())
    stolen = vault.Vault(tmp_path / "vault.db", tmp_path / "vault.key")
    with pytest.raises(InvalidToken):
        stolen.read("name")


def test_read_secret_absent_paths_return_none(monkeypatch, tmp_path):
    monkeypatch.setenv("SQUIRREL_HOME", str(tmp_path / "nothing-here"))
    assert vault.read_secret("willowgate_key_fpr") is None  # no vault at all
    monkeypatch.setenv("SQUIRREL_HOME", str(tmp_path / "box"))
    vault.default_vault()
    assert vault.read_secret("willowgate_key_fpr") is None  # vault, no secret


def test_gate_resolves_fpr_env_first_then_vault(monkeypatch, tmp_path):
    import sap.core.gate as gate
    monkeypatch.setenv("SQUIRREL_HOME", str(tmp_path / "box"))
    monkeypatch.delenv("WILLOWGATE_KEY_FPR", raising=False)
    assert gate._operator_key_fpr() == ""            # nothing anywhere
    vault.default_vault().write("willowgate_key_fpr", "FADED0123456789")
    assert gate._operator_key_fpr() == "FADED0123456789"   # vault speaks
    monkeypatch.setenv("WILLOWGATE_KEY_FPR", "ENV0VERRIDE")
    assert gate._operator_key_fpr() == "ENV0VERRIDE"       # env wins
