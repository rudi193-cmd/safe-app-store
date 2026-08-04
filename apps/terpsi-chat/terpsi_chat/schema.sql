-- terpsi-chat — schema stub
--
-- Target: SQLite on the org's LAN box. Postgres differences noted inline.
--
-- The design rule this file exists to serve: a safety property is expressed as
-- something the database cannot represent, not as something the application
-- promises to avoid. Where a property is NOT enforced here, it says so.
--
-- !! HAZARD, READ FIRST !!
-- SQLite enforces foreign keys only when `PRAGMA foreign_keys = ON` is set, per
-- connection, and it is OFF by default. Several guarantees below are FKs. On a
-- connection without that pragma they are decorative. There is no way to bind
-- the pragma to the schema, so it must be set in exactly one connection factory
-- and asserted by a gate (see test_gates.py::test_fk_pragma_is_the_whole_ballgame).
-- Postgres has no equivalent hazard; FKs there are always enforced.

-- ---------------------------------------------------------------------------
-- 1. Identity — two spaces, two tables
-- ---------------------------------------------------------------------------
-- Adults and minors are separate tables rather than one table with a role
-- column. This is what makes the adult/minor channel constraint structural: a
-- channel table's FK targets decide who can appear in it, so a mis-typed edge
-- has nowhere to be stored. A discriminator column would push that decision
-- into every query.
--
-- roster_provenance carries how well the org actually knows this row.
-- 'measured' = traced to an enrolment record a person can look up.
-- 'assumed'  = someone typed it in. Most spreadsheet-maintained rosters are this.
-- A result is worth its weakest input; the guardian binding below is worth this.

CREATE TABLE adults (
  adult_id          TEXT PRIMARY KEY,
  display_name      TEXT NOT NULL,
  roster_ref        TEXT NOT NULL,
  roster_provenance TEXT NOT NULL
                    CHECK (roster_provenance IN ('measured', 'fitted', 'assumed')),
  joined_at         TEXT NOT NULL
);

