-- ai-game-master / schema / campaign ledger (append-only, hash-chained)
-- Backend: SQLite. Pattern-ported from Nestor's hash-chained ledger
-- (nestor/ledger.py, Apache-2.0, github.com/rudi193-cmd/Nestor, pinned
-- v0.2.0) — the same prev-is-a-hash-of-the-previous-entry chain, re-expressed
-- against a SQL table instead of the JSONL file the Vander dogfood used
-- (vander_tracker.py wrote nestor.ledger.head()/verify() over a .jsonl). No
-- Nestor code is copied verbatim; the pattern is re-stated in this repo's idiom.
--
-- One row per TURN — a snapshot of what the table did and what became true.
-- This is the game's book of record: the thing that answers "what did we
-- decide three sessions ago" without anyone — not the DM, not the machine —
-- being able to quietly rewrite it after the fact. The DM adjudicates; this
-- keeps an honest book.
--
-- ── The chain ───────────────────────────────────────────────────────────────
--   prev_hash  the `hash` of the row immediately before this one, ordered by
--              id ascending. The first row carries the literal string
--              'genesis' — the same empty-chain sentinel nestor.ledger.head()
--              and verify() use.
--   hash       SHA-256 hex digest of this row's own canonical JSON form:
--                {"id": <id>, "ts": <ts>, "session": <session>,
--                 "kind": <kind>, "note": <note>, "state": <state>,
--                 "prev_hash": <prev_hash>}
--              serialized with Python's json.dumps default separators
--              (", " / ": "), ensure_ascii=False, in exactly that key order.
--              (See bootstrap/verify_ledger.py for the one authority on the
--              canonical form — schema and verifier must agree byte-for-byte.)
--
-- Editing any past row changes what its `hash` should be on re-hash, so the
-- next row's `prev_hash` no longer matches. bootstrap/verify_ledger.py walks
-- the table looking for exactly that mismatch, and a break is a REFUSAL
-- (nonzero exit), never a warning — matching nestor.ledger.verify's contract.
--
-- Same limit Nestor states up front: the walk vouches for every row *except
-- the last*, which nothing follows yet. Keep a separately-recorded expected
-- head (outside the box — a notes app, a co-DM's phone) to close that gap;
-- this schema does not do it on its own.
--
-- `state` is the turn snapshot (party HP/slots/resources, clock, foes,
-- inventory, geas) as JSON — the shape vander_tracker.py sealed each turn.
-- `kind` distinguishes a play turn ('turn') from a session marker
-- ('session_open' / 'session_close') so a reader can fold the log into
-- sessions without parsing prose.

CREATE TABLE IF NOT EXISTS ledger (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    session    INTEGER NOT NULL DEFAULT 0,
    kind       TEXT NOT NULL DEFAULT 'turn',
    note       TEXT NOT NULL,
    state      TEXT NOT NULL,
    prev_hash  TEXT NOT NULL,
    hash       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ledger_session ON ledger(session);
CREATE INDEX IF NOT EXISTS idx_ledger_kind    ON ledger(kind);
