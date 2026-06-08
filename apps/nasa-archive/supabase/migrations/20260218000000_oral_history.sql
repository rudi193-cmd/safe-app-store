-- ============================================================
-- NASA Archive — Oral History Schema
-- Run this in: Supabase Dashboard → SQL Editor
-- Based on: North America Scooter Archive Technical Specification
--
-- Cultural principles encoded here:
--   "Names Given Not Chosen"  → oral_namings.drunk
--   "Grief Makes Space"       → oral_memorials
--   "Someone Always Stops"    → oral_rescues
--   "Corrections Not Erasure" → .corrections JSONB on stories/events
--   "Recognition Not Instruction" → club_name as canonical identity
-- ============================================================

-- ============================================================
-- ENUMERATIONS
-- ============================================================

-- Privacy governance: every fact has a source type.
-- HARD RULE: pipeline only touches public_record.
-- oral_history_consented requires explicit in-session user consent.
CREATE TYPE source_type AS ENUM (
  'public_record',          -- census, immigration, scoot.net, podcasts, web archives
  'oral_history_consented'  -- user said yes in-session to storage
);

-- Confidence scoring per the Knowledge Graph spec.
CREATE TYPE confidence_level AS ENUM (
  'high',         -- multiple independent sources agree
  'medium',       -- single reliable source
  'low',          -- approximate, inferred, or secondhand
  'conflicting'   -- sources disagree — human curation required
);

CREATE TYPE bike_status AS ENUM (
  'riding',
  'garage',
  'garden_art',   -- "it's a planter now"
  'sold',
  'totaled',
  'stolen',
  'unknown'
);

CREATE TYPE absurdity_level AS ENUM (
  'normal',
  'notable',
  'legendary',
  'mythological'
);

CREATE TYPE story_source AS ENUM (
  'oral',
  'written',
  'photo_caption',
  'secondhand'
);

CREATE TYPE club_role AS ENUM (
  'member',
  'officer',
  'founder',
  'honorary',
  'ex_member'
);

-- ============================================================
-- CORE ENTITIES
-- ============================================================

-- PERSONS
-- club_name is the canonical public identifier. Legal names are private.
-- "Recognition Not Instruction" — we record how the community knows them.
CREATE TABLE oral_persons (
  id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW(),

  -- Identity
  club_name       TEXT NOT NULL,       -- "Slappy", "The Colonel", "Wrench"
  legal_name      TEXT,                -- private, optional

  -- History
  scootering_since INTEGER,
  home_city       TEXT,
  home_state      TEXT,

  -- Community network (denormalized for quick reads)
  rescue_count    INTEGER DEFAULT 0,   -- times they rescued others
  rescued_count   INTEGER DEFAULT 0,   -- times they were rescued
  carried_by      UUID REFERENCES oral_persons(id), -- who got them into scootering

  -- Oral history
  bio             TEXT,
  corrections     JSONB DEFAULT '[]',  -- first-class corrections

  -- Privacy
  public_profile  BOOLEAN DEFAULT TRUE,
  deceased        BOOLEAN DEFAULT FALSE,
  year_of_passing INTEGER,

  -- Governance (SAFE OS Knowledge Graph spec)
  -- source_type: who may have written this record
  -- confidence:  how certain we are about the data
  -- sources:     array of {type, url, timestamp, narrator_id, confidence}
  source_type     source_type NOT NULL DEFAULT 'oral_history_consented',
  confidence      confidence_level NOT NULL DEFAULT 'medium',
  sources         JSONB DEFAULT '[]'
);

-- LOCATIONS
CREATE TABLE oral_locations (
  id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  created_at    TIMESTAMPTZ DEFAULT NOW(),

  name          TEXT NOT NULL,   -- "Miller's Bar", "The Farm", "Laconia"
  address       TEXT,
  city          TEXT,
  state         TEXT,
  country       TEXT DEFAULT 'USA',
  location_type TEXT,            -- 'bar', 'campground', 'venue', 'road', 'diner'
  still_exists  BOOLEAN,
  notes         TEXT,

  source_type   source_type NOT NULL DEFAULT 'oral_history_consented',
  confidence    confidence_level NOT NULL DEFAULT 'medium',
  sources       JSONB DEFAULT '[]'
);

