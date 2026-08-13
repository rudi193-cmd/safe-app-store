-- ai-game-master / schema / corpus (injectable knowledge) — REFERENCE ONLY
-- Backend: SQLite or Postgres. This is the ONE schema in this blueprint the
-- engine ADAPTS to rather than owns — exactly as willow-data-vault marks
-- 05_knowledge.reference.sql "REFERENCE ONLY, willow ADAPTS". Do not assume
-- this shape against an existing corpus; resolve columns at runtime.
--
-- The corpus is the READABLE, injectable knowledge the GM reasons over: the
-- rules text and the persona/voice material. It is a semantic-search seam over
-- an injectable corpus — the Jeles shape (github.com/rudi193-cmd/Jeles:
-- verified corpus in front of live search; conflict_scan searches for what
-- refutes, not what resembles). The engine ships the READER; the corpus stays
-- with whoever grew it.
--
-- ── What goes here, and the licence wall ────────────────────────────────────
-- REUSE tier (open shelf — game-engine plumbing, safe to ship):
--   * the SRD rules text — CC-BY 4.0 (SRD 5.1 / 5.2). Attribution is a hard
--     requirement of that licence: every SRD row MUST carry its source and
--     attribution string, and a row that cannot cite its source is 'unknown',
--     never silently included. (See docs/DECISION.md for the licence terms.)
--   * dice/table plumbing — reused, not stored as knowledge.
--
-- INJECT tier (the moat — NEVER in a shared/public corpus):
--   * a specific campaign's canon, a table's house rules, a family's guests.
--     Those are DATA and live in the BOX (the populated instance), never in
--     this blueprint or any shared shelf — the same blueprint/box wall this
--     whole repo is built on. A campaign corpus is grown by a table and stays
--     with that table.
--
--   source        where the row came from ('SRD-5.1', 'house', 'persona:crone')
--   attribution   the licence attribution string — REQUIRED for any CC-BY row;
--                 a row with licence='CC-BY-4.0' and no attribution is invalid
--   licence       'CC-BY-4.0' | 'house' | 'campaign' | ...
--   tier          'reuse' | 'inject' — reuse may be shared; inject may NOT
--   text          the passage
--   embedding     optional vector blob (the reader's search seam; adaptive)

CREATE TABLE IF NOT EXISTS corpus (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,
    attribution TEXT,
    licence     TEXT NOT NULL DEFAULT 'house',
    tier        TEXT NOT NULL DEFAULT 'inject',
    text        TEXT NOT NULL,
    embedding   BLOB,
    CHECK (tier IN ('reuse','inject')),
    -- a CC-BY row without attribution is invalid: the licence requires the credit
    CHECK (NOT (licence = 'CC-BY-4.0' AND (attribution IS NULL OR attribution = '')))
);
CREATE INDEX IF NOT EXISTS idx_corpus_tier   ON corpus(tier);
CREATE INDEX IF NOT EXISTS idx_corpus_source ON corpus(source);
