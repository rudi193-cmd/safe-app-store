"""Journal is append-only; entries carry provenance; re-open preserves history."""
from njord.journal.journal import Journal


def test_append_and_read():
    j = Journal()
    j.append("recommend", {"symbol": "AAPL", "score": 1.2},
             provenance={"source_ids": ["STUB"], "fetched_at": ["2026-07-24T00:00:00Z"]})
    entries = j.read_all()
    assert len(entries) == 1
    assert entries[0].kind == "recommend"
    assert entries[0].provenance["source_ids"] == ["STUB"]


def test_append_is_additive_not_mutating():
    j = Journal()
    j.append("a", {"n": 1})
    j.append("b", {"n": 2})
    j.append("c", {"n": 3})
    entries = j.read_all()
    assert [e.kind for e in entries] == ["a", "b", "c"]
    assert [e.payload["n"] for e in entries] == [1, 2, 3]


def test_reopen_preserves_history():
    j1 = Journal()
    j1.append("recommend", {"symbol": "MSFT"}, provenance={"source_ids": ["STUB"]})
    # A fresh Journal pointing at the same path sees prior entries.
    j2 = Journal()
    j2.append("recommend", {"symbol": "NVDA"}, provenance={"source_ids": ["STUB"]})
    entries = j2.read_all()
    assert len(entries) == 2
    assert entries[0].payload["symbol"] == "MSFT"
    assert entries[1].payload["symbol"] == "NVDA"


def test_every_entry_can_carry_provenance():
    j = Journal()
    j.append("recommend", {"symbol": "AAPL"},
             provenance={"source_ids": ["STUB"], "fetched_at": ["2026-07-24T00:00:00Z"]})
    e = j.read_all()[0]
    assert e.provenance and "source_ids" in e.provenance
