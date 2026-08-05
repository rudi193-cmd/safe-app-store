"""The decision record's covenant, enforced (stores/decisions/README.md).

Two halves, same pattern as the other drift-guards: prove the REAL record is
currently clean, and prove the checks are not vacuous — each one catches a
synthetic violation. A gate that only ever saw clean input has never been
shown to gate anything (the lesson test_p1_keeping_records.py encodes for
catalog_lint).
"""
from __future__ import annotations

import copy
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import decisions_boot  # noqa: E402


def _clean() -> dict:
    return copy.deepcopy(decisions_boot.load())


class TestRealRecord:
    def test_current_record_is_clean(self):
        assert decisions_boot.validate(decisions_boot.load()) == []

    def test_renders_without_error_and_splits_never_from_not_yet(self):
        out = io.StringIO()
        decisions_boot.render(decisions_boot.load(), out=out)
        text = out.getvalue()
        assert "standing law:" in text
        assert "[never]" in text
        assert "[not yet" in text
        # The essay's verdict is in the record, with its reopen condition.
        assert "deterministic, reproducible, and auditable" in text


class TestChecksAreNotVacuous:
    def test_missing_reason_on_decision_caught(self):
        rec = _clean()
        rec["decisions"][0]["reason"] = ""
        assert any("reason" in p for p in decisions_boot.validate(rec))

    def test_verifier_equals_author_caught(self):
        rec = _clean()
        rec["decisions"][0]["verified_by"] = rec["decisions"][0]["author"]
        assert any("same hand" in p for p in decisions_boot.validate(rec))

    def test_unexplained_rejection_caught(self):
        rec = _clean()
        rec["rejections"][0]["reason"] = ""
        assert any("reason" in p for p in decisions_boot.validate(rec))

    def test_omitted_reopen_when_caught(self):
        # 'never' must be written, not omitted - deleting the key is the
        # accidental-permanence bug, distinct from an empty string.
        rec = _clean()
        del rec["rejections"][0]["reopen_when"]
        assert any("reopen_when" in p for p in decisions_boot.validate(rec))

    def test_superseded_decisions_leave_the_standing_law(self):
        rec = _clean()
        rec["decisions"][0]["superseded_by"] = "2026-08-06"
        out = io.StringIO()
        decisions_boot.render(rec, out=out)
        # Match the rendered LAW LINE, not the bare commitment string - the
        # commitment's words may legitimately appear in other entries'
        # reasons (found the day 'Nestor' showed up in a rejection reason).
        law_line = f"-> {rec['decisions'][0]['commitment']}  (sealed by"
        assert law_line not in out.getvalue()
        rec2 = _clean()
        assert law_line in (lambda s: (decisions_boot.render(rec2, out=s), s)[1])(io.StringIO()).getvalue()

    def test_strict_exits_nonzero_on_violation(self, tmp_path):
        import json
        rec = _clean()
        rec["rejections"][0]["reason"] = ""
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps(rec))
        assert decisions_boot.main(["--strict", "--record", str(bad)]) == 1
        assert decisions_boot.main(["--record", str(bad)]) == 0  # warn-only