CREATE TABLE minors (
  minor_id          TEXT PRIMARY KEY,
  display_name      TEXT NOT NULL,
  roster_ref        TEXT NOT NULL,
  roster_provenance TEXT NOT NULL
                    CHECK (roster_provenance IN ('measured', 'fitted', 'assumed')),
  -- Age band sets the DEFAULT scope of guardian structural visibility and
  -- whether guardian approval gates new peer contact. It is a default on scope,
  -- not a different system, so the 12->13 transition is a value change rather
  -- than a migration.
  band              TEXT NOT NULL CHECK (band IN ('junior', 'senior')),
  joined_at         TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- 2. Guardian binding — a named person, inherited from the org roster
-- ---------------------------------------------------------------------------
-- The org already established who this is, offline, with accountability. We
-- inherit that verification and we inherit its errors: custody arrangements,
-- protective orders, a situation that changed mid-season. Hence provenance.
--
-- Named person, never a role. Role-shaped guardianship is how a new partner or
-- a controlling relative inherits visibility nobody consciously granted.

CREATE TABLE guardian_links (
  minor_id              TEXT NOT NULL REFERENCES minors(minor_id),
  guardian_person_ref   TEXT NOT NULL,
  guardian_display_name TEXT NOT NULL,
  provenance            TEXT NOT NULL
                        CHECK (provenance IN ('measured', 'fitted', 'assumed')),
  established_at        TEXT NOT NULL,
  PRIMARY KEY (minor_id, guardian_person_ref)
);

-- Changes of guardian are loud by construction: the event log is append-only
-- and sits beside the link table, so a correction never overwrites the record
-- of what the binding used to be.
CREATE TABLE guardian_link_events (
  event_id            TEXT PRIMARY KEY,
  minor_id            TEXT NOT NULL REFERENCES minors(minor_id),
  guardian_person_ref TEXT NOT NULL,
  action              TEXT NOT NULL CHECK (action IN ('established', 'revoked', 'scope_changed')),
  occurred_at         TEXT NOT NULL,
  actor_ref           TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- 3. Channel classes — three shapes, three different sets of properties
-- ---------------------------------------------------------------------------

-- 3a. peer: minor <-> minor. Private, end-to-end encrypted, NOT retained by
--     the org. The org is not the custodian of children's private chat.
--
-- This table IS the accepted state. There is no `state` column to check,
-- because a row existing is what "accepted" means; the FK from peer_messages
-- then does the enforcement for every write path, including ones not yet
-- written. Blocking is a DELETE from here.
CREATE TABLE peer_channels (
  channel_id         TEXT PRIMARY KEY,
  low_minor          TEXT NOT NULL REFERENCES minors(minor_id),
  high_minor         TEXT NOT NULL REFERENCES minors(minor_id),
  opened_at          TEXT NOT NULL,
  -- Young person may shield a specific edge from the guardian structural view.
  -- OPEN DECISION: whether the COUNT of shielded edges is itself visible. It is
  -- a signal either way; see PLAN.md. Currently the view exposes the count.
  shielded_by_minor  INTEGER NOT NULL DEFAULT 0 CHECK (shielded_by_minor IN (0, 1)),
  -- Canonical ordering: one row per pair, and a self-edge is unrepresentable.
  CHECK (low_minor < high_minor),
  UNIQUE (low_minor, high_minor)
);

-- The door into peer_channels is multi-signature. Requests accumulate
-- approvals here; nothing becomes a channel until the set is complete.
CREATE TABLE peer_channel_requests (
  request_id               TEXT PRIMARY KEY,
  from_minor               TEXT NOT NULL REFERENCES minors(minor_id),
  to_minor                 TEXT NOT NULL REFERENCES minors(minor_id),
  requested_at             TEXT NOT NULL,
  counterparty_accepted_at TEXT,
  CHECK (from_minor <> to_minor)
);

-- Guardian approval IS this row. There is deliberately no
-- `guardian_approved_at` column on the request: a bare timestamp records that
-- a decision happened and nothing about what the person deciding was looking
-- at, and those diverge immediately.
--
-- The log's job is not to record what is currently true about a young person;
-- it is to record what was known to the guardian at the moment they decided.
-- A guardian who approved on an `assumed` roster entry that later turned out
-- wrong made a reasonable decision on thin evidence — not a mistake
-- retroactively made to look like negligence, and not a good call
-- retroactively made to look like foresight. Only a snapshot keeps that
-- legible.
--
-- Making approval and evidence the same row is what stops the evidence being
-- the field everyone forgets. Same move as peer_channels being the accepted
-- state rather than a status column.
CREATE TABLE guardian_approval_evidence (
  request_id                     TEXT PRIMARY KEY
                                 REFERENCES peer_channel_requests(request_id),
  approved_at                    TEXT NOT NULL,
  guardian_person_ref            TEXT NOT NULL,
  -- The counterparty AS SHOWN, frozen. Not a join to minors — that would
  -- resolve to today's values and defeat the entire point.
  counterparty_minor_id          TEXT NOT NULL,
  counterparty_display_name      TEXT NOT NULL,
  counterparty_roster_provenance TEXT NOT NULL
                                 CHECK (counterparty_roster_provenance
                                        IN ('measured', 'fitted', 'assumed')),
  counterparty_band              TEXT NOT NULL
                                 CHECK (counterparty_band IN ('junior', 'senior')),
  -- How well the org knew this guardian was this young person's guardian, at
  -- the time it let them decide. The weakest input the decision rests on.
  guardian_link_provenance       TEXT NOT NULL
                                 CHECK (guardian_link_provenance
                                        IN ('measured', 'fitted', 'assumed')),
  -- min() across the two above, stored rather than derived, because deriving
  -- it later would derive it from today's values.
  decision_provenance            TEXT NOT NULL
                                 CHECK (decision_provenance
                                        IN ('measured', 'fitted', 'assumed'))
);

-- Required approvals: counterparty always; guardian additionally if either
-- party is in the junior band. Expressed here rather than in service code so
-- it holds for every insert path.
CREATE TRIGGER peer_channels_require_completed_request
BEFORE INSERT ON peer_channels
WHEN NOT EXISTS (
  SELECT 1 FROM peer_channel_requests r
  WHERE ((r.from_minor = NEW.low_minor  AND r.to_minor = NEW.high_minor)
      OR (r.from_minor = NEW.high_minor AND r.to_minor = NEW.low_minor))
    AND r.counterparty_accepted_at IS NOT NULL
    AND (EXISTS (SELECT 1 FROM guardian_approval_evidence e
                 WHERE e.request_id = r.request_id)
         OR (SELECT COUNT(*) FROM minors m
             WHERE m.minor_id IN (NEW.low_minor, NEW.high_minor)
               AND m.band = 'junior') = 0)
)
BEGIN
  SELECT RAISE(ABORT, 'peer channel requires a request with the full approval set');
END;

-- Evidence is append-only. A correction lands beside the record, never on top
-- of it: a log that can quietly overwrite its own mistakes can confirm the
-- current answer but cannot be used to check whether the reasoning was sound.
CREATE TRIGGER guardian_approval_evidence_no_update
BEFORE UPDATE ON guardian_approval_evidence
BEGIN
  SELECT RAISE(ABORT, 'approval evidence is append-only; record a correction beside it');
END;

CREATE TRIGGER guardian_approval_evidence_no_delete
BEFORE DELETE ON guardian_approval_evidence
BEGIN
  SELECT RAISE(ABORT, 'approval evidence is append-only; it cannot be withdrawn');
END;

-- 3b. staff: adult -> minor. An ORGANISATIONAL RECORD, not private
--     correspondence. Retained, readable by a named safeguarding lead, and
--     both parties know that at the time they write. The knowing is the
--     preventive mechanism; the retention is the fallback for when prevention
--     failed.
--
-- witness_adult_id is NOT NULL and must differ from the sender. That pair of
-- constraints is the whole "no private adult-minor channel" guarantee: a
-- two-party adult-minor channel has no representable form in this schema.
-- This is two-deep leadership, which the org already practises offline.
CREATE TABLE staff_channels (
  channel_id       TEXT PRIMARY KEY,
  adult_id         TEXT NOT NULL REFERENCES adults(adult_id),
  minor_id         TEXT NOT NULL REFERENCES minors(minor_id),
  witness_adult_id TEXT NOT NULL REFERENCES adults(adult_id),
  opened_at        TEXT NOT NULL,
  CHECK (witness_adult_id <> adult_id),
  UNIQUE (adult_id, minor_id)
);

-- 3c. adult <-> adult: ordinary org comms, no special handling.
CREATE TABLE adult_channels (
  channel_id TEXT PRIMARY KEY,
  low_adult  TEXT NOT NULL REFERENCES adults(adult_id),
  high_adult TEXT NOT NULL REFERENCES adults(adult_id),
  opened_at  TEXT NOT NULL,
  CHECK (low_adult < high_adult),
  UNIQUE (low_adult, high_adult)
);

-- ---------------------------------------------------------------------------
-- 4. Messages — one table per class, because the classes differ in kind
-- ---------------------------------------------------------------------------
-- A single messages table with a nullable body and a nullable ciphertext would
-- make "peer messages are never stored in plaintext" a matter of which column
-- the application happened to fill. Separate tables make it a matter of which
-- columns exist.

-- peer_messages has NO plaintext column. Not "must not be used" — absent.
-- test_gates.py enumerates this table's columns against an allowlist, so
-- adding one next year fails the suite rather than passing unnoticed.
CREATE TABLE peer_messages (
  message_id      TEXT PRIMARY KEY,
  channel_id      TEXT NOT NULL REFERENCES peer_channels(channel_id),
  sender_minor_id TEXT NOT NULL REFERENCES minors(minor_id),
  sent_at         TEXT NOT NULL,
  ciphertext      BLOB NOT NULL
);

-- staff_messages holds retained plaintext, deliberately. Encrypting it to a
-- key the org holds anyway would be theatre.
CREATE TABLE staff_messages (
  message_id TEXT PRIMARY KEY,
  channel_id TEXT NOT NULL REFERENCES staff_channels(channel_id),
  sender_ref TEXT NOT NULL,
  sent_at    TEXT NOT NULL,
  body       TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- 5. Reading the retained record — named person, logged, visible
-- ---------------------------------------------------------------------------
-- "Safeguarding lead" as a role means whoever holds the role inherits a
-- searchable archive of children's messages, and role membership drifts.
-- A read is an event with a person's name on it, and the young person can see
-- that it happened.
-- The same snapshot discipline as guardian approval, for the same reason. A
-- read of a complete archive and a read of one that has already had messages
-- disposed of are different events, and six months later nothing distinguishes
-- them unless it was written down at the time.
CREATE TABLE staff_archive_reads (
  read_id                  TEXT PRIMARY KEY,
  channel_id               TEXT NOT NULL REFERENCES staff_channels(channel_id),
  reader_person_ref        TEXT NOT NULL,
  read_at                  TEXT NOT NULL,
  stated_reason            TEXT NOT NULL,
  -- What was actually in front of the reader.
  messages_present_at_read INTEGER NOT NULL CHECK (messages_present_at_read >= 0),
  disposals_before_read    INTEGER NOT NULL CHECK (disposals_before_read >= 0),
  -- 'unknown' is a real answer and must stay sayable: a reader who could not
  -- establish whether the archive was whole has to be able to record that,
  -- rather than pick one of the two confident options.
  archive_state            TEXT NOT NULL
                           CHECK (archive_state IN ('complete',
                                                    'disposals_recorded',
                                                    'unknown'))
);

CREATE TRIGGER staff_archive_reads_no_update
BEFORE UPDATE ON staff_archive_reads
BEGIN
  SELECT RAISE(ABORT, 'a read record is append-only; record a correction beside it');
END;

CREATE TRIGGER staff_archive_reads_no_delete
BEFORE DELETE ON staff_archive_reads
BEGIN
  SELECT RAISE(ABORT, 'a read record is append-only; a read cannot be un-happened');
END;

-- ---------------------------------------------------------------------------
-- 6. Retention — minimisation is ACTIVELY WRONG for the staff class
-- ---------------------------------------------------------------------------
-- Disclosure of abuse routinely happens years to decades later. A tidy expiry
-- is, in practice, a mechanism that destroys the relevant records on schedule.
-- So deletion is not blocked outright (that would be undeliverable) but it is
-- made loud: a disposal record must exist first, and it survives the deletion.
--
-- LEGAL: this collides with data-minimisation duties. Unresolved — the egress
-- policy blocked primary-source retrieval. See PLAN.md "What is not sourced".
CREATE TABLE retention_disposals (
  message_id     TEXT PRIMARY KEY,
  authorised_by  TEXT NOT NULL,
  authorised_at  TEXT NOT NULL,
  stated_basis   TEXT NOT NULL
);

CREATE TRIGGER staff_messages_no_silent_delete
BEFORE DELETE ON staff_messages
WHEN NOT EXISTS (SELECT 1 FROM retention_disposals d WHERE d.message_id = OLD.message_id)
BEGIN
  SELECT RAISE(ABORT, 'staff message disposal requires an authorised retention_disposals record');
END;

-- ---------------------------------------------------------------------------
-- 7. Guardian visibility — structure, never content
-- ---------------------------------------------------------------------------
-- The guardian surface is this view and nothing else. It does not reference
-- peer_messages.ciphertext, and a gate asserts its column set, so widening it
-- is a test failure rather than a quiet change.
--
-- Note this leaks by design: the EXISTENCE of an edge is itself a disclosure.
-- A new contact can out a young person. shielded_by_minor is the partial
-- mitigation, and it is a compromise, not a solve.
CREATE VIEW guardian_visible_structure AS
SELECT
  c.channel_id,
  c.low_minor,
  c.high_minor,
  c.opened_at,
  COUNT(m.message_id) AS message_count,
  MIN(m.sent_at)      AS first_at,
  MAX(m.sent_at)      AS last_at
FROM peer_channels c
LEFT JOIN peer_messages m ON m.channel_id = c.channel_id
WHERE c.shielded_by_minor = 0
GROUP BY c.channel_id, c.low_minor, c.high_minor, c.opened_at;

-- Symmetry is the thing that separates a safety feature from surveillance:
-- whatever the guardian sees, the young person sees, including the fact that
-- the guardian looked. One table, read by both roles.
CREATE TABLE guardian_observations (
  observation_id      TEXT PRIMARY KEY,
  minor_id            TEXT NOT NULL REFERENCES minors(minor_id),
  guardian_person_ref TEXT NOT NULL,
  observed_at         TEXT NOT NULL,
  scope               TEXT NOT NULL CHECK (scope IN ('structure', 'contact_events'))
);

-- ---------------------------------------------------------------------------
-- 8. Absence is a recorded value, not a missing row
-- ---------------------------------------------------------------------------
-- "Nothing concerning was observed" and "there was no capability to observe"
-- are different facts. Without this table the second silently reports as the
-- first, and gets quoted to a parent or a court as reassurance it was never
-- entitled to be. Cheap now, impossible to retrofit after four documents have
-- quoted the reassuring version.
CREATE TABLE observation_capability (
  minor_id     TEXT NOT NULL REFERENCES minors(minor_id),
  period_start TEXT NOT NULL,
  period_end   TEXT NOT NULL,
  capability   TEXT NOT NULL
               CHECK (capability IN ('observed', 'no_capability', 'capability_declined')),
  note         TEXT NOT NULL,
  PRIMARY KEY (minor_id, period_start)
);

-- ---------------------------------------------------------------------------
-- 9. Outbound notification — pointer only
-- ---------------------------------------------------------------------------
-- The single outbound to home base triggers an SMS saying something is waiting.
-- The SMS carries no content, no sender identity, no subject. This table holds
-- what was sent so the fixed-string property is auditable after the fact;
-- notify.py holds the mechanism. See its docstring for why this will be under
-- constant pressure to grow a preview.
CREATE TABLE outbound_notices (
  notice_id     TEXT PRIMARY KEY,
  recipient_ref TEXT NOT NULL,
  template_key  TEXT NOT NULL,
  sent_at       TEXT NOT NULL
);
