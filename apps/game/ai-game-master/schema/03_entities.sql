-- ai-game-master / schema / entities (who and what is in the world)
-- Backend: SQLite. Entity-resolution shape pattern-ported from Nestor's
-- entity.py (github.com/rudi193-cmd/Nestor, pinned v0.2.0) — one row per
-- resolved referent, with aliases folding onto it, so "the Prince", "Villippe",
-- and "the father" are one entity and not three. No Nestor code is copied
-- verbatim.
--
-- An entity is any durable referent: a player character (Grask, Wren, Vex), an
-- NPC (Prince Villippe, the Crone, Kaelan Blackheart), a place (Lake Eldoria),
-- an item (the Four Ancient Tomes), or a GUEST — a character a player brought
-- to the table and the DM welcomed in.
--
-- ── The guest lane (the load-bearing design signal) ─────────────────────────
-- The Vander game the kids actually played was not a rules slog: the DM
-- loosened the dice, let role-play count for more than the mechanics allowed,
-- and said *yes-and* when players walked in Beetlejuice, the Sandworm, and Bill
-- Cipher from Gravity Falls. Those are entities of kind='guest'. A guest is
-- canon exactly the way anything else is: a player PROPOSES it, and a NAMED
-- HUMAN (the DM) SEALS it into canon (schema/02_canon.sql). The ledger then
-- records "Bill Cipher — guest, sealed by <DM>, session N" — joyful,
-- non-standard, human-authored canon that is auditable and un-retconnable.
--
-- This is why the product is a yes-and BOOKKEEPER, not a rules referee: guests
-- are a first-class kind, not an exception the engine grudgingly tolerates.
--
--   kind        'pc' | 'npc' | 'place' | 'item' | 'guest' | 'faction'
--   canonical   the resolved display name
--   aliases     JSON array of other strings that resolve to this entity
--   sheet       JSON — stats / properties (a PC's HP/AC/slots, an item's effect)
--   sealed_by   for a guest or any entity whose EXISTENCE is a canon act: the
--               named human who welcomed it in. NULL for entities that are just
--               part of the written setting.
--   introduced_ledger_id  the ledger turn the entity first entered play.

CREATE TABLE IF NOT EXISTS entities (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,
    canonical   TEXT NOT NULL,
    aliases     TEXT NOT NULL DEFAULT '[]',
    sheet       TEXT,
    sealed_by   TEXT,                 -- a named human, when existence is a canon act (e.g. a guest)
    introduced_ledger_id INTEGER,
    invalid_at  TEXT,                 -- retire by dating, never by deleting (archive-don't-delete)
    CHECK (kind IN ('pc','npc','place','item','guest','faction'))
);
CREATE INDEX IF NOT EXISTS idx_entities_kind  ON entities(kind);
CREATE INDEX IF NOT EXISTS idx_entities_valid ON entities(invalid_at);
