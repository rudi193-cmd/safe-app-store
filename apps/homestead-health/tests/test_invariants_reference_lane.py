"""H-7 — the reference lane holds no subject and dials for nothing (bite 6).

The information lane: public knowledge, pinned and versioned, served by an injected
reader that returns cited answers and never touches a subject. Bite 6's done-when
(`homestead/docs/PLAN-homestead-health.md` § bite 6):

* a household question returns cited answers from the pinned corpus;
* grepping the reference store for any subject id comes back empty (H-7);
* the reader has no network import and never resolves a link at runtime (I-17);
* a CC-BY source's attribution appears on every answer that quotes it;
* the corpus reports its own version and date the way H-5's schedule does.

Landed directly (the extension's H-6…H-8 were never in `test_invariants_pending.py`).
"""
from __future__ import annotations

import ast
import inspect
from datetime import date
from pathlib import Path

import pytest

from homestead_health.reference_lane import CORPUS, Corpus, Entry, Reader, Result

MODULE = Path(__file__).resolve().parent.parent / "homestead_health" / "reference_lane.py"


# ── a household question returns cited answers ───────────────────────────────


def test_a_question_returns_cited_answers_from_the_pinned_corpus():
    results = Reader().ask("How do I prepare for my child's checkup?")
    assert results, "a matching question returns answers"
    top = results[0]
    assert isinstance(top, Result)
    assert "prepare" in top.entry.question.lower() or "checkup" in top.entry.question.lower()
    # Every answer carries its citation — a source and a license.
    for r in results:
        assert r.entry.source and r.entry.license
        assert r.attribution == f"{r.entry.source} ({r.entry.license})"


def test_nothing_matching_returns_nothing_rather_than_improvising():
    """A reference lane that invents an answer is the symptom-checker H-2 forbids.
    A question with no overlap returns an empty list — said plainly, not improvised."""
    assert Reader().ask("xyzzy quux frobnicate") == []


def test_the_reader_is_injected_over_its_corpus():
    """Ship the reader, the corpus stays with whoever grew it: the corpus is injected,
    defaulting to the pin. A host can hand a different corpus without changing the
    reader."""
    tiny = Corpus(
        version="test corpus",
        as_of=date(2026, 1, 1),
        entries=(Entry("What is a booster?", "A later dose in a series.", "Test Source", "public domain"),),
    )
    reader = Reader(tiny)
    assert reader.corpus is tiny
    hits = reader.ask("what is a booster")
    assert len(hits) == 1 and hits[0].entry.source == "Test Source"
    assert Reader().corpus is CORPUS


# ── attribution rides through, CC-BY included ────────────────────────────────


def test_a_cc_by_sources_attribution_appears_on_every_answer_that_quotes_it():
    """The corpus carries a CC-BY part; a question that draws it back gets its credit
    on the result, by construction — not a footnote someone can forget."""
    cc_by = [e for e in CORPUS.entries if "CC-BY" in e.license]
    assert cc_by, "the corpus includes a CC-BY part to exercise attribution"

    results = Reader().ask("keep household records")
    drawn = [r for r in results if r.entry in cc_by]
    assert drawn, "the CC-BY entry is retrievable"
    for r in drawn:
        assert r.entry.license in r.attribution and r.entry.source in r.attribution


# ── the corpus reports its own version and date (H-5, widened) ───────────────


def test_the_corpus_names_its_version_and_date():
    assert CORPUS.version, "a corpus that cannot say its version isn't a snapshot"
    assert CORPUS.as_of, "a corpus that cannot say its date is a live feed in disguise"
    assert CORPUS.version in CORPUS.citation()
    assert CORPUS.as_of.isoformat() in CORPUS.citation()


def test_as_of_is_a_literal_date_not_a_computed_value():
    """H-5's fix, carried here: `as_of` must parse as a literal `date(...)`, so a
    `getattr(date,'today')()` or a helper cannot make the snapshot a live feed while
    the tests stay green."""
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    as_of = None
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "CORPUS" for t in node.targets)
            and isinstance(node.value, ast.Call)
        ):
            for kw in node.value.keywords:
                if kw.arg == "as_of":
                    as_of = kw.value
    assert isinstance(as_of, ast.Call), "as_of must be a literal date(y, m, d)"
    callee = as_of.func
    name = callee.attr if isinstance(callee, ast.Attribute) else getattr(callee, "id", "")
    assert name == "date" and as_of.args and all(isinstance(a, ast.Constant) for a in as_of.args)


# ── holds no subject (H-7) ───────────────────────────────────────────────────


def test_the_corpus_holds_no_subject_by_shape():
    """Structural allowlist: the fields are exactly question/answer/source/license
    and version/as_of/entries. Any added person-shaped field fails — reference_lane.py
    enforces the same at import as a build failure."""
    assert set(Entry.__dataclass_fields__) == {"question", "answer", "source", "license"}
    assert set(Corpus.__dataclass_fields__) == {"version", "as_of", "entries"}


def test_the_import_guard_fires_on_a_drifted_field_set(monkeypatch):
    import homestead_health.reference_lane as ref

    monkeypatch.setattr(ref, "_ENTRY_FIELDS", frozenset({"question"}))
    with pytest.raises(RuntimeError):
        ref._check_no_subject_can_enter()


def test_the_reader_takes_a_question_never_a_subject():
    """The wall against H-2, made structural. `ask` takes a question and a limit —
    there is no subject parameter, and there is nowhere to pass a child's record. The
    lane retrieves public reference; it never joins it to a person."""
    params = set(inspect.signature(Reader.ask).parameters)
    assert params == {"self", "question", "limit"}
    for banned in ("subject", "subj", "child", "person", "record", "roster"):
        assert banned not in params


def test_no_subject_id_appears_anywhere_in_the_corpus():
    blob = repr(CORPUS)
    assert "subj-" not in blob
    assert "subject" not in blob.lower()


# ── dials for nothing, and joins to no subject-bearing module (H-7 / I-17) ───


def test_the_module_imports_no_network_and_no_subject_bearing_module():
    """I-17 (never dials) and H-7 (never joins to a subject): the module imports no
    network module and nothing that carries a person — no roster, no record store, no
    gate. It cannot join to a child because it never imports one."""
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    net = {"socket", "ssl", "urllib", "http", "requests", "httpx", "aiohttp", "urllib3"}
    assert not (net & {m.split(".")[0] for m in imported}), f"the lane dials: {imported}"

    subject_bearing = {
        "homestead_health.roster",
        "homestead.keep.record",
        "homestead.keep.rungs",
    }
    assert not (subject_bearing & imported), (
        f"the reference lane must not import a subject-bearing module: "
        f"{subject_bearing & imported}"
    )


def test_no_source_is_a_resolvable_link():
    """Never resolves a link at runtime (I-17): the corpus cites sources by name and
    title, not by a URL the reader could be tempted to fetch. No entry's source or
    answer carries an http(s) link."""
    for e in CORPUS.entries:
        assert "http://" not in e.source and "https://" not in e.source
        assert "http://" not in e.answer and "https://" not in e.answer
