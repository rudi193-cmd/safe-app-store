"""Tests for local intelligence layer (mocked Ollama)."""

from __future__ import annotations

import unittest
from unittest import mock

import intelligence
import llm_client
import tool_context
import workflow
from workflow import item_to_action_card


class LlmClientTests(unittest.TestCase):
    def test_generate_success(self) -> None:
        mock_resp = mock.Mock()
        mock_resp.json.return_value = {"response": "Hello", "model": "llama3.2:3b"}
        mock_resp.raise_for_status = mock.Mock()
        with mock.patch("llm_client.requests.post", return_value=mock_resp):
            out = llm_client.generate("test prompt", system="sys")
        self.assertTrue(out["ok"])
        self.assertEqual(out["text"], "Hello")

    def test_generate_timeout(self) -> None:
        import requests

        with mock.patch(
            "llm_client.requests.post",
            side_effect=requests.Timeout("timed out"),
        ):
            out = llm_client.generate("x")
        self.assertFalse(out["ok"])
        self.assertIn("timed out", out["error"])


class ToolContextTests(unittest.TestCase):
    def test_format_context_separates_sources(self) -> None:
        bundle = {
            "case_facts": [
                {
                    "kind": "case_fact",
                    "source": "gazelle",
                    "title": "Card",
                    "summary": "Fact line",
                }
            ],
            "legal_research": [
                {
                    "kind": "legal_research",
                    "source": "courtlistener",
                    "title": "Research",
                    "summary": "Case law",
                }
            ],
        }
        text = tool_context.format_context_for_prompt(bundle)
        self.assertIn("CASE FACTS", text)
        self.assertIn("LEGAL RESEARCH", text)
        self.assertIn("not case evidence", text)

    def test_courtlistener_empty_without_key(self) -> None:
        card = item_to_action_card({
            "case": "coparent",
            "source_db": "coparent",
            "kind": "atom",
            "item_type": "atom",
            "item_id": "ATM-001",
            "atom_id": "ATM-001",
            "title": "Test",
        })
        with mock.patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("COURTLISTENER_API_KEY", None)
            blocks = tool_context.courtlistener_context_for_card(card)
        self.assertEqual(blocks, [])

    def test_courtlistener_context_does_not_search_case_law(self) -> None:
        card = item_to_action_card({
            "case": "coparent",
            "source_db": "coparent",
            "kind": "atom",
            "item_type": "atom",
            "item_id": "ATM-001",
            "atom_id": "ATM-001",
            "title": "Test",
        })
        with mock.patch.dict("os.environ", {"COURTLISTENER_API_KEY": "token"}), mock.patch(
            "tool_context.courtlistener_verify_citations",
            return_value={"ok": True, "citations": [], "results": []},
        ), mock.patch("tool_context.courtlistener_search") as search:
            blocks = tool_context.courtlistener_context_for_card(card)
        search.assert_not_called()
        self.assertEqual(blocks, [])


class IntelligenceTests(unittest.TestCase):
    def test_brief_card_calls_llm(self) -> None:
        card = item_to_action_card({
            "case": "coparent",
            "source_db": "coparent",
            "kind": "atom",
            "item_type": "atom",
            "item_id": "ATM-001",
            "atom_id": "ATM-001",
            "domain": "schedule",
            "title": "Thursday exchange",
        })
        with mock.patch(
            "intelligence.llm_client.generate",
            return_value={"ok": True, "text": "# Brief\n\nDo X.", "model": "llama3.2:3b", "provider": "ollama", "error": None},
        ), mock.patch("intelligence.gazelle_state.log_activity"):
            out = intelligence.brief_card(card, include_courtlistener=False)
        self.assertTrue(out["ok"])
        self.assertIn("Brief", out["text"])

    def test_system_prompt_bars_unsupplied_case_law(self) -> None:
        self.assertIn("Do not cite or discuss case law", intelligence.SYSTEM_PROMPT)

    def test_draft_without_doc_type(self) -> None:
        card = item_to_action_card({
            "case": "cross_case",
            "source_db": "cross_case",
            "kind": "intersection",
            "item_type": "intersection",
            "item_id": "x-1",
            "title": "Cross item",
        })
        with mock.patch.object(workflow, "suggested_doc_type", return_value=None):
            out = intelligence.draft_from_card(card, include_courtlistener=False)
        self.assertFalse(out["ok"])

    def test_inspect_fact_row_is_review_only(self) -> None:
        row = {
            "atom_id": "ATM-001",
            "fact": "ATM-001: Thursday exchange",
            "review_status": "Unreviewed",
            "case_summary": "Confirm exchange time before drafting.",
            "source_summary": "Parenting plan section V.Q",
            "detail": {"evidence": [{"title": "Parenting plan section V.Q"}]},
            "card": {"source_item": {"source_db": "coparent"}},
        }
        with mock.patch(
            "intelligence.llm_client.generate",
            return_value={
                "ok": True,
                "text": "**Suggested status**: needs_source",
                "model": "llama3.2:3b",
                "provider": "ollama",
                "error": None,
            },
        ), mock.patch("intelligence.gazelle_state.log_activity") as log_activity, mock.patch(
            "intelligence.gazelle_state.set_fact_verification"
        ) as set_status:
            out = intelligence.inspect_fact_row(row)
        self.assertTrue(out["ok"])
        self.assertEqual(out["atom_id"], "ATM-001")
        self.assertEqual(out["context_sources"], ["fact:ATM-001"])
        set_status.assert_not_called()
        log_activity.assert_called_once()


if __name__ == "__main__":
    unittest.main()
