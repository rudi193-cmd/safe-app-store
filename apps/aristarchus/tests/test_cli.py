"""The warn-mode gate: it speaks, it does not block - except for integrity.

run_check() is tested directly with an injected memory (any matcher), and
main() end-to-end with exact-match questions plus --no-semantic, so the
suite never needs the sentence encoder (which this build environment cannot
download anyway - the bench provenance note tells that story).
"""
from __future__ import annotations

import io
import json

import pytest

from aristarchus import DecisionMemory, DecisionStore
from aristarchus.cli import check_question, main, run_check


@pytest.fixture()
def mem(tmp_path, monkeypatch):
    monkeypatch.setenv("ARISTARCHUS_SEAL_KEY", "test-key")
    store = DecisionStore(":memory:", tmp_path / "ledger.jsonl")
    m = DecisionMemory(store, threshold=0.85)
    d = m.propose("Which store should hold the decision graph?", "Nestor",
                  "only store with a seal", author="machine")
    m.seal(d["id"], "operator")
    m.reject("Which store should hold the decision graph?", "SAPS1",
             reason="asserted, not ratified", verifier="operator",
             reopen_when="SAPS1 grows a ratification primitive")
    yield m
    store.close()


class TestWarnMode:
    def test_clear_question_exits_zero_and_says_clear(self, mem):
        out = io.StringIO()
        code = run_check(mem, ["Should the demo pause between beats?"],
                         out=out)
        assert code == 0
        assert "clear" in out.getvalue()

    def test_constrained_question_speaks_but_exits_zero(self, mem):
        out = io.StringIO()
        code = run_check(mem, ["Which store should hold the decision graph?"],
                         out=out)
        assert code == 0                       # warn-mode: never blocks
        text = out.getvalue()
        assert "constrained" in text
        assert "Nestor" in text                # the law
        assert "not yet" in text               # the reopener, as a condition
        assert "SAPS1 grows a ratification primitive" in text

    def test_exact_match_is_confident_tier(self, mem):
        r = check_question(mem, "Which store should hold the decision graph?")
        assert r["tier"] == "confident" and r["score"] == 1.0

    def test_strict_exits_2_on_findings_and_says_unearned(self, mem):
        out = io.StringIO()
        code = run_check(mem, ["Which store should hold the decision graph?"],
                         strict=True, out=out)
        assert code == 2
        assert "not earned" in out.getvalue()

    def test_strict_stays_zero_when_clear(self, mem):
        code = run_check(mem, ["Should the demo pause between beats?"],
                         strict=True, out=io.StringIO())
        assert code == 0

    def test_json_output(self, mem):
        out = io.StringIO()
        run_check(mem, ["Which store should hold the decision graph?"],
                  json_out=True, out=out)
        payload = json.loads(out.getvalue())
        assert payload["ledger_ok"] is True
        assert payload["results"][0]["tier"] == "confident"


class TestIntegrityOutranksAdvisory:
    def test_broken_ledger_exits_2_even_in_warn_mode(self, mem):
        ledger = mem.store.ledger_path
        lines = ledger.read_text().splitlines()
        entry = json.loads(lines[0])
        entry["detail"]["author"] = "someone else"
        lines[0] = json.dumps(entry, sort_keys=True)
        ledger.write_text("\n".join(lines) + "\n")
        out = io.StringIO()
        code = run_check(mem, ["anything"], out=out)
        assert code == 2
        assert "BROKEN ledger" in out.getvalue()

    def test_tampered_row_is_a_finding(self, mem):
        mem.store._conn.execute(
            "UPDATE decisions SET commitment='attacker value'")
        mem.store._conn.commit()
        r = check_question(mem, "Which store should hold the decision graph?")
        assert r["tier"] == "integrity"
        out = io.StringIO()
        code = run_check(mem, ["Which store should hold the decision graph?"],
                         out=out)
        assert code == 0                       # warn-mode still speaks-only
        assert "TAMPERED" in out.getvalue()


class TestMainEndToEnd:
    def test_main_with_real_db(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("ARISTARCHUS_SEAL_KEY", "test-key")
        db, ledger = str(tmp_path / "d.db"), str(tmp_path / "l.jsonl")
        store = DecisionStore(db, ledger)
        m = DecisionMemory(store)
        d = m.propose("Ship the corpus?", "no - reader only",
                      author="machine")
        m.seal(d["id"], "operator")
        store.close()

        code = main(["check", "--db", db, "--ledger", ledger,
                     "--no-semantic", "Ship the corpus?"])
        assert code == 0
        text = capsys.readouterr().out
        assert "constrained" in text and "reader only" in text

    def test_main_strict_flag(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("ARISTARCHUS_SEAL_KEY", "test-key")
        db, ledger = str(tmp_path / "d.db"), str(tmp_path / "l.jsonl")
        store = DecisionStore(db, ledger)
        m = DecisionMemory(store)
        d = m.propose("Ship the corpus?", "no", author="machine")
        m.seal(d["id"], "operator")
        store.close()

        code = main(["check", "--db", db, "--ledger", ledger, "--strict",
                     "--no-semantic", "Ship the corpus?"])
        assert code == 2
