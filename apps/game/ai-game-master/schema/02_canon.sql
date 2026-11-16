-- ai-game-master / schema / canon (the sealed truth of the world)
-- Backend: SQLite. State machine pattern-ported from terpsi-music's
-- records/sealing.py (github.com/rudi193-cmd/terpsi-music) and the same
-- covenant Nestor carries: *you may propose, you may not confirm.* No code is
-- copied verbatim; the four-state lifecycle and the not-a-person guard are
-- re-expressed here for a campaign's facts.
--
-- A canon row is one FACT about the world — "Prince Villippe is freed",
-- "Bill Cipher is a guest of the valley", "the red button is bait". Every
-- fact carries a lifecycle status, and the whole point of this table is the
-- wall between the two halves of that lifecycle:
--
--   PENDING   the machine (or a player) has PROPOSED this fact. Not yet true.
--   DRAFT     in play, provisional — a machine answer stands as draft until a
--             human seals it. Still not canon.
--   SEALED    a NAMED HUMAN at the head of the table made it true. Only a
--             person seals. This is the only status that is canon.
--   REJECTED  a named human refused it. Recorded as durably as a seal — an
--             audit trail that logs only agreement is not one.
--
-- The machine writes PENDING and DRAFT. It MUST NOT write SEALED or REJECTED;
-- those transitions require `sealed_by` to name a real person. This is the
-- thesis, not a feature: "the human seals canon" is the line the whole fleet's
-- covenant already draws (Nestor's asymmetric seal, terpsi's sealing.py,
-- willow-mcp's human_session). The GM proposes, rolls, and remembers; it never
-- replaces the person running the table for a room of ten-year-olds.
--
-- ── The not-a-person guard ──────────────────────────────────────────────────
-- `sealed_by` is a human's name. A seal attributed to the machine, a persona,
-- an agent id, or any sentinel in NOT_A_PERSON is INVALID even if the row
-- otherwise looks sealed — the verifier (bootstrap/verify_ledger.py --canon)
-- refuses it. terpsi's _NOT_A_PERSON is the source of this list; keep them in
-- sync when either grows.
--   NOT_A_PERSON = {'', 'system', 'machine', 'ai', 'gm', 'dm-bot', 'assistant',
--                   'claude', 'model', 'auto', 'none', 'null'}
--
-- ── ties to the chain ───────────────────────────────────────────────────────
-- `ledger_id` points at the ledger row (schema/01_ledger.sql) that recorded
-- the turn this fact was sealed on, so a canon fact traces to the tamper-
-- evident moment it became true. A seal that names no ledger turn is a claim
-- with no receipt.

CREATE TABLE IF NOT EXISTS canon (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    fact       TEXT NOT NULL,                      -- the statement about the world
    status     TEXT NOT NULL DEFAULT 'PENDING',    -- PENDING|DRAFT|SEALED|REJECTED
    proposed_by TEXT NOT NULL DEFAULT '',          -- machine, a player, or the DM
    sealed_by  TEXT,                               -- a NAMED HUMAN — required for SEALED/REJECTED
    sealed_at  TEXT,
    ledger_id  INTEGER,                            -- the ledger turn this was sealed on
    reason     TEXT,                               -- why sealed, or why rejected
    CHECK (status IN ('PENDING','DRAFT','SEALED','REJECTED')),
    -- a SEALED or REJECTED row MUST name who did it; PENDING/DRAFT must not
    CHECK (
        (status IN ('SEALED','REJECTED') AND sealed_by IS NOT NULL AND sealed_by <> '')
        OR
        (status IN ('PENDING','DRAFT') AND sealed_by IS NULL)
    )
);
CREATE INDEX IF NOT EXISTS idx_canon_status ON canon(status);
