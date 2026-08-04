"""Gates for the terpsi-chat schema.

Run: python3 -m pytest tests/ -q   (from apps/terpsi-chat)

Each test here corresponds to a claim made in PLAN.md. A claim without a gate
below is a wish and should be read as one.

Every gate in this file is checked by test_mutation.py, which deliberately
breaks the mechanism and asserts the gate goes red. A gate that cannot fail is
not a gate, so this file is only meaningful together with that one.

stdlib unittest — pytest is not installed and this should stay dependency-free.
"""

import inspect
import pathlib
import sqlite3
import unittest

from terpsi_chat import notify
from terpsi_chat.schema_surface import EXPECTED_SCHEMA_SURFACE

SCHEMA_PATH = pathlib.Path(__file__).resolve().parents[1] / "terpsi_chat" / "schema.sql"


def build_db(schema_sql: str | None = None, enforce_fks: bool = True) -> sqlite3.Connection:
    """An in-memory database with the schema applied.

    `enforce_fks` exists so test_fk_pragma_is_the_whole_ballgame can show what
    the schema is worth without it. Production code must never pass False; the
    single connection factory sets it once.
    """
    conn = sqlite3.connect(":memory:")
    if enforce_fks:
        conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema_sql if schema_sql is not None else SCHEMA_PATH.read_text())
    return conn


