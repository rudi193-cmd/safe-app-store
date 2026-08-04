-- ============================================================
-- The Intake Desk — schema
-- docs/specs/intake_desk_spec.md §4
--
-- Local-first SQLite. Zero Willow, zero Postgres, zero network.
-- apps/nasa-archive/supabase/migrations/20260218000000_oral_history.sql
-- is the proven ancestor; this is that shape, localized and de-domained.
--
-- The invariants are enforced HERE, in triggers, not only in Python.
-- A gate that lives in one call path is a convention; a gate in the
-- database is a gate.
-- ============================================================

PRAGMA foreign_keys = ON;

-- ── statements — what a person actually said. Verbatim. Whole. ──────────────
--
-- Never edited, never normalized, never deleted. Everything else in this
-- schema points back into it by character offset.
CREATE TABLE IF NOT EXISTS statements (
  id           TEXT PRIMARY KEY,
  created_at   TEXT NOT NULL,
  session_id   TEXT NOT NULL,
  narrator_id  TEXT NOT NULL,
  taker_id     TEXT NOT NULL,
  body         TEXT NOT NULL,
  medium       TEXT NOT NULL
               CHECK (medium IN ('audio','transcript','typed','letter','note')),
  captured_at  TEXT,
  consent_ref  TEXT NOT NULL,          -- subject-consent subject_id. required.
  body_sha256  TEXT NOT NULL
);

-- ── claims — one checkable assertion, anchored in a statement ────────────────
CREATE TABLE IF NOT EXISTS claims (
  id           TEXT PRIMARY KEY,
  statement_id TEXT NOT NULL REFERENCES statements(id),
  span_start   INTEGER NOT NULL,
  span_end     INTEGER NOT NULL,
  assertion    TEXT NOT NULL,
  entities     TEXT NOT NULL DEFAULT '[]',
  occurred_at  TEXT,                   -- ISO8601, may be fuzzy: "1998", "1998-06?"
  place        TEXT,

  state        TEXT NOT NULL DEFAULT 'filed'
               CHECK (state IN ('filed','routed','ruled','published',
                                'withheld','uncheckable')),
  source_type  TEXT NOT NULL
               CHECK (source_type IN ('public_record','oral_history_consented',
                                      'authored','unverifiable')),
  confidence   TEXT NOT NULL DEFAULT 'medium'
               CHECK (confidence IN ('high','medium','low','conflicting')),

  ruled_by     TEXT,
  ruled_at     TEXT,
  ruling_note  TEXT,

  corrections  TEXT NOT NULL DEFAULT '[]'
);

-- ── docket_entries — evidence for and against. Machine-written, human-read. ──
CREATE TABLE IF NOT EXISTS docket_entries (
  id          TEXT PRIMARY KEY,
  claim_id    TEXT NOT NULL REFERENCES claims(id),
  created_at  TEXT NOT NULL,
  relation    TEXT NOT NULL
              CHECK (relation IN ('corroborates','contradicts',
                                  'contextualizes','no_source_found')),
  source_kind TEXT NOT NULL
              CHECK (source_kind IN ('vault','public_record','web','operator')),
  source_ref  TEXT,
  excerpt     TEXT,
  found_by    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_claims_state      ON claims(state);
CREATE INDEX IF NOT EXISTS idx_claims_statement  ON claims(statement_id);
CREATE INDEX IF NOT EXISTS idx_claims_confidence ON claims(confidence);
CREATE INDEX IF NOT EXISTS idx_docket_claim      ON docket_entries(claim_id);
CREATE INDEX IF NOT EXISTS idx_statements_sess   ON statements(session_id);

-- ============================================================
-- The invariants (spec §4)
-- ============================================================

-- 1. The verbatim account is write-once.
--    "Corrections not erasure" is only true if the original cannot move.
CREATE TRIGGER IF NOT EXISTS statements_body_write_once
BEFORE UPDATE OF body, body_sha256, narrator_id, taker_id ON statements
BEGIN
  SELECT RAISE(ABORT,
    'statements.body is write-once — file a correction on the claim instead');
END;

-- 2. Statements are never deleted. `withheld` is the operation.
CREATE TRIGGER IF NOT EXISTS statements_never_deleted
BEFORE DELETE ON statements
BEGIN
  SELECT RAISE(ABORT,
    'statements are never deleted — withhold the claims instead (spec 3.5)');
END;

CREATE TRIGGER IF NOT EXISTS claims_never_deleted
BEFORE DELETE ON claims
BEGIN
  SELECT RAISE(ABORT,
    'claims are never deleted — withhold instead (spec 3.5)');
END;

-- 3. A claim's span must resolve inside its statement's body.
--    There is no free-floating fact in this system.
CREATE TRIGGER IF NOT EXISTS claims_span_resolves
BEFORE INSERT ON claims
WHEN NEW.span_start < 0
  OR NEW.span_end <= NEW.span_start
  OR NEW.span_end > (SELECT length(body) FROM statements WHERE id = NEW.statement_id)
BEGIN
  SELECT RAISE(ABORT,
    'claim span does not resolve inside its statement body');
END;

-- 4. §0.2 — proposing and ratifying never rest in the same hand.
--    The one gate with no override flag.
CREATE TRIGGER IF NOT EXISTS claims_witness_gate
BEFORE UPDATE OF ruled_by ON claims
WHEN NEW.ruled_by IS NOT NULL
 AND NEW.ruled_by IN (
       SELECT narrator_id FROM statements WHERE id = NEW.statement_id
       UNION
       SELECT taker_id    FROM statements WHERE id = NEW.statement_id)
BEGIN
  SELECT RAISE(ABORT,
    'ruled_by must be neither the narrator nor the taker (verified_by != author)');
END;

-- 5. A claim cannot reach `published` without a ruler.
CREATE TRIGGER IF NOT EXISTS claims_publish_needs_ruling
BEFORE UPDATE OF state ON claims
WHEN NEW.state = 'published' AND (NEW.ruled_by IS NULL OR NEW.ruled_at IS NULL)
BEGIN
  SELECT RAISE(ABORT, 'a claim cannot be published before it is ruled');
END;