-- BIKES
CREATE TABLE oral_bikes (
  id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  created_at       TIMESTAMPTZ DEFAULT NOW(),

  make             TEXT,          -- 'Vespa', 'Lambretta', 'Honda'
  model            TEXT,
  year             INTEGER,
  nickname         TEXT,          -- "The Beast", "Deathtrap"

  current_owner_id UUID REFERENCES oral_persons(id),
  current_status   bike_status DEFAULT 'unknown',
  notes            TEXT,          -- its story

  source_type      source_type NOT NULL DEFAULT 'oral_history_consented',
  confidence       confidence_level NOT NULL DEFAULT 'medium',
  sources          JSONB DEFAULT '[]'
);

-- CLUBS
CREATE TABLE oral_clubs (
  id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  created_at    TIMESTAMPTZ DEFAULT NOW(),

  name          TEXT NOT NULL,
  city          TEXT,
  state         TEXT,
  founded_year  INTEGER,

  -- "cultural_dna" — what defines this club
  -- e.g., "fast bikes, no drama" / "deep roots, loud opinions" / "show up and wrench"
  cultural_dna  TEXT,

  active        BOOLEAN DEFAULT TRUE,
  notes         TEXT,

  source_type   source_type NOT NULL DEFAULT 'oral_history_consented',
  confidence    confidence_level NOT NULL DEFAULT 'medium',
  sources       JSONB DEFAULT '[]'
);

