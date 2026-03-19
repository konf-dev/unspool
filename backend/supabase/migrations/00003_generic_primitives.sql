-- Generic primitives: events, trackers, notes, scheduled_actions, collections
-- These are the building blocks the LLM composes into any feature.

-- ============================================================
-- 1. events — meetings, reminders, recurring, calendar sync
-- ============================================================
CREATE TABLE IF NOT EXISTS events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    title TEXT NOT NULL,
    description TEXT,
    starts_at TIMESTAMPTZ,
    ends_at TIMESTAMPTZ,
    is_all_day BOOLEAN DEFAULT false,
    rrule TEXT,
    source TEXT DEFAULT 'user' CHECK (source IN ('user', 'google', 'system')),
    google_event_id TEXT,
    source_message_id UUID REFERENCES messages(id),
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'cancelled', 'completed')),
    created_at TIMESTAMPTZ DEFAULT now(),
    metadata JSONB DEFAULT '{}',
    UNIQUE(user_id, google_event_id)
);

CREATE INDEX IF NOT EXISTS idx_events_user_start ON events(user_id, starts_at)
    WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_events_user_rrule ON events(user_id)
    WHERE rrule IS NOT NULL AND status = 'active';

ALTER TABLE events ENABLE ROW LEVEL SECURITY;
CREATE POLICY IF NOT EXISTS "users_own_events" ON events FOR ALL
    USING (auth.uid() = user_id);

-- ============================================================
-- 2. trackers — define what to track (fuel, sleep, meds, etc.)
-- ============================================================
CREATE TABLE IF NOT EXISTS trackers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    name TEXT NOT NULL,
    unit TEXT,
    track_type TEXT DEFAULT 'numeric' CHECK (track_type IN ('numeric', 'boolean', 'text', 'currency')),
    created_by TEXT DEFAULT 'user' CHECK (created_by IN ('user', 'ai')),
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    metadata JSONB DEFAULT '{}',
    UNIQUE(user_id, lower(name))
);

CREATE INDEX IF NOT EXISTS idx_trackers_user ON trackers(user_id) WHERE active = true;

ALTER TABLE trackers ENABLE ROW LEVEL SECURITY;
CREATE POLICY IF NOT EXISTS "users_own_trackers" ON trackers FOR ALL
    USING (auth.uid() = user_id);

-- ============================================================
-- 3. tracker_entries — individual data points
-- ============================================================
CREATE TABLE IF NOT EXISTS tracker_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tracker_id UUID NOT NULL REFERENCES trackers(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id),
    value TEXT NOT NULL,
    recorded_at TIMESTAMPTZ DEFAULT now(),
    note TEXT,
    source_message_id UUID REFERENCES messages(id),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tracker_entries_tracker ON tracker_entries(tracker_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_tracker_entries_user ON tracker_entries(user_id, recorded_at DESC);

ALTER TABLE tracker_entries ENABLE ROW LEVEL SECURITY;
CREATE POLICY IF NOT EXISTS "users_own_tracker_entries" ON tracker_entries FOR ALL
    USING (auth.uid() = user_id);

-- ============================================================
-- 4. notes — freeform structured information
-- ============================================================
CREATE TABLE IF NOT EXISTS notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    title TEXT,
    content TEXT NOT NULL,
    tags TEXT[] DEFAULT '{}',
    embedding vector(1536),
    source_message_id UUID REFERENCES messages(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_notes_embedding ON notes
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_notes_tags ON notes USING gin(tags);

ALTER TABLE notes ENABLE ROW LEVEL SECURITY;
CREATE POLICY IF NOT EXISTS "users_own_notes" ON notes FOR ALL
    USING (auth.uid() = user_id);

-- ============================================================
-- 5. scheduled_actions — deferred execution at a future time
-- ============================================================
CREATE TABLE IF NOT EXISTS scheduled_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    action_type TEXT NOT NULL,
    payload JSONB DEFAULT '{}',
    execute_at TIMESTAMPTZ NOT NULL,
    rrule TEXT,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'executed', 'cancelled', 'failed')),
    last_executed_at TIMESTAMPTZ,
    source_message_id UUID REFERENCES messages(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_scheduled_pending ON scheduled_actions(execute_at)
    WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_scheduled_user ON scheduled_actions(user_id, status);

ALTER TABLE scheduled_actions ENABLE ROW LEVEL SECURITY;
CREATE POLICY IF NOT EXISTS "users_own_scheduled" ON scheduled_actions FOR ALL
    USING (auth.uid() = user_id);

-- ============================================================
-- 6. collections — ephemeral groupings of items
-- ============================================================
CREATE TABLE IF NOT EXISTS collections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    name TEXT NOT NULL,
    description TEXT,
    item_ids UUID[] DEFAULT '{}',
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_collections_user ON collections(user_id) WHERE active = true;

ALTER TABLE collections ENABLE ROW LEVEL SECURITY;
CREATE POLICY IF NOT EXISTS "users_own_collections" ON collections FOR ALL
    USING (auth.uid() = user_id);
