"""Persistence resolves through the vault, and only one module decides where.

Installer design D8: no hardcoded home paths, and — the case this app got wrong
first — no defaulting user data into the app's own install directory. A
disposition log beside the source would sit inside a checkout, travel into any
copy of the app, and vanish on a reinstall.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from playgate import paths

PACKAGE = Path(__file__).resolve().parents[1] / "playgate"
APP_ROOT = PACKAGE.parent


# -- the policy is in one place -------------------------------------------

def test_only_paths_module_imports_the_resolver():
    """`vault_root` is a security boundary — the single decision about where
    the vault box is. A second importer is a second place for it to drift."""
    importers = []
    for module in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(module.read_text(), filename=str(module))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(n.split(".")[0] == "vault_paths" for n in names):
                importers.append(module.name)
    assert sorted(set(importers)) == ["paths.py"], importers


def test_the_core_modules_take_paths_rather_than_choosing_them():
    """catalog, disposition and install must not reach for a location. Being
    handed one is what keeps them stdlib-only and keeps the whole suite inside
    tmp_path."""
    for name in ("catalog.py", "disposition.py", "install.py", "interruption.py"):
        source = (PACKAGE / name).read_text()
        assert "vault_paths" not in source, name
        assert "Path.home" not in source, name
        assert "expanduser" not in source, name


# -- nothing lands in the install directory -------------------------------

def test_the_log_does_not_default_into_the_app_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path / "vault"))
    monkeypatch.delenv("PLAYGATE_LOG", raising=False)
    monkeypatch.delenv("APP_DATA", raising=False)
    resolved = paths.log_path().resolve()
    assert APP_ROOT.resolve() not in resolved.parents, resolved
    assert resolved.parent == (tmp_path / "vault" / "playgate").resolve()


def test_the_apk_dir_does_not_default_into_the_app_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path / "vault"))
    monkeypatch.delenv("PLAYGATE_APK_DIR", raising=False)
    resolved = paths.apk_dir().resolve()
    assert APP_ROOT.resolve() not in resolved.parents, resolved


def test_no_module_hardcodes_a_home_or_absolute_persistence_path():
    """Reads the source rather than trusting the two resolvers above: a new
    module could add its own default tomorrow."""
    forbidden = ("Path.home(", 'os.path.expanduser("~', "'~/", '"~/', "/home/", "/Users/")
    for module in sorted(PACKAGE.rglob("*.py")):
        source = module.read_text()
        for needle in forbidden:
            assert needle not in source, f"{module.name} contains {needle!r}"


# -- overrides still work -------------------------------------------------

def test_the_log_env_override_wins(monkeypatch, tmp_path):
    """Preserved so an operator can point at a legacy location while migrating
    into the vault."""
    monkeypatch.setenv("PLAYGATE_LOG", str(tmp_path / "elsewhere" / "r.jsonl"))
    assert paths.log_path() == tmp_path / "elsewhere" / "r.jsonl"


def test_the_apk_env_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("PLAYGATE_APK_DIR", str(tmp_path / "apks"))
    assert paths.apk_dir() == tmp_path / "apks"


def test_app_dir_is_under_the_vault_root(monkeypatch, tmp_path):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path / "vault"))
    monkeypatch.delenv("APP_DATA", raising=False)
    assert paths.app_dir() == tmp_path / "vault" / "playgate"


# -- the server refuses rather than guessing ------------------------------

def test_an_unconfigured_host_refuses_to_install_rather_than_searching_itself():
    """The previous default pointed apk_root at the app's own directory, which
    would have made an unconfigured host quietly look for APKs beside its own
    source.

    Asserts on the *class* default rather than on a handler built with an
    explicit None — an earlier version of this test passed None in and then
    checked it came back, which covered nothing. The mutation pass is what
    found that.
    """
    from playgate import server

    assert server.Handler.apk_root is None, (
        "the unconfigured default is no longer None; a host started without "
        "--apk-root would search wherever this now points"
    )

    class Fake:
        apk_path = "game.apk"
        sha256 = "00" * 32

    result = server.Handler._install(server.Handler, Fake())
    assert not result.ok and "no apk root configured" in result.detail


def test_the_shipped_catalog_is_the_one_app_relative_path():
    """Shipped content, not user data: read-only, travels with the app, and
    replaced wholesale by --catalog."""
    from playgate import catalog

    assert APP_ROOT.resolve() in catalog.DEFAULT_CATALOG.resolve().parents
    assert catalog.DEFAULT_CATALOG.is_file()
