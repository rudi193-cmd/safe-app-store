# b17: SAPS1  ΔΣ=42
"""
Tests for The Binder's READ seam (willow_read).

These run WITHOUT textual and WITHOUT psycopg2: the seam imports neither at
module top. They prove the preferred path (injected client) and the graceful
degradation contract (never raises; empty on any failure).
"""
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import willow_read  # noqa: E402


# ── Fakes ─────────────────────────────────────────────────────────────────────

class FakeClient:
    """A willow-mcp-shaped client returning canned atoms."""

    def __init__(self, atoms):
        self.atoms = atoms
        self.calls = []

    def knowledge_search(self, query, limit):
        self.calls.append((query, limit))
        return self.atoms


class RaisingClient:
    def knowledge_search(self, query, limit):
        raise RuntimeError("backend exploded")


@pytest.fixture(autouse=True)
def _clear_client():
    """Every test starts with no injected client."""
    willow_read.set_client(None)
    yield
    willow_read.set_client(None)


# ── Preferred path: injected client wins and is normalized ────────────────────

def test_injected_client_is_preferred_and_normalized():
    atoms = [
        {"content": "the body text", "domain": "saps1", "source": "atomA",
         "tags": ["x"], "title": "Title A", "project": "proj-a"},
        {"content": "second body", "domain": "saps1", "source": "atomB",
         "tags": []},
    ]
    fake = FakeClient(atoms)
    willow_read.set_client(fake)

    assert willow_read.active_backend() == "mcp"
    assert willow_read.available() is True

    out = willow_read.search("anything", limit=5)
    assert fake.calls == [("anything", 5)]
    assert out == [
        {"title": "Title A", "summary": "the body text", "project": "proj-a"},
        # no explicit title -> falls back to source; no project -> domain
        {"title": "atomB", "summary": "second body", "project": "saps1"},
    ]
    # Every row is exactly the display shape.
    for row in out:
        assert set(row.keys()) == {"title", "summary", "project"}


def test_client_passed_as_arg_is_preferred():
    fake = FakeClient([{"content": "c", "source": "s", "domain": "d"}])
    # No module-level client set; pass via arg.
    out = willow_read.search("q", limit=3, client=fake)
    assert out == [{"title": "s", "summary": "c", "project": "d"}]
    assert fake.calls == [("q", 3)]


# ── Degradation: no gated client -> no read (box audit B3) ────────────────────

def test_no_client_returns_empty_and_reports_none():
    # The raw willow.knowledge fallback (an unscoped gate-bypass) was removed, so
    # with no gated client there is no read — regardless of whether psycopg2 is
    # installed. Previously this only held when psycopg2 was absent.
    assert willow_read.active_backend() == "none"
    assert willow_read.available() is False
    assert willow_read.search("hello world") == []  # never raises


# ── Seam never propagates a client error ──────────────────────────────────────

def test_raising_client_returns_empty():
    willow_read.set_client(RaisingClient())
    # active_backend still "mcp" (a client is set), but search must not raise.
    assert willow_read.active_backend() == "mcp"
    assert willow_read.search("boom") == []


# ── Normalization tolerance ───────────────────────────────────────────────────

def test_atom_missing_summary_uses_content():
    fake = FakeClient([{"content": "only content here", "source": "src"}])
    willow_read.set_client(fake)
    out = willow_read.search("q")
    assert out == [{"title": "src", "summary": "only content here", "project": ""}]


def test_atom_missing_everything_no_keyerror():
    fake = FakeClient([{}])
    willow_read.set_client(fake)
    out = willow_read.search("q")
    assert out == [{"title": "", "summary": "", "project": ""}]


def test_explicit_summary_preferred_over_content():
    fake = FakeClient([{"summary": "the summary", "content": "the content",
                        "title": "T", "project": "P"}])
    willow_read.set_client(fake)
    out = willow_read.search("q")
    assert out == [{"title": "T", "summary": "the summary", "project": "P"}]


def test_non_dict_atom_normalizes_to_blank():
    fake = FakeClient(["not a dict", 42])
    willow_read.set_client(fake)
    out = willow_read.search("q")
    assert out == [
        {"title": "", "summary": "", "project": ""},
        {"title": "", "summary": "", "project": ""},
    ]


def test_empty_atom_list_returns_empty():
    fake = FakeClient([])
    willow_read.set_client(fake)
    assert willow_read.search("q") == []


# ── set_client / get_client round-trip ────────────────────────────────────────

def test_set_and_get_client():
    assert willow_read.get_client() is None
    fake = FakeClient([])
    willow_read.set_client(fake)
    assert willow_read.get_client() is fake
    willow_read.set_client(None)
    assert willow_read.get_client() is None


# ── Static coupling checks: the anti-pattern moved OUT of app.py ──────────────

def test_app_py_has_no_psycopg2_and_no_kb_sql():
    app_path = os.path.join(_HERE, "app.py")
    with open(app_path, "r", encoding="utf-8") as fh:
        source = fh.read()
    assert "import psycopg2" not in source
    assert "psycopg2" not in source
    assert "willow.knowledge" not in source
    # And it must go through the seam.
    assert "import willow_read" in source


def test_seam_has_no_top_level_psycopg2_import():
    seam_path = os.path.join(_HERE, "willow_read.py")
    with open(seam_path, "r", encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    # No un-indented (module-level) psycopg2 import.
    for line in lines:
        if line.startswith("import psycopg2") or line.startswith("from psycopg2"):
            pytest.fail(f"module-level psycopg2 import found: {line!r}")