-- EVENTS (rallies, runs, incidents of record)
CREATE TABLE oral_events (
  id                   UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  created_at           TIMESTAMPTZ DEFAULT NOW(),

  name                 TEXT NOT NULL,     -- "Iowa Storm Rally", "That Night at Miller's"
  event_year           INTEGER,
  event_date           DATE,              -- exact date if known

  location_id          UUID REFERENCES oral_locations(id),
  organizer_id         UUID REFERENCES oral_persons(id),

  absurdity_level      absurdity_level DEFAULT 'normal',
  estimated_attendance INTEGER,

  -- Link to main archive (if there's a gallery)
  archive_slug         TEXT,             -- matches gallery_index.json slug

  description          TEXT,
  notes                TEXT,
  corrections          JSONB DEFAULT '[]',

  source_type          source_type NOT NULL DEFAULT 'oral_history_consented',
  confidence           confidence_level NOT NULL DEFAULT 'medium',
  sources              JSONB DEFAULT '[]'
);

-- STORIES — the oral history records
CREATE TABLE oral_stories (
  id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  created_at       TIMESTAMPTZ DEFAULT NOW(),
  updated_at       TIMESTAMPTZ DEFAULT NOW(),

  title            TEXT,
  content          TEXT NOT NULL,

  narrator_id      UUID REFERENCES oral_persons(id),
  event_id         UUID REFERENCES oral_events(id),

  -- Direct archive link (rally slug from gallery_index.json)
  archive_slug     TEXT,             -- e.g., "laconia2003" — for rally page queries

  source           story_source DEFAULT 'oral',
  capture_date     DATE,
  capture_session  TEXT,      -- e.g., "pharaohs-2026-02-18"

  verified         BOOLEAN DEFAULT FALSE,

  -- FIRST-CLASS: corrections are not buried in notes.
  -- Format: [{"by": "club_name", "date": "...", "field": "...", "was": "...", "is": "..."}]
  corrections      JSONB DEFAULT '[]',

  -- Governance (SAFE OS Knowledge Graph spec)
  -- source_type distinguishes how this story entered the system.
  -- Stories submitted via the oral-chat edge function are always oral_history_consented
  -- (user chose to submit). Pipeline-seeded stories are public_record.
  source_type      source_type NOT NULL DEFAULT 'oral_history_consented',
  confidence       confidence_level NOT NULL DEFAULT 'medium',
  sources          JSONB DEFAULT '[]',

  -- RAG support
  summary          TEXT,             -- brief summary for retrieval
  embedding_ready  BOOLEAN DEFAULT FALSE
);

-- PHOTOS (oral history context for archive photos)
CREATE TABLE oral_photos (
  id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  created_at      TIMESTAMPTZ DEFAULT NOW(),

  -- Reference to main archive
  r2_url          TEXT NOT NULL,   -- Cloudflare R2 URL
  archive_slug    TEXT,            -- rally slug from gallery_index.json
  photo_filename  TEXT,

  -- Oral history context
  description     TEXT,
  photo_year      INTEGER,

  location_id     UUID REFERENCES oral_locations(id),
  event_id        UUID REFERENCES oral_events(id),

  -- Who added this oral context
  claimed_by      UUID REFERENCES auth.users(id)
);

-- ============================================================
-- RELATIONSHIP TABLES
-- ============================================================

-- RESCUES — "Someone Always Stops"
CREATE TABLE oral_rescues (
  id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  created_at   TIMESTAMPTZ DEFAULT NOW(),

  rescuer_id   UUID NOT NULL REFERENCES oral_persons(id),
  rescued_id   UUID NOT NULL REFERENCES oral_persons(id),

  event_id     UUID REFERENCES oral_events(id),
  location_id  UUID REFERENCES oral_locations(id),
  bike_id      UUID REFERENCES oral_bikes(id),  -- what broke down

  rescue_year  INTEGER,
  description  TEXT                              -- what actually happened
);

-- NAMINGS — "Names Given Not Chosen"
CREATE TABLE oral_namings (
  id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  created_at   TIMESTAMPTZ DEFAULT NOW(),

  person_id    UUID NOT NULL REFERENCES oral_persons(id),
  given_name   TEXT NOT NULL,           -- the name they received
  named_by_id  UUID REFERENCES oral_persons(id),
  event_id     UUID REFERENCES oral_events(id),

  drunk        BOOLEAN DEFAULT FALSE,   -- was this a drunk decision
  naming_year  INTEGER,
  story        TEXT                     -- how it happened
);

-- SPONSORSHIPS — club welcoming a person
CREATE TABLE oral_sponsorships (
  id                   UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  created_at           TIMESTAMPTZ DEFAULT NOW(),

  sponsored_person_id  UUID NOT NULL REFERENCES oral_persons(id),
  sponsoring_club_id   UUID REFERENCES oral_clubs(id),
  vouching_person_id   UUID REFERENCES oral_persons(id),  -- who personally vouched

  event_id             UUID REFERENCES oral_events(id),
  sponsorship_year     INTEGER,
  notes                TEXT
);

-- TRANSFERS — bikes changing hands
CREATE TABLE oral_transfers (
  id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  created_at      TIMESTAMPTZ DEFAULT NOW(),

  bike_id         UUID NOT NULL REFERENCES oral_bikes(id),
  from_person_id  UUID REFERENCES oral_persons(id),
  to_person_id    UUID REFERENCES oral_persons(id),

  transfer_year   INTEGER,
  story           TEXT    -- context: why, how, under what circumstances
);

-- MEMORIALS — "Grief Makes Space"
CREATE TABLE oral_memorials (
  id                 UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  created_at         TIMESTAMPTZ DEFAULT NOW(),

  person_id          UUID NOT NULL REFERENCES oral_persons(id),
  year_of_passing    INTEGER,

  memorial_event_id  UUID REFERENCES oral_events(id),  -- rally dedicated to them
  tribute            TEXT,                             -- community tribute

  submitted_by       UUID REFERENCES auth.users(id)
);

-- ============================================================
-- JUNCTION TABLES
-- ============================================================

-- person ↔ clubs (membership history)
CREATE TABLE oral_person_clubs (
  person_id    UUID NOT NULL REFERENCES oral_persons(id) ON DELETE CASCADE,
  club_id      UUID NOT NULL REFERENCES oral_clubs(id) ON DELETE CASCADE,
  role         club_role DEFAULT 'member',
  joined_year  INTEGER,
  left_year    INTEGER,  -- NULL = still active member
  notes        TEXT,
  PRIMARY KEY (person_id, club_id)
);

-- person ↔ events (attendance)
CREATE TABLE oral_person_events (
  person_id  UUID NOT NULL REFERENCES oral_persons(id) ON DELETE CASCADE,
  event_id   UUID NOT NULL REFERENCES oral_events(id) ON DELETE CASCADE,
  role       TEXT DEFAULT 'attendee',  -- 'attendee', 'organizer', 'band', 'vendor'
  PRIMARY KEY (person_id, event_id)
);

-- story ↔ persons (who appears)
CREATE TABLE oral_story_persons (
  story_id   UUID NOT NULL REFERENCES oral_stories(id) ON DELETE CASCADE,
  person_id  UUID NOT NULL REFERENCES oral_persons(id) ON DELETE CASCADE,
  role       TEXT DEFAULT 'subject',  -- 'narrator', 'subject', 'witness', 'mentioned'
  PRIMARY KEY (story_id, person_id)
);

-- story ↔ bikes
CREATE TABLE oral_story_bikes (
  story_id  UUID NOT NULL REFERENCES oral_stories(id) ON DELETE CASCADE,
  bike_id   UUID NOT NULL REFERENCES oral_bikes(id) ON DELETE CASCADE,
  PRIMARY KEY (story_id, bike_id)
);

-- story ↔ locations
CREATE TABLE oral_story_locations (
  story_id     UUID NOT NULL REFERENCES oral_stories(id) ON DELETE CASCADE,
  location_id  UUID NOT NULL REFERENCES oral_locations(id) ON DELETE CASCADE,
  PRIMARY KEY (story_id, location_id)
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX idx_oral_persons_club_name   ON oral_persons(club_name);
CREATE INDEX idx_oral_persons_carried_by  ON oral_persons(carried_by);
CREATE INDEX idx_oral_events_year         ON oral_events(event_year);
CREATE INDEX idx_oral_events_absurdity    ON oral_events(absurdity_level);
CREATE INDEX idx_oral_events_slug         ON oral_events(archive_slug);
CREATE INDEX idx_oral_stories_narrator    ON oral_stories(narrator_id);
CREATE INDEX idx_oral_stories_event       ON oral_stories(event_id);
CREATE INDEX idx_oral_stories_session     ON oral_stories(capture_session);
CREATE INDEX idx_oral_stories_slug        ON oral_stories(archive_slug);
CREATE INDEX idx_oral_rescues_rescuer     ON oral_rescues(rescuer_id);
CREATE INDEX idx_oral_rescues_rescued     ON oral_rescues(rescued_id);
CREATE INDEX idx_oral_namings_person      ON oral_namings(person_id);
CREATE INDEX idx_oral_photos_slug         ON oral_photos(archive_slug);

-- Governance indexes — pipeline queries public_record only
CREATE INDEX idx_oral_persons_source_type  ON oral_persons(source_type);
CREATE INDEX idx_oral_events_source_type   ON oral_events(source_type);
CREATE INDEX idx_oral_stories_source_type  ON oral_stories(source_type);
CREATE INDEX idx_oral_stories_confidence   ON oral_stories(confidence);

-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================

ALTER TABLE oral_persons       ENABLE ROW LEVEL SECURITY;
ALTER TABLE oral_locations     ENABLE ROW LEVEL SECURITY;
ALTER TABLE oral_bikes         ENABLE ROW LEVEL SECURITY;
ALTER TABLE oral_clubs         ENABLE ROW LEVEL SECURITY;
ALTER TABLE oral_events        ENABLE ROW LEVEL SECURITY;
ALTER TABLE oral_stories       ENABLE ROW LEVEL SECURITY;
ALTER TABLE oral_photos        ENABLE ROW LEVEL SECURITY;
ALTER TABLE oral_rescues       ENABLE ROW LEVEL SECURITY;
ALTER TABLE oral_namings       ENABLE ROW LEVEL SECURITY;
ALTER TABLE oral_sponsorships  ENABLE ROW LEVEL SECURITY;
ALTER TABLE oral_transfers     ENABLE ROW LEVEL SECURITY;
ALTER TABLE oral_memorials     ENABLE ROW LEVEL SECURITY;
ALTER TABLE oral_person_clubs  ENABLE ROW LEVEL SECURITY;
ALTER TABLE oral_person_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE oral_story_persons ENABLE ROW LEVEL SECURITY;
ALTER TABLE oral_story_bikes   ENABLE ROW LEVEL SECURITY;
ALTER TABLE oral_story_locations ENABLE ROW LEVEL SECURITY;

-- Public read (non-private records are open to all)
CREATE POLICY "public_read" ON oral_persons
  FOR SELECT USING (public_profile = TRUE);

CREATE POLICY "public_read" ON oral_locations
  FOR SELECT TO anon, authenticated USING (TRUE);

CREATE POLICY "public_read" ON oral_bikes
  FOR SELECT TO anon, authenticated USING (TRUE);

CREATE POLICY "public_read" ON oral_clubs
  FOR SELECT TO anon, authenticated USING (TRUE);

CREATE POLICY "public_read" ON oral_events
  FOR SELECT TO anon, authenticated USING (TRUE);

CREATE POLICY "public_read" ON oral_stories
  FOR SELECT TO anon, authenticated USING (TRUE);

CREATE POLICY "public_read" ON oral_photos
  FOR SELECT TO anon, authenticated USING (TRUE);

CREATE POLICY "public_read" ON oral_rescues
  FOR SELECT TO anon, authenticated USING (TRUE);

CREATE POLICY "public_read" ON oral_namings
  FOR SELECT TO anon, authenticated USING (TRUE);

CREATE POLICY "public_read" ON oral_sponsorships
  FOR SELECT TO anon, authenticated USING (TRUE);

CREATE POLICY "public_read" ON oral_transfers
  FOR SELECT TO anon, authenticated USING (TRUE);

CREATE POLICY "public_read" ON oral_memorials
  FOR SELECT TO anon, authenticated USING (TRUE);

CREATE POLICY "public_read" ON oral_person_clubs
  FOR SELECT TO anon, authenticated USING (TRUE);

CREATE POLICY "public_read" ON oral_person_events
  FOR SELECT TO anon, authenticated USING (TRUE);

CREATE POLICY "public_read" ON oral_story_persons
  FOR SELECT TO anon, authenticated USING (TRUE);

CREATE POLICY "public_read" ON oral_story_bikes
  FOR SELECT TO anon, authenticated USING (TRUE);

CREATE POLICY "public_read" ON oral_story_locations
  FOR SELECT TO anon, authenticated USING (TRUE);

-- Authenticated users can contribute stories and photo context.
-- oral_history_consented is implicit — submitting = consenting to storage.
-- The pipeline uses service role to insert public_record stories directly.
CREATE POLICY "authenticated_insert_stories" ON oral_stories
  FOR INSERT TO authenticated WITH CHECK (source_type = 'oral_history_consented');

CREATE POLICY "authenticated_insert_photos" ON oral_photos
  FOR INSERT TO authenticated WITH CHECK (auth.uid() = claimed_by);

-- ============================================================
-- TRIGGERS
-- ============================================================

CREATE OR REPLACE FUNCTION update_oral_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER oral_persons_updated_at
  BEFORE UPDATE ON oral_persons
  FOR EACH ROW EXECUTE FUNCTION update_oral_updated_at();

CREATE TRIGGER oral_stories_updated_at
  BEFORE UPDATE ON oral_stories
  FOR EACH ROW EXECUTE FUNCTION update_oral_updated_at();

-- ============================================================
-- RESCUE COUNT TRIGGER
-- Keep oral_persons.rescue_count accurate automatically
-- ============================================================

CREATE OR REPLACE FUNCTION increment_rescue_counts()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE oral_persons SET rescue_count = rescue_count + 1
    WHERE id = NEW.rescuer_id;
  UPDATE oral_persons SET rescued_count = rescued_count + 1
    WHERE id = NEW.rescued_id;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER oral_rescues_count_trigger
  AFTER INSERT ON oral_rescues
  FOR EACH ROW EXECUTE FUNCTION increment_rescue_counts();
