"""The four verbs, then the attacks.

made / rejected / modified / affects-future - each verb gets its section,
because the finding that started this build was that existing stores hold
two of the four. The adversarial section is the same set of attacks Nestor's
sixty-second demo runs against itself: the forged seal, the tampered ledger,
the machine trying to do the human's half.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from aristarchus import (CovenantViolation, DecisionMemory, DecisionStore,
                         LedgerBroken, SealKeyMissing)


@pytest.fixture()
def mem(tmp_path, monkeypatch):
    monkeypatch.setenv("ARISTARCHUS_SEAL_KEY", "test-key")
    store = DecisionStore(":memory:", tmp_path / "ledger.jsonl")
    yield DecisionMemory(store)
    store.close()


def _decide(mem, question, commitment, reason="because", author="machine",
            verifier="operator"):
    draft = mem.propose(question, commitment, reason, author=author)
    return mem.seal(draft["id"], verifier, reason)


# -- made ----------------------------------------------------------------

class TestMade:
    def test_propose_is_a_draft_not_a_decision(self, mem):
        row = mem.propose("Which store holds the graph?", "Nestor",
                          author="machine")
        assert row["status"] == "draft"
        assert row["seal_sig"] == ""

    def test_seal_ratifies_with_provenance(self, mem):
        sealed = _decide(mem, "Which store holds the graph?", "Nestor",
                         reason="only store with a seal and a hash chain")
        live = mem.constraints_on("Which store holds the graph?").live
        assert live is not None
        assert live["status"] == "sealed"
        assert live["verifier"] == "operator"
        assert live["reason"] == "only store with a seal and a hash chain"
        assert live["id"] == sealed["id"]

    def test_reason_for_yes_is_kept(self, mem):
        # N4: the rationale behind what was chosen is what a future
        # proposal must argue against - it cannot be an empty column.
        sealed = _decide(mem, "Partial or full unique index?", "partial",
                         reason="keeps the concurrent-seal race guard")
        assert sealed["reason"] == "keeps the concurrent-seal race guard"


# -- rejected ------------------------------------------------------------

class TestRejected:
    def test_rejection_is_durable_and_reasoned(self, mem):
        mem.reject("Where does the graph live?", "SAPS1",
                   reason="no seal, no signature, no hash chain",
                   verifier="operator")
        c = mem.constraints_on("Where does the graph live?")
        assert len(c.rejections) == 1
        assert c.rejections[0]["reason"] == ("no seal, no signature, "
                                             "no hash chain")

    def test_rejection_without_reason_refused(self, mem):
        # The Aristarchus bug itself: an unexplained no.
        with pytest.raises(CovenantViolation):
            mem.reject("Anything?", "an option", reason="",
                       verifier="operator")

    def test_never_vs_not_yet(self, mem):
        # N5: empty reopen_when is a closed door; non-empty is a deferral
        # surfaced as a condition to check, in a different bucket.
        mem.reject("Ship the corpus with the reader?", "bundle both",
                   reason="the corpus stays with whoever grew it",
                   verifier="operator")
        mem.reject("Put the graph in SAPS1?", "SAPS1",
                   reason="asserted, not ratified",
                   verifier="operator",
                   reopen_when="SAPS1 grows a ratification primitive")
        never = mem.constraints_on("Ship the corpus with the reader?")
        notyet = mem.constraints_on("Put the graph in SAPS1?")
        assert never.rejections and not never.reopeners
        assert notyet.reopeners and not notyet.rejections
        assert notyet.reopeners[0]["reopen_when"] == (
            "SAPS1 grows a ratification primitive")


# -- modified ------------------------------------------------------------

class TestModified:
    def test_supersede_keeps_the_lineage(self, mem):
        first = _decide(mem, "Catalog format?", "root catalog.json",
                        reason="simplest thing that works")
        second = mem.supersede(first["id"], ".willow/store/catalog.json",
                               reason="rule 9: the catalog lives in "
                                      ".willow/store/",
                               verifier="operator", author="machine")
        c = mem.constraints_on("Catalog format?")
        assert c.live["id"] == second["id"]
        assert len(c.lineage) == 1
        assert c.lineage[0]["id"] == first["id"]
        # The replaced decision keeps ITS reason - the lineage is reasons,
        # not just rows.
        assert c.lineage[0]["reason"] == "simplest thing that works"
        assert c.lineage[0]["superseded_by"] == second["id"]

    def test_one_live_row_no_silent_overwrite(self, mem):
        _decide(mem, "Catalog format?", "root catalog.json")
        # A second propose on a live key is refused and points at
        # supersede() - revision must not be able to destroy quietly.
        with pytest.raises(CovenantViolation, match="supersede"):
            mem.propose("Catalog format?", "something else",
                        author="machine")

    def test_partial_index_allows_history_to_accumulate(self, mem):
        d1 = _decide(mem, "Threshold?", "0.80", reason="first guess")
        d2 = mem.supersede(d1["id"], "0.92", reason="benched on boil-2k",
                           verifier="operator")
        d3 = mem.supersede(d2["id"], "0.90", reason="recall fell at 0.92",
                           verifier="operator")
        c = mem.constraints_on("Threshold?")
        assert c.live["id"] == d3["id"]
        assert [r["id"] for r in c.lineage] == [d2["id"], d1["id"]]

    def test_failed_supersede_leaves_store_intact(self, mem):
        first = _decide(mem, "Catalog format?", "root catalog.json")
        with pytest.raises(CovenantViolation):
            # verifier == author: the seal inside supersede must refuse,
            # and the old row must come back to the live index untouched.
            mem.supersede(first["id"], "other", reason="r",
                          verifier="machine", author="machine")
        c = mem.constraints_on("Catalog format?")
        assert c.live is not None and c.live["id"] == first["id"]
        assert c.lineage == []

    def test_supersede_only_the_live_row(self, mem):
        d1 = _decide(mem, "Threshold?", "0.80")
        mem.supersede(d1["id"], "0.92", reason="benched",
                      verifier="operator")
        with pytest.raises(CovenantViolation, match="already superseded"):
            mem.supersede(d1["id"], "0.95", reason="stale base",
                          verifier="operator")


# -- affects future ------------------------------------------------------

class TestAffectsFuture:
    def test_reworded_question_finds_the_record(self, mem):
        # N1, the load-bearing joint: the same decision wearing different
        # words must resolve to the stored key. The baseline StringMatcher
        # only has to survive light rewording here; the real accuracy
        # number is the bench (open question 2), not this test.
        _decide(mem, "Which store should hold the decision graph?", "Nestor")
        c = mem.constraints_on("Which store should hold the decision graph")
        assert c.live is not None
        assert c.match_score >= 0.90

    def test_supersedes_edge_recorded_and_signed(self, mem):
        d1 = _decide(mem, "Threshold?", "0.80")
        d2 = mem.supersede(d1["id"], "0.92", reason="benched",
                           verifier="operator")
        edges = mem.store.edges_for(d2["id"])
        assert len(edges) == 1
        e = edges[0]
        assert (e["kind"], e["src_id"], e["dst_id"]) == \
            ("supersedes", d2["id"], d1["id"])
        assert e["edge_sig"] and not e.get("tampered")

    def test_cross_decision_edges(self, mem):
        a = _decide(mem, "Sandbox runner?", "bwrap")
        b = _decide(mem, "Mount boundary?", "per-builder directory")
        mem.store.add_edge(b["id"], a["id"], "depends_on",
                           "the boundary assumes the sandbox exists",
                           "operator")
        c = mem.constraints_on("Mount boundary?")
        kinds = [e["kind"] for e in c.edges]
        assert "depends_on" in kinds

    def test_unconstrained_question_says_so(self, mem):
        c = mem.constraints_on("Something never discussed?")
        assert c.unconstrained


# -- adversarial ---------------------------------------------------------

class TestAdversarial:
    def test_forged_seal_not_served(self, mem):
        sealed = _decide(mem, "Catalog format?", "root catalog.json")
        # Forge straight into the database, past the API - the row now
        # SAYS sealed with a commitment nobody ratified.
        mem.store._conn.execute(
            "UPDATE decisions SET commitment='attacker value' WHERE id=?",
            (sealed["id"],))
        mem.store._conn.commit()
        c = mem.constraints_on("Catalog format?")
        assert c.live is None
        assert c.tampered and c.tampered[0]["status"] == "tampered"

    def test_seal_requires_key(self, mem, monkeypatch):
        draft = mem.propose("Q?", "A", author="machine")
        monkeypatch.delenv("ARISTARCHUS_SEAL_KEY")
        with pytest.raises(SealKeyMissing):
            mem.seal(draft["id"], "operator")

    def test_missing_key_downgrades_reads_not_upgrades(self, mem,
                                                       monkeypatch):
        _decide(mem, "Q?", "A")
        monkeypatch.delenv("ARISTARCHUS_SEAL_KEY")
        # Without the key nothing can verify, so nothing is served sealed.
        c = mem.constraints_on("Q?")
        assert c.live is None
        assert c.tampered

    def test_verifier_must_differ_from_author(self, mem):
        draft = mem.propose("Q?", "A", author="machine")
        with pytest.raises(CovenantViolation, match="same hand"):
            mem.seal(draft["id"], "machine")

    def test_seal_requires_a_verifier_at_all(self, mem):
        draft = mem.propose("Q?", "A", author="machine")
        with pytest.raises(CovenantViolation):
            mem.seal(draft["id"], "")

    def test_tampered_ledger_refuses_next_decision(self, mem, tmp_path):
        _decide(mem, "Q?", "A")
        ledger = mem.store.ledger_path
        lines = ledger.read_text().splitlines()
        entry = json.loads(lines[0])
        entry["detail"]["author"] = "someone else"   # edit one past field
        lines[0] = json.dumps(entry, sort_keys=True)
        ledger.write_text("\n".join(lines) + "\n")
        assert not mem.store.ledger_verify()
        with pytest.raises(LedgerBroken):
            mem.propose("Next?", "thing", author="machine")

    def test_edge_requires_verifier(self, mem):
        a = _decide(mem, "Q1?", "A")
        b = _decide(mem, "Q2?", "B")
        with pytest.raises(CovenantViolation):
            mem.store.add_edge(a["id"], b["id"], "contradicts", "r", "")

    def test_live_index_is_a_real_constraint(self, mem):
        # Belt and braces: even bypassing propose()'s guard, the partial
        # unique index itself refuses a second live row for the same key.
        _decide(mem, "Q?", "A")
        with pytest.raises(sqlite3.IntegrityError):
            mem.store._conn.execute(
                "INSERT INTO decisions (id, question, question_norm, domain,"
                " commitment, reason, status, author, verifier, created_at,"
                " seal_sig, superseded_by) VALUES ('x','Q?','q','decision',"
                "'B','','draft','m','','now','','')")
