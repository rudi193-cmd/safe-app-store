"""Tests for the shared vault_paths resolver (box audit A5)."""
from pathlib import Path

import vault_paths as vp


# ── vault_root ──────────────────────────────────────────────────────────────

def test_vault_root_defaults_under_home(monkeypatch):
    monkeypatch.delenv("WILLOW_STORE_ROOT", raising=False)
    assert vp.vault_root() == Path.home() / ".willow" / "store"


def test_vault_root_honors_env_override(monkeypatch):
    monkeypatch.setenv("WILLOW_STORE_ROOT", "/data/vault")
    assert vp.vault_root() == Path("/data/vault")


def test_vault_root_expands_user(monkeypatch):
    monkeypatch.setenv("WILLOW_STORE_ROOT", "~/mybox")
    assert vp.vault_root() == Path.home() / "mybox"


# ── app_dir ─────────────────────────────────────────────────────────────────

def test_app_dir_is_under_the_vault(monkeypatch):
    monkeypatch.setenv("WILLOW_STORE_ROOT", "/data/vault")
    monkeypatch.delenv("APP_DATA", raising=False)
    assert vp.app_dir("civics-check") == Path("/data/vault/civics-check")


def test_app_dir_env_override_wins(monkeypatch):
    monkeypatch.setenv("WILLOW_STORE_ROOT", "/data/vault")
    monkeypatch.setenv("APP_DATA", "/legacy/civics")
    assert vp.app_dir("civics-check") == Path("/legacy/civics")


def test_app_dir_custom_env_var(monkeypatch):
    monkeypatch.setenv("WILLOW_STORE_ROOT", "/data/vault")
    monkeypatch.delenv("APP_DATA", raising=False)
    monkeypatch.setenv("MY_DIR", "/somewhere/else")
    assert vp.app_dir("x", env_var="MY_DIR") == Path("/somewhere/else")


# ── resolve ─────────────────────────────────────────────────────────────────

def test_resolve_joins_parts_under_vault(monkeypatch):
    monkeypatch.setenv("WILLOW_STORE_ROOT", "/data/vault")
    monkeypatch.delenv("FIELD_NOTES_DB", raising=False)
    assert vp.resolve("field-notes", "field-notes.db",
                       env_vars=("FIELD_NOTES_DB",)) == Path("/data/vault/field-notes/field-notes.db")


def test_resolve_first_set_env_var_wins(monkeypatch):
    monkeypatch.setenv("WILLOW_STORE_ROOT", "/data/vault")
    monkeypatch.delenv("PRIVATE_LEDGER_DB", raising=False)
    monkeypatch.setenv("LEDGER_DB", "/legacy/ledger.db")
    # PRIVATE_LEDGER_DB is unset, so the fallback LEDGER_DB wins.
    assert vp.resolve("private-ledger", "private-ledger.db",
                      env_vars=("PRIVATE_LEDGER_DB", "LEDGER_DB")) == Path("/legacy/ledger.db")


def test_resolve_env_precedence_is_ordered(monkeypatch):
    monkeypatch.setenv("PRIMARY", "/primary.db")
    monkeypatch.setenv("SECONDARY", "/secondary.db")
    assert vp.resolve("x.db", env_vars=("PRIMARY", "SECONDARY")) == Path("/primary.db")


def test_resolve_no_env_no_parts_is_vault_root(monkeypatch):
    monkeypatch.setenv("WILLOW_STORE_ROOT", "/data/vault")
    assert vp.resolve(env_vars=()) == Path("/data/vault")


def test_resolve_ignores_empty_env(monkeypatch):
    monkeypatch.setenv("WILLOW_STORE_ROOT", "/data/vault")
    monkeypatch.setenv("EMPTY", "")
    assert vp.resolve("db.sqlite", env_vars=("EMPTY",)) == Path("/data/vault/db.sqlite")