def seed(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        INSERT INTO adults VALUES ('a_tech', 'Tech',    'roster:1', 'measured', '2026-01-01');
        INSERT INTO adults VALUES ('a_dir',  'Director','roster:2', 'measured', '2026-01-01');
        INSERT INTO minors VALUES ('m_jun1', 'Junior1', 'roster:3', 'measured', 'junior', '2026-01-01');
        INSERT INTO minors VALUES ('m_jun2', 'Junior2', 'roster:4', 'measured', 'junior', '2026-01-01');
        INSERT INTO minors VALUES ('m_sen1', 'Senior1', 'roster:5', 'assumed',  'senior', '2026-01-01');
        INSERT INTO minors VALUES ('m_sen2', 'Senior2', 'roster:6', 'assumed',  'senior', '2026-01-01');
        """
    )


def approved_request(conn, a, b, *, guardian=True):
    request_id = f"r_{a}_{b}"
    conn.execute(
        "INSERT INTO peer_channel_requests VALUES (?,?,?,?,?)",
        (request_id, a, b, "2026-02-01", "2026-02-02"),
    )
    if guardian:
        guardian_approves(conn, request_id, b)
    return request_id


def guardian_approves(conn, request_id, counterparty, *, provenance="measured"):
    """Approval and evidence are the same row; there is no way to do one only."""
    conn.execute(
        "INSERT INTO guardian_approval_evidence VALUES (?,?,?,?,?,?,?,?,?)",
        (request_id, "2026-02-03", "guardian:named.person", counterparty,
         "Counterparty As Shown", provenance, "senior", "measured", provenance),
    )


class ContactGraph(unittest.TestCase):
    """No message exists outside an accepted relationship."""

    def test_message_into_nonexistent_channel_is_refused(self):
        conn = build_db()
        seed(conn)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO peer_messages VALUES ('x','no_such_channel','m_sen1','2026-02-01',X'00')"
            )

    def test_peer_channel_needs_a_completed_request(self):
        conn = build_db()
        seed(conn)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO peer_channels (channel_id, low_minor, high_minor, opened_at) "
                "VALUES ('c1','m_sen1','m_sen2','2026-02-01')"
            )

    def test_junior_band_additionally_requires_guardian_approval(self):
        conn = build_db()
        seed(conn)
        request_id = approved_request(conn, "m_jun1", "m_jun2", guardian=False)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO peer_channels (channel_id, low_minor, high_minor, opened_at) "
                "VALUES ('c1','m_jun1','m_jun2','2026-02-01')"
            )
        guardian_approves(conn, request_id, "m_jun2")
        conn.execute(
            "INSERT INTO peer_channels (channel_id, low_minor, high_minor, opened_at) "
            "VALUES ('c1','m_jun1','m_jun2','2026-02-01')"
        )

    def test_senior_band_does_not_require_guardian_approval(self):
        conn = build_db()
        seed(conn)
        approved_request(conn, "m_sen1", "m_sen2", guardian=False)
        conn.execute(
            "INSERT INTO peer_channels (channel_id, low_minor, high_minor, opened_at) "
            "VALUES ('c1','m_sen1','m_sen2','2026-02-01')"
        )

    def test_self_edge_is_unrepresentable(self):
        """Note: enforced twice over — by the ordering CHECK and, independently,
        by the approval trigger finding no matching request (one cannot exist,
        since peer_channel_requests forbids from == to). Kept because the
        property matters, but it is NOT the gate for the ordering CHECK; see
        test_reversed_pair_cannot_duplicate_a_relationship for that.
        """
        conn = build_db()
        seed(conn)
        approved_request(conn, "m_sen1", "m_sen2", guardian=False)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO peer_channels (channel_id, low_minor, high_minor, opened_at) "
                "VALUES ('c0','m_sen1','m_sen1','2026-02-01')"
            )

    def test_duplicate_pair_is_refused(self):
        conn = build_db()
        seed(conn)
        approved_request(conn, "m_sen1", "m_sen2", guardian=False)
        conn.execute(
            "INSERT INTO peer_channels (channel_id, low_minor, high_minor, opened_at) "
            "VALUES ('c1','m_sen1','m_sen2','2026-02-01')"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO peer_channels (channel_id, low_minor, high_minor, opened_at) "
                "VALUES ('c2','m_sen1','m_sen2','2026-02-01')"
            )

    def test_reversed_pair_cannot_duplicate_a_relationship(self):
        """What the canonical ordering CHECK uniquely buys.

        UNIQUE(low_minor, high_minor) does not see (b, a) as a duplicate of
        (a, b), and the approval trigger matches a request in either direction.
        So without the ordering CHECK, one relationship can hold two channel
        rows — and blocking, which is a DELETE from this table, would then
        remove only one of them. This is the gate for that CHECK.
        """
        conn = build_db()
        seed(conn)
        approved_request(conn, "m_sen1", "m_sen2", guardian=False)
        conn.execute(
            "INSERT INTO peer_channels (channel_id, low_minor, high_minor, opened_at) "
            "VALUES ('c1','m_sen1','m_sen2','2026-02-01')"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO peer_channels (channel_id, low_minor, high_minor, opened_at) "
                "VALUES ('c2','m_sen2','m_sen1','2026-02-01')"
            )


class DecisionEvidence(unittest.TestCase):
    """A decision records what the decider was looking at, or it is not a record.

    From the ad-breaks paper, now landed beside playgate in safe-app-store: the
    log's job is not to record what is currently true, but what was known to the
    person who made the decision, at the time they made it. Those diverge
    immediately, and a bare timestamp cannot tell them apart afterwards.
    """

    def test_approval_cannot_be_recorded_without_evidence(self):
        """There is no `guardian_approved_at` column to set on its own."""
        conn = build_db()
        cols = [r[1] for r in conn.execute("PRAGMA table_info(peer_channel_requests)")]
        self.assertNotIn(
            "guardian_approved_at", cols,
            "a bare approval timestamp is back; approval must be the evidence row",
        )

    def test_evidence_is_frozen_not_a_join(self):
        """The snapshot must not track later changes to the counterparty."""
        conn = build_db()
        seed(conn)
        request_id = approved_request(conn, "m_sen1", "m_sen2", guardian=False)
        guardian_approves(conn, request_id, "m_sen2", provenance="assumed")
        # The roster is corrected after the fact — the org learns more.
        conn.execute("UPDATE minors SET roster_provenance='measured' WHERE minor_id='m_sen2'")
        recorded = conn.execute(
            "SELECT counterparty_roster_provenance, decision_provenance "
            "FROM guardian_approval_evidence WHERE request_id=?", (request_id,)
        ).fetchone()
        self.assertEqual(
            recorded, ("assumed", "assumed"),
            "the snapshot moved with the roster — the guardian's decision now "
            "looks better-evidenced than it was, which is the exact rewrite "
            "this table exists to prevent",
        )

    def test_evidence_cannot_be_edited_or_withdrawn(self):
        conn = build_db()
        seed(conn)
        request_id = approved_request(conn, "m_sen1", "m_sen2")
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE guardian_approval_evidence SET decision_provenance='measured'"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM guardian_approval_evidence WHERE request_id=?",
                         (request_id,))

    def test_an_unsupported_provenance_value_is_refused(self):
        conn = build_db()
        seed(conn)
        request_id = approved_request(conn, "m_sen1", "m_sen2", guardian=False)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO guardian_approval_evidence VALUES (?,?,?,?,?,?,?,?,?)",
                (request_id, "2026-02-03", "g", "m_sen2", "Shown",
                 "probably_fine", "senior", "measured", "measured"),
            )

    def test_an_archive_read_must_say_what_was_in_front_of_it(self):
        """Each snapshot column is checked on its own.

        An earlier version omitted all three at once and passed while only one
        was still mandatory — it would have gone green with two of the three
        made optional. Per-column, so a partial regression cannot hide behind
        its neighbours.
        """
        snapshot = {
            "messages_present_at_read": "12",
            "disposals_before_read": "0",
            "archive_state": "'complete'",
        }
        base = {
            "read_id": "'r1'", "channel_id": "'s1'",
            "reader_person_ref": "'named.lead'", "read_at": "'2026-03-01'",
            "stated_reason": "'concern raised'",
        }
        for omitted in snapshot:
            with self.subTest(omitted=omitted):
                conn = build_db()
                seed(conn)
                conn.execute(
                    "INSERT INTO staff_channels "
                    "VALUES ('s1','a_tech','m_sen1','a_dir','2026-02-01')"
                )
                supplied = dict(base, **{k: v for k, v in snapshot.items() if k != omitted})
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(
                        f"INSERT INTO staff_archive_reads ({','.join(supplied)}) "
                        f"VALUES ({','.join(supplied.values())})"
                    )

    def test_unknown_completeness_stays_sayable(self):
        """A reader who cannot establish whether the archive is whole must be
        able to say so, rather than pick one of the confident options."""
        conn = build_db()
        seed(conn)
        conn.execute("INSERT INTO staff_channels VALUES ('s1','a_tech','m_sen1','a_dir','2026-02-01')")
        conn.execute(
            "INSERT INTO staff_archive_reads VALUES "
            "('r1','s1','named.lead','2026-03-01','concern raised',12,0,'unknown')"
        )
        self.assertEqual(
            conn.execute("SELECT archive_state FROM staff_archive_reads").fetchone()[0],
            "unknown",
        )

    def test_a_read_record_cannot_be_edited_or_withdrawn(self):
        conn = build_db()
        seed(conn)
        conn.execute("INSERT INTO staff_channels VALUES ('s1','a_tech','m_sen1','a_dir','2026-02-01')")
        conn.execute(
            "INSERT INTO staff_archive_reads VALUES "
            "('r1','s1','named.lead','2026-03-01','concern raised',12,0,'complete')"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("UPDATE staff_archive_reads SET stated_reason='routine'")
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM staff_archive_reads WHERE read_id='r1'")


class NoPrivateAdultMinorChannel(unittest.TestCase):
    """The load-bearing one. A two-party adult-minor channel has no form."""

    def test_witness_is_mandatory(self):
        conn = build_db()
        seed(conn)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO staff_channels (channel_id, adult_id, minor_id, witness_adult_id, opened_at) "
                "VALUES ('s1','a_tech','m_sen1',NULL,'2026-02-01')"
            )

    def test_adult_cannot_witness_themselves(self):
        conn = build_db()
        seed(conn)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO staff_channels VALUES ('s1','a_tech','m_sen1','a_tech','2026-02-01')"
            )

    def test_witnessed_channel_is_permitted(self):
        conn = build_db()
        seed(conn)
        conn.execute(
            "INSERT INTO staff_channels VALUES ('s1','a_tech','m_sen1','a_dir','2026-02-01')"
        )


class ContentSeparation(unittest.TestCase):
    """Enumerated over the live schema, so a column added next year fails.

    Two complementary gates. The token one states the intent and survives
    refactoring; the snapshot one has no heuristic and therefore no false
    negatives. Neither alone is enough: a careless snapshot update would slip a
    content column past the second, and a camelCase name would slip past the
    first.

    An early draft of the token gate matched substrings and flagged
    `ciphertext` (contains "text") and `message_id` (contains "message") — it
    failed on exactly the columns that demonstrate the design working. Matching
    on underscore-delimited tokens is the fix; noting it because a substring
    check here looks correct and is not.
    """

    # The complete set of places plaintext message content may live.
    PLAINTEXT_ALLOWLIST = {("staff_messages", "body")}
    CONTENT_TOKENS = {"body", "text", "content", "plaintext", "preview", "subject", "snippet", "msg"}

    def _columns(self, conn):
        objs = conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
        ).fetchall()
        for (name,) in objs:
            for row in conn.execute(f"PRAGMA table_info({name})"):
                yield name, row[1]

    def test_no_plaintext_column_outside_the_allowlist(self):
        conn = build_db()
        found = {
            (t, c) for t, c in self._columns(conn)
            if self.CONTENT_TOKENS & set(c.lower().split("_"))
        }
        self.assertEqual(
            found, self.PLAINTEXT_ALLOWLIST,
            "a column that looks like it holds message content appeared outside "
            "staff_messages.body — peer content must never be stored in plaintext",
        )

    def test_schema_surface_is_unchanged(self):
        """Every column in the schema, pinned.

        Deliberately noisy: any schema change fails this until someone updates
        the snapshot on purpose. That is the point — this surface holds
        children's communications, so a column arriving without a human
        noticing is the failure being prevented.
        """
        conn = build_db()
        self.assertEqual(len(set(self._columns(conn))), 93)
        self.assertEqual(
            sorted(self._columns(conn)), sorted(EXPECTED_SCHEMA_SURFACE)
        )

    def test_peer_messages_columns_are_exactly_as_designed(self):
        conn = build_db()
        cols = [r[1] for r in conn.execute("PRAGMA table_info(peer_messages)")]
        self.assertEqual(
            cols, ["message_id", "channel_id", "sender_minor_id", "sent_at", "ciphertext"]
        )

    def test_guardian_view_exposes_structure_only(self):
        conn = build_db()
        cols = [r[1] for r in conn.execute("PRAGMA table_info(guardian_visible_structure)")]
        self.assertNotIn("ciphertext", cols)
        self.assertEqual(
            cols,
            ["channel_id", "low_minor", "high_minor", "opened_at",
             "message_count", "first_at", "last_at"],
        )

    def test_shielded_edges_are_absent_from_the_guardian_view(self):
        conn = build_db()
        seed(conn)
        approved_request(conn, "m_sen1", "m_sen2", guardian=False)
        conn.execute(
            "INSERT INTO peer_channels (channel_id, low_minor, high_minor, opened_at, shielded_by_minor) "
            "VALUES ('c1','m_sen1','m_sen2','2026-02-01',1)"
        )
        rows = conn.execute("SELECT * FROM guardian_visible_structure").fetchall()
        self.assertEqual(rows, [])


class IdentitySpaceMigration(unittest.TestCase):
    """The alumnus-turned-tech case: peer edges must be resolved, not inherited.

    Alumni come back as techs at eighteen or nineteen, still socially peers with
    current students. Their existing minor<->minor edges were never created as
    adult-minor channels and would not satisfy the witness constraint, so the
    migration is where "no private adult-minor channel" quietly fails. The FKs
    into `minors` make that impossible: the row cannot leave the minor space
    until every reference to it is resolved.

    Writing this test surfaced a reference I had not accounted for.
    `peer_channel_requests` also points at `minors`, so a *pending* request is
    an unresolved edge too — closing the channels is not sufficient. A migration
    routine that only swept `peer_channels` would have been refused by the
    database, which is the outcome the design wants and is why the constraint
    lives there rather than in the routine. `guardian_links`,
    `guardian_observations` and `observation_capability` reference `minors` as
    well; see PLAN.md for what should happen to each on migration, which is a
    decision and not yet made.
    """

    def test_minor_with_live_peer_edges_cannot_be_removed(self):
        conn = build_db()
        seed(conn)
        approved_request(conn, "m_sen1", "m_sen2", guardian=False)
        conn.execute(
            "INSERT INTO peer_channels (channel_id, low_minor, high_minor, opened_at) "
            "VALUES ('c1','m_sen1','m_sen2','2026-02-01')"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM minors WHERE minor_id='m_sen1'")

    def test_migration_succeeds_once_edges_are_resolved(self):
        conn = build_db()
        seed(conn)
        approved_request(conn, "m_sen1", "m_sen2", guardian=False)
        conn.execute(
            "INSERT INTO peer_channels (channel_id, low_minor, high_minor, opened_at) "
            "VALUES ('c1','m_sen1','m_sen2','2026-02-01')"
        )
        conn.execute("DELETE FROM peer_channels WHERE channel_id='c1'")
        # Not sufficient on its own — a pending request is an unresolved edge.
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM minors WHERE minor_id='m_sen1'")
        conn.execute("DELETE FROM peer_channel_requests WHERE from_minor='m_sen1' OR to_minor='m_sen1'")
        conn.execute("DELETE FROM minors WHERE minor_id='m_sen1'")
        conn.execute(
            "INSERT INTO adults VALUES ('a_sen1','Senior1','roster:5','measured','2026-09-01')"
        )


class Retention(unittest.TestCase):
    def _staff_message(self, conn):
        conn.execute("INSERT INTO staff_channels VALUES ('s1','a_tech','m_sen1','a_dir','2026-02-01')")
        conn.execute("INSERT INTO staff_messages VALUES ('sm1','s1','a_tech','2026-02-02','logistics')")

    def test_silent_disposal_is_refused(self):
        conn = build_db()
        seed(conn)
        self._staff_message(conn)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM staff_messages WHERE message_id='sm1'")

    def test_disposal_with_an_authorised_record_succeeds_and_the_record_survives(self):
        conn = build_db()
        seed(conn)
        self._staff_message(conn)
        conn.execute(
            "INSERT INTO retention_disposals VALUES ('sm1','named.person','2027-01-01','stated basis')"
        )
        conn.execute("DELETE FROM staff_messages WHERE message_id='sm1'")
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM retention_disposals").fetchone()[0], 1
        )


class OutboundNotice(unittest.TestCase):
    def test_no_template_can_carry_content(self):
        for key, body in notify.NOTICE_TEMPLATES.items():
            for marker in notify._PLACEHOLDER_MARKERS:
                self.assertNotIn(marker, body, f"template {key!r} has an interpolation point")

    def test_render_notice_has_nowhere_to_put_content(self):
        params = list(inspect.signature(notify.render_notice).parameters)
        self.assertEqual(
            params, ["template_key"],
            "render_notice grew a parameter — content is one argument away from SMS",
        )

    def test_unknown_template_is_refused_rather_than_improvised(self):
        with self.assertRaises(notify.NoticeTemplateError):
            notify.render_notice("urgent_from_coach")


class AbsenceIsRecorded(unittest.TestCase):
    def test_no_capability_is_a_storable_value_distinct_from_no_rows(self):
        conn = build_db()
        seed(conn)
        conn.execute(
            "INSERT INTO observation_capability VALUES "
            "('m_sen1','2026-02-01','2026-02-28','no_capability','peer content is E2EE; org cannot observe')"
        )
        row = conn.execute(
            "SELECT capability FROM observation_capability WHERE minor_id='m_sen1'"
        ).fetchone()
        self.assertEqual(row[0], "no_capability")

    def test_an_unsupported_capability_value_is_refused(self):
        conn = build_db()
        seed(conn)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO observation_capability VALUES "
                "('m_sen1','2026-03-01','2026-03-31','all_clear','')"
            )


class SqliteHazard(unittest.TestCase):
    def test_fk_pragma_is_the_whole_ballgame(self):
        """Without the pragma, the referential guarantees are decorative.

        This is not a hypothetical. SQLite defaults foreign_keys to OFF, per
        connection. One connection opened without it and the contact-graph
        guarantee silently stops holding, with no error anywhere.
        """
        conn = build_db(enforce_fks=False)
        seed(conn)
        conn.execute(
            "INSERT INTO peer_messages VALUES ('x','no_such_channel','m_sen1','2026-02-01',X'00')"
        )
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM peer_messages").fetchone()[0], 1,
            "expected the unenforced case to accept an orphan row",
        )
        enforced = build_db(enforce_fks=True)
        self.assertEqual(
            enforced.execute("PRAGMA foreign_keys").fetchone()[0], 1
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
