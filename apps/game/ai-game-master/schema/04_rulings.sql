-- ai-game-master / schema / rulings (the signed decision graph)
-- Backend: SQLite. Pattern-ported from Nestor's signed decision graph
-- (nestor/decision.py + nestor/signing.py, Apache-2.0,
-- github.com/rudi193-cmd/Nestor, pinned v0.2.0) — decisions that carry a
-- signature and can point at the decisions they supersede. No Nestor code is
-- copied verbatim.
--
-- A ruling is a DM adjudication that outlives the moment: "rule-of-cool — the
-- Sandworm counts as difficult terrain, not an instakill", "the button is
-- never pressed; restraint is the win", "guests roll with the same dice we
-- loosened for everyone". Rulings are how a table stays consistent across
-- seven months of once-a-week sessions — the thing a machine is genuinely good
-- at holding so the human doesn't have to.
--
-- ── Signed, and superseding — not deleting ──────────────────────────────────
-- A ruling can be SIGNED (sig / signer) so a later reader can tell a real
-- adjudication from a note someone dropped in. And a ruling can SUPERSEDE an
-- earlier one (supersedes_id) rather than overwrite it — the old ruling stays
-- in the table, dated out, so the reasoning trail survives. Corrections land
-- BESIDE the record, never on top of it: a log that quietly overwrites its own
-- mistakes can confirm the current answer but cannot be used to check whether
-- the reasoning was sound.
--
-- The signature covers the ruling's own content; it is tamper-EVIDENCE and an
-- attribution, and it grants no authority on its own — sealing canon is still
-- schema/02_canon.sql's job and still requires a named human. A signed ruling
-- says "the DM decided this and here is proof it wasn't altered", not "this is
-- automatically true".
--
--   text          the adjudication
--   scope         'rule' | 'canon' | 'session' — how far the ruling reaches
--   signer        the human (or, for an unsigned house-note, '')
--   sig           detached signature over `text` (Ed25519 or HMAC; scheme in
--                 sig_scheme), verified by bootstrap/verify_ledger.py --rulings
--                 against a public key the box holds outside this table
--   supersedes_id  a prior ruling this one replaces (the prior row is dated out
--                  via invalid_at, not removed)

CREATE TABLE IF NOT EXISTS rulings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    text          TEXT NOT NULL,
    scope         TEXT NOT NULL DEFAULT 'rule',
    signer        TEXT NOT NULL DEFAULT '',
    sig           TEXT,
    sig_scheme    TEXT,                 -- 'ed25519' | 'hmac-sha256' | NULL (unsigned house-note)
    ledger_id     INTEGER,             -- the turn it was made on
    supersedes_id INTEGER REFERENCES rulings(id),
    invalid_at    TEXT,                -- set when superseded; the row stays
    CHECK (scope IN ('rule','canon','session'))
);
CREATE INDEX IF NOT EXISTS idx_rulings_scope ON rulings(scope);
CREATE INDEX IF NOT EXISTS idx_rulings_valid ON rulings(invalid_at);
