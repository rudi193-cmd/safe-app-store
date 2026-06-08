-- ============================================================
-- NASA Archive — User Memory & Rally Tracker
-- Run this in: Supabase Dashboard → SQL Editor
--
-- Cultural principles encoded here:
--   "You Were There"          → user_rally_attendance
--   "Your Story, Your Terms"  → public_profile opt-in
--   "Nothing Is Sold"         → no analytics tables, no third-party ids
-- ============================================================

-- ============================================================
-- USER PROFILES
-- ============================================================
-- Extends auth.users. Created on first login by trigger or explicit save.
CREATE TABLE user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    display_name TEXT,
    home_city TEXT,
    home_state TEXT,
    riding_since INTEGER,           -- year they started scooting
    bio TEXT,
    public_profile BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- RALLY ATTENDANCE TRACKER
-- ============================================================
-- "I was there" / "I'm going" markers per user per rally.
CREATE TABLE user_rally_attendance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    rally_slug TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('attended', 'planning')),
    year_attended INTEGER,          -- null for 'planning'
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, rally_slug)
);

-- ============================================================
-- ORAL HISTORY CHAT SESSIONS (persistent memory)
-- ============================================================
-- The oral historian remembers what you shared last time.
-- messages: [{role, content, timestamp}]
-- extracted_facts: {persons: [], bikes: [], locations: [], stories: []}
CREATE TABLE oral_chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    rally_slug TEXT,                -- null for general (non-rally-specific) sessions
    messages JSONB NOT NULL DEFAULT '[]',
    extracted_facts JSONB NOT NULL DEFAULT '{}',
    started_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================

ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_rally_attendance ENABLE ROW LEVEL SECURITY;
ALTER TABLE oral_chat_sessions ENABLE ROW LEVEL SECURITY;

-- Own profile: full access
CREATE POLICY "own_profile_all" ON user_profiles
    FOR ALL USING (auth.uid() = id);

-- Public profiles: anyone can read if opted in
CREATE POLICY "public_profile_read" ON user_profiles
    FOR SELECT USING (public_profile = true);

-- Own attendance: full access
CREATE POLICY "own_attendance_all" ON user_rally_attendance
    FOR ALL USING (auth.uid() = user_id);

-- Public attendance: readable if user has public profile
CREATE POLICY "public_attendance_read" ON user_rally_attendance
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM user_profiles
            WHERE id = user_id AND public_profile = true
        )
    );

-- Own sessions: full access (private by default — no public policy)
CREATE POLICY "own_sessions_all" ON oral_chat_sessions
    FOR ALL USING (auth.uid() = user_id);

-- ============================================================
-- ATTENDANCE COUNTS VIEW (for rally pages)
-- ============================================================
-- How many people have marked each rally as attended.
-- Used to show "47 people were here" on rally detail pages.
CREATE VIEW rally_attendance_counts AS
SELECT
    rally_slug,
    COUNT(*) FILTER (WHERE status = 'attended') AS attended_count,
    COUNT(*) FILTER (WHERE status = 'planning') AS planning_count
FROM user_rally_attendance
GROUP BY rally_slug;

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX idx_attendance_user ON user_rally_attendance(user_id);
CREATE INDEX idx_attendance_slug ON user_rally_attendance(rally_slug);
CREATE INDEX idx_sessions_user ON oral_chat_sessions(user_id);
CREATE INDEX idx_sessions_slug ON oral_chat_sessions(rally_slug);
