"""Mutation harness — proves the gates in test_gates.py can actually fail.

Run: python3 -m pytest tests/ -q   (from apps/terpsi-chat)

A gate that cannot fail is not a gate. A green suite proves the tests ran, not
that they are load-bearing; the only way to know a constraint is doing work is
to remove it and watch the suite notice.

Each entry below removes exactly one mechanism from the schema (or from
notify.py) and asserts that the named gate goes red. If a mutation is applied
and the gate still passes, that gate is decoration and this harness fails.

Two failure modes this harness guards against in itself:
  - A mutation whose string replacement silently does not match, leaving the
    schema unchanged. Asserted against directly.
  - A mutation so broad that the gate fails for an unrelated reason. Mitigated
    by keeping each replacement minimal and targeted at one constraint.
"""

import io
import pathlib
import tempfile
import unittest

from tests import test_gates

SCHEMA = (pathlib.Path(__file__).resolve().parents[1] / "terpsi_chat" / "schema.sql").read_text()


# (label, gate to run, text to remove/replace, replacement, occurrences)
#
# `occurrences` is -1 for "every match". Getting this wrong is quiet and
# dangerous: an early version replaced only the first match everywhere, so the
# minors-FK mutation stripped one foreign key of four, the delete stayed blocked
# by the survivors, and the gate looked like it had caught a mechanism removal
# it had never actually seen removed.
SCHEMA_MUTATIONS = [
    (
        "witness becomes optional",
        "NoPrivateAdultMinorChannel.test_witness_is_mandatory",
        "witness_adult_id TEXT NOT NULL REFERENCES adults(adult_id),",
        "witness_adult_id TEXT REFERENCES adults(adult_id),",
        1,
    ),
    (
        "an adult may witness themselves",
        "NoPrivateAdultMinorChannel.test_adult_cannot_witness_themselves",
        "CHECK (witness_adult_id <> adult_id),",
        "",
        1,
    ),
    (
        "peer messages lose their channel foreign key",
        "ContactGraph.test_message_into_nonexistent_channel_is_refused",
        "channel_id      TEXT NOT NULL REFERENCES peer_channels(channel_id),",
        "channel_id      TEXT NOT NULL,",
        1,
    ),
    (
        "the approval trigger is dropped",
        "ContactGraph.test_peer_channel_needs_a_completed_request",
        "BEFORE INSERT ON peer_channels",
        "BEFORE INSERT ON peer_channel_requests",
        1,
    ),
    (
        "the junior band no longer pulls in guardian approval",
        "ContactGraph.test_junior_band_additionally_requires_guardian_approval",
        "AND m.band = 'junior'",
        "AND m.band = 'no_such_band'",
        1,
    ),
    (
        "peer_messages grows a plaintext column",
        "ContentSeparation.test_no_plaintext_column_outside_the_allowlist",
        "ciphertext      BLOB NOT NULL",
        "ciphertext      BLOB NOT NULL,\n  body            TEXT",
        1,
    ),
    (
        "peer_messages grows a plaintext column (surface snapshot)",
        "ContentSeparation.test_schema_surface_is_unchanged",
        "ciphertext      BLOB NOT NULL",
        "ciphertext      BLOB NOT NULL,\n  body            TEXT",
        1,
    ),
    (
        "peer_messages grows a plaintext column (exact column list)",
        "ContentSeparation.test_peer_messages_columns_are_exactly_as_designed",
        "ciphertext      BLOB NOT NULL",
        "ciphertext      BLOB NOT NULL,\n  body            TEXT",
        1,
    ),
    (
        "the guardian view is widened to content",
        "ContentSeparation.test_guardian_view_exposes_structure_only",
        "  MAX(m.sent_at)      AS last_at",
        "  MAX(m.sent_at)      AS last_at,\n  MAX(m.ciphertext)   AS ciphertext",
        1,
    ),
    (
        "the guardian view stops honouring shielding",
        "ContentSeparation.test_shielded_edges_are_absent_from_the_guardian_view",
        "WHERE c.shielded_by_minor = 0",
        "",
        1,
    ),
    (
        "the retention trigger is dropped",
        "Retention.test_silent_disposal_is_refused",
        "BEFORE DELETE ON staff_messages",
        "BEFORE DELETE ON retention_disposals",
        1,
    ),
    (
        "canonical pair ordering is dropped",
        "ContactGraph.test_reversed_pair_cannot_duplicate_a_relationship",
        "CHECK (low_minor < high_minor),",
        "",
        1,
    ),
    (
        "the duplicate-pair unique constraint is dropped",
        "ContactGraph.test_duplicate_pair_is_refused",
        "UNIQUE (low_minor, high_minor)",
        "",
        1,
    ),
    (
        "observation capability accepts any value",
        "AbsenceIsRecorded.test_an_unsupported_capability_value_is_refused",
        "CHECK (capability IN ('observed', 'no_capability', 'capability_declined')),",
        "",
        1,
    ),
    (
        "minors lose referential protection, so migration can strand edges",
        "IdentitySpaceMigration.test_minor_with_live_peer_edges_cannot_be_removed",
        "REFERENCES minors(minor_id)",
        "",
        -1,
    ),
    (
        "a bare approval timestamp comes back",
        "DecisionEvidence.test_approval_cannot_be_recorded_without_evidence",
        "  counterparty_accepted_at TEXT,",
        "  counterparty_accepted_at TEXT,\n  guardian_approved_at     TEXT,",
        1,
    ),
    (
        "approval no longer has to carry evidence",
        "ContactGraph.test_junior_band_additionally_requires_guardian_approval",
        "AND (EXISTS (SELECT 1 FROM guardian_approval_evidence e\n                 WHERE e.request_id = r.request_id)",
        "AND (1 = 1",
        1,
    ),
    (
        "evidence is kept in sync with the roster instead of frozen",
        "DecisionEvidence.test_evidence_is_frozen_not_a_join",
        "CREATE TRIGGER guardian_approval_evidence_no_update\nBEFORE UPDATE ON guardian_approval_evidence\nBEGIN\n  SELECT RAISE(ABORT, 'approval evidence is append-only; record a correction beside it');\nEND;",
        "CREATE TRIGGER guardian_approval_evidence_helpfully_resyncs\n"
        "AFTER UPDATE OF roster_provenance ON minors\n"
        "BEGIN\n"
        "  UPDATE guardian_approval_evidence\n"
        "     SET counterparty_roster_provenance = NEW.roster_provenance,\n"
        "         decision_provenance            = NEW.roster_provenance\n"
        "   WHERE counterparty_minor_id = NEW.minor_id;\n"
        "END;",
        1,
    ),
    (
        "approval evidence becomes editable",
        "DecisionEvidence.test_evidence_cannot_be_edited_or_withdrawn",
        "BEFORE UPDATE ON guardian_approval_evidence",
        "BEFORE UPDATE ON retention_disposals",
        1,
    ),
    (
        "an archive read need not say what was in front of it",
        "DecisionEvidence.test_an_archive_read_must_say_what_was_in_front_of_it",
        "  messages_present_at_read INTEGER NOT NULL CHECK (messages_present_at_read >= 0),",
        "  messages_present_at_read INTEGER CHECK (messages_present_at_read >= 0),",
        1,
    ),
    (
        "'unknown' completeness stops being sayable",
        "DecisionEvidence.test_unknown_completeness_stays_sayable",
        "                           CHECK (archive_state IN ('complete',\n                                                    'disposals_recorded',\n                                                    'unknown'))",
        "                           CHECK (archive_state IN ('complete',\n                                                    'disposals_recorded'))",
        1,
    ),
    (
        "a read record becomes editable",
        "DecisionEvidence.test_a_read_record_cannot_be_edited_or_withdrawn",
        "BEFORE UPDATE ON staff_archive_reads",
        "BEFORE UPDATE ON outbound_notices",
        1,
    ),
]


