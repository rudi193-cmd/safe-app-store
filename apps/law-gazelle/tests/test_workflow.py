"""Tests for lawyer-led workflow action cards."""

from __future__ import annotations

import unittest
from unittest import mock

import workflow
from workflow import (
    ACTION_DRAFT_SCHEDULE,
    ACTION_VERIFY_FACT,
    STATUS_OVERDUE,
    STATUS_READY_TO_DRAFT,
    item_to_action_card,
)


class WorkflowInferenceTests(unittest.TestCase):
    def test_schedule_deadline_ready_to_draft(self) -> None:
        item = {
            "case": "coparent",
            "source_db": "coparent",
            "kind": "deadline",
            "item_type": "deadline",
            "item_id": "deadline:schedule",
            "deadline_key": "schedule",
            "title": "Schedule proposals",
            "deadline": "2099-01-01",
            "days_until": 5,
            "overdue": False,
        }
        card = item_to_action_card(item)
        self.assertEqual(card["recommended_action"], ACTION_DRAFT_SCHEDULE)
        self.assertEqual(card["status"], workflow.STATUS_DUE_SOON)

    def test_overdue_deadline(self) -> None:
        item = {
            "case": "coparent",
            "source_db": "coparent",
            "kind": "deadline",
            "item_type": "deadline",
            "item_id": "deadline:schedule",
            "deadline_key": "schedule",
            "title": "Schedule",
            "overdue": True,
            "days_until": -2,
        }
        card = item_to_action_card(item)
        self.assertEqual(card["status"], STATUS_OVERDUE)

    def test_schedule_atom_draft(self) -> None:
        item = {
            "case": "coparent",
            "source_db": "coparent",
            "kind": "atom",
            "item_type": "atom",
            "item_id": "ATM-001",
            "atom_id": "ATM-001",
            "domain": "schedule",
            "priority": "urgent",
            "title": "Thursday exchange",
        }
        with mock.patch.object(workflow.gazelle_state, "get_fact_verification", return_value=None):
            card = item_to_action_card(item)
        self.assertEqual(card["recommended_action"], ACTION_DRAFT_SCHEDULE)

    def test_atom_needs_source_blocked(self) -> None:
        item = {
            "case": "coparent",
            "source_db": "coparent",
            "kind": "atom",
            "item_type": "atom",
            "item_id": "ATM-002",
            "atom_id": "ATM-002",
            "domain": "compliance",
            "title": "Missing proof",
        }
        with mock.patch.object(
            workflow.gazelle_state, "get_fact_verification", return_value="needs_source"
        ):
            card = item_to_action_card(item)
        self.assertEqual(card["recommended_action"], ACTION_VERIFY_FACT)
        self.assertEqual(card["status"], workflow.STATUS_BLOCKED)

    def test_action_deck_has_seven_steps(self) -> None:
        card = item_to_action_card({
            "case": "coparent",
            "source_db": "coparent",
            "kind": "atom",
            "item_type": "atom",
            "item_id": "ATM-001",
            "title": "Test",
        })
        steps = workflow.action_deck_entries(card)
        self.assertEqual(len(steps), 7)

    def test_suggested_doc_type_schedule(self) -> None:
        card = item_to_action_card({
            "case": "coparent",
            "source_db": "coparent",
            "kind": "deadline",
            "item_type": "deadline",
            "item_id": "deadline:schedule",
            "deadline_key": "schedule",
            "title": "Schedule",
        })
        self.assertEqual(workflow.suggested_doc_type(card), "schedule_response")

    def test_fact_review_row_has_workbench_fields(self) -> None:
        card = item_to_action_card({
            "case": "coparent",
            "source_db": "coparent",
            "kind": "atom",
            "item_type": "atom",
            "item_id": "ATM-001",
            "atom_id": "ATM-001",
            "title": "Thursday exchange",
        })
        detail = {
            "atom": {
                "atom_id": "ATM-001",
                "title": "Thursday exchange",
                "action_required": "Confirm exchange time before drafting.",
                "domain": "schedule",
                "priority": "urgent",
            },
            "evidence": [{"title": "Parenting plan section V.Q"}],
        }
        with mock.patch.object(workflow, "get_atom_detail", return_value=detail), mock.patch.object(
            workflow.gazelle_state, "get_fact_verification", return_value=None
        ):
            rows = workflow.fact_review_rows(card)
        self.assertEqual(rows[0]["review_status"], "Unreviewed")
        self.assertIn("Confirm exchange time", rows[0]["case_summary"])
        self.assertEqual(rows[0]["source_summary"], "Parenting plan section V.Q")
        self.assertIn("Press 1", rows[0]["review_action"])


if __name__ == "__main__":
    unittest.main()
