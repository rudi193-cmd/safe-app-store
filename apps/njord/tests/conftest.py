"""Shared test fixtures — isolate all Njord vault state under a tmp dir so the
suite never touches a real ~/.willow store, and runs fully offline.
"""
import os
import sys
from pathlib import Path

import pytest

# Make src/ importable without an install.
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(autouse=True)
def isolated_vault(tmp_path, monkeypatch):
    """Point NJORD_HOME + WILLOW_STORE_ROOT at a throwaway dir for every test."""
    home = tmp_path / "njord_home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("NJORD_HOME", str(home))
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path / "store"))
    # Ensure no live gate env leaks in from the host.
    monkeypatch.delenv("NJORD_LIVE_CREDENTIAL", raising=False)
    monkeypatch.delenv("NJORD_I_UNDERSTAND_LIVE", raising=False)
    yield home