def run_gate(gate: str) -> unittest.TestResult:
    suite = unittest.TestLoader().loadTestsFromName(gate, module=test_gates)
    return unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)


class MutationsAreCaught(unittest.TestCase):
    def test_every_mechanism_has_a_gate_that_notices_its_removal(self):
        original = test_gates.SCHEMA_PATH
        failures = []
        try:
            for label, gate, find, replace, count in SCHEMA_MUTATIONS:
                self.assertIn(find, SCHEMA, f"mutation {label!r} no longer matches the schema")
                mutated = SCHEMA.replace(find, replace, count)
                self.assertNotEqual(mutated, SCHEMA, f"mutation {label!r} changed nothing")

                with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False) as fh:
                    fh.write(mutated)
                    test_gates.SCHEMA_PATH = pathlib.Path(fh.name)

                result = run_gate(gate)
                if result.wasSuccessful():
                    failures.append(f"  {gate}\n    still passed after: {label}")
        finally:
            test_gates.SCHEMA_PATH = original

        self.assertEqual(
            failures, [],
            "these gates did not notice their mechanism being removed, so they "
            "are not gates:\n" + "\n".join(failures),
        )

    def test_the_unmutated_schema_passes_every_mutated_gate(self):
        """Control. Without this, a gate that fails unconditionally would look
        like a working gate above."""
        for label, gate, _find, _replace, _count in SCHEMA_MUTATIONS:
            result = run_gate(gate)
            self.assertTrue(
                result.wasSuccessful(),
                f"{gate} fails even unmutated, so its result above is meaningless "
                f"(paired with mutation {label!r})",
            )


class NotifyMutationsAreCaught(unittest.TestCase):
    def test_a_template_placeholder_is_caught(self):
        original = test_gates.notify.NOTICE_TEMPLATES
        try:
            test_gates.notify.NOTICE_TEMPLATES = dict(
                original, waiting="{sender} sent you a message: {preview}"
            )
            result = run_gate("OutboundNotice.test_no_template_can_carry_content")
            self.assertFalse(
                result.wasSuccessful(),
                "an SMS template with interpolation points was not caught",
            )
        finally:
            test_gates.notify.NOTICE_TEMPLATES = original

    def test_a_widened_render_signature_is_caught(self):
        original = test_gates.notify.render_notice
        try:
            test_gates.notify.render_notice = lambda template_key, preview=None: ""
            result = run_gate("OutboundNotice.test_render_notice_has_nowhere_to_put_content")
            self.assertFalse(
                result.wasSuccessful(),
                "render_notice growing a content parameter was not caught",
            )
        finally:
            test_gates.notify.render_notice = original


if __name__ == "__main__":
    unittest.main(verbosity=2)
