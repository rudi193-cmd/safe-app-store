"""End-to-end: seed the local CLAUDE.md, list what landed, check a claim.

Runs against an isolated jeles corpus (temp WILLOW_STORE_ROOT) so a real
maker's corpus is never touched. Every one of the nine QUESTIONS-listed
maxims must round-trip: parse → seed → list → check.
"""
from __future__ import annotations

import io
import os
import sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR.parent.parent / "libs" / "quick-stupids" / "src"))

pytest.importorskip("jeles", reason="quick-stupids needs jeles installed")


@pytest.fixture
def isolated_corpus(tmp_path, monkeypatch):
    """Point jeles at a temp SOIL root and reload its corpus module so no
    real user data is written."""
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path / "soil"))
    monkeypatch.setenv("WILLOW_HOME", str(tmp_path / "home"))
    (tmp_path / "soil").mkdir(parents=True, exist_ok=True)
    (tmp_path / "home").mkdir(parents=True, exist_ok=True)
    # Reload jeles.corpus so it picks up the fresh env
    for mod in list(sys.modules):
        if mod == "jeles.corpus" or mod.startswith("jeles.corpus."):
            del sys.modules[mod]
    import jeles.corpus as jc  # noqa: F401
    yield


def _run(argv):
    """Run qstupid.main with argv, capturing stdout+stderr; return (rc, out, err)."""
    from qstupid import main
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


def test_seed_then_list_then_check(isolated_corpus):
    from qstupid import QUESTIONS, _principles

    # Sanity: the parser finds every QUESTIONS-listed maxim in the local CLAUDE.md
    principles = _principles()
    assert set(principles.keys()) == set(QUESTIONS.values()), \
        f"parser missed: {set(QUESTIONS.values()) - set(principles.keys())}"
    assert len(principles) == 9

    # seed
    rc, out, _ = _run(["seed"])
    assert rc == 0, out
    assert out.count("[updated ]") + out.count("[created ]") == 9, out
    assert "9 principles filed" in out

    # list — must show every one under our prefix
    rc, out, _ = _run(["list"])
    assert rc == 0
    assert "9 nuggets on file." in out
    assert out.count("quick-stupids/founding/") >= 9

    # check — a claim that clearly bears on "a test that does not run in CI is not a test"
    rc, out, _ = _run(["check", "we", "should", "skip", "the", "test", "in", "CI"])
    assert rc == 0
    assert "That would be filed under:" in out
    assert "It isn't lost. It's misfiled." in out
    # At least one hit line
    assert "quick-stupids/founding/" in out

    # check — a claim with nothing on file → no-hits message
    rc, out, _ = _run(["check", "how", "do", "I", "brew", "espresso"])
    assert rc == 0
    assert "nothing in the founding rules bears on that" in out


def test_seed_is_idempotent(isolated_corpus):
    _run(["seed"])
    rc, out2, _ = _run(["seed"])
    assert rc == 0
    # Second run: every one should be "updated" (deterministic sha1 ids)
    assert out2.count("[updated ]") == 9, out2

    # list count unchanged
    rc, out3, _ = _run(["list"])
    assert "9 nuggets on file." in out3


def test_missing_section_produces_empty_seed(isolated_corpus, tmp_path, monkeypatch):
    """If the section is renamed or deleted, seed reports 0 principles
    rather than silently filing nothing under a lying success code."""
    import qstupid
    monkeypatch.setattr(qstupid, "CLAUDE_MD", tmp_path / "empty.md")
    (tmp_path / "empty.md").write_text("# no matching section here\n")
    rc, out, err = _run(["seed"])
    assert rc == 1
    assert "no principles supplied" in err

    # check still works, still reports nothing (no hits from this app)
    rc, out, _ = _run(["check", "anything"])
    assert rc == 0
    assert "nothing in the founding rules bears on that" in out


def test_check_isolation_from_another_apps_prefix(isolated_corpus):
    """If another app files nuggets under a different id prefix, our
    check must not surface them."""
    _run(["seed"])
    from jeles import corpus as jc
    jc.put_nugget(
        nugget_id="OTHER-app/founding/deadbeef",
        question="What is the answer to another app's question?",
        answer="A different answer that mentions test and CI and skip in one sentence.",
        sources=["file://elsewhere"],
        verified_by="other-app",
        tags=["other-app"],
    )
    rc, out, _ = _run(["check", "test", "CI", "skip"])
    assert rc == 0
    # Every hit line must be under our prefix, none from OTHER-app
    for line in out.splitlines():
        if line.strip().startswith("(") and "app/" in line:
            assert "quick-stupids/founding/" in line, f"leaked other-app row: {line}"
