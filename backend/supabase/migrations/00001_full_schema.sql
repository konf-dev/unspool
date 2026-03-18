-- Unspool full schema — single migration (replaces 00001-00004)
-- Requires Postgres 14+ with pgvector extension

CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- 1. user_profiles
-- ============================================================
CREATE TABLE user_profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id),
  display_name TEXT,
  timezone TEXT,
  tone_preference TEXT DEFAULT 'casual',
  length_preference TEXT DEFAULT 'medium',
  pushiness_preference TEXT DEFAULT 'gentle',
  uses_emoji BOOLEAN DEFAULT false,
  primary_language TEXT DEFAULT 'en',
  google_calendar_connected BOOLEAN DEFAULT false,
  notification_sent_today BOOLEAN DEFAULT false,
  last_interaction_at TIMESTAMPTZ,
  patterns JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Auto-create user_profiles on signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.user_profiles (id) VALUES (NEW.id);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ============================================================
-- 2. messages
-- ============================================================
CREATE TABLE messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  metadata JSONB DEFAULT '{}'
);
CREATE INDEX idx_messages_user_created ON messages(user_id, created_at DESC);

-- ============================================================
-- 3. items
-- ============================================================
CREATE TABLE items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  raw_text TEXT NOT NULL,
  interpreted_action TEXT NOT NULL,
  deadline_type TEXT CHECK (deadline_type IN ('hard', 'soft', 'none')),
  deadline_at TIMESTAMPTZ,
  urgency_score FLOAT DEFAULT 0.0,
  energy_estimate TEXT CHECK (energy_estimate IN ('low', 'medium', 'high')),
  status TEXT DEFAULT 'open' CHECK (status IN ('open', 'done', 'expired', 'deprioritized')),
  source_message_id UUID REFERENCES messages(id),
  entity_ids UUID[] DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  last_surfaced_at TIMESTAMPTZ,
  nudge_after TIMESTAMPTZ,
  embedding vector(1024),
  search_text tsvector GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(raw_text, '') || ' ' || coalesce(interpreted_action, ''))
  ) STORED
);
CREATE INDEX idx_items_user_status ON items(user_id, status);
CREATE INDEX idx_items_user_deadline ON items(user_id, deadline_at) WHERE status = 'open';
CREATE INDEX idx_items_embedding ON items
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
CREATE INDEX idx_items_search ON items USING gin(search_text);

-- ============================================================
-- 4. item_events
-- ============================================================
CREATE TABLE item_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  item_id UUID NOT NULL REFERENCES items(id),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  event_type TEXT NOT NULL CHECK (event_type IN (
    'created', 'surfaced', 'rescheduled', 'snoozed', 'done', 'expired', 'deprioritized'
  )),
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_item_events_item ON item_events(item_id, created_at DESC);

-- ============================================================
-- 5. memories
-- ============================================================
CREATE TABLE memories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  type TEXT NOT NULL CHECK (type IN ('semantic', 'episodic')),
  content TEXT NOT NULL,
  source_message_id UUID REFERENCES messages(id),
  confidence FLOAT DEFAULT 1.0,
  last_validated_at TIMESTAMPTZ,
  superseded_by UUID REFERENCES memories(id),
  embedding vector(1024),
  created_at TIMESTAMPTZ DEFAULT now(),
  search_text tsvector GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(content, ''))
  ) STORED
);
CREATE INDEX idx_memories_user_type ON memories(user_id, type);
CREATE INDEX idx_memories_embedding ON memories
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
CREATE INDEX idx_memories_search ON memories USING gin(search_text);

-- ============================================================
-- 6. entities
-- ============================================================
CREATE TABLE entities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  name TEXT NOT NULL,
  type TEXT CHECK (type IN ('person', 'project', 'place', 'organization')),
  aliases TEXT[] DEFAULT '{}',
  context TEXT,
  emotional_valence TEXT,
  last_mentioned_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(user_id, name, type)
);
CREATE INDEX idx_entities_user ON entities(user_id);

-- ============================================================
-- 7. recurrences
-- ============================================================
CREATE TABLE recurrences (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  description TEXT NOT NULL,
  rrule TEXT,
  time_of_day TIME,
  source TEXT CHECK (source IN ('inferred', 'calendar', 'explicit')),
  confidence FLOAT DEFAULT 1.0,
  last_triggered_at TIMESTAMPTZ,
  active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Add recurrence FK to items now that recurrences exists
ALTER TABLE items ADD COLUMN recurrence_id UUID REFERENCES recurrences(id);

-- ============================================================
-- 8. calendar_events
-- ============================================================
CREATE TABLE calendar_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  google_event_id TEXT NOT NULL,
  summary TEXT NOT NULL,
  start_at TIMESTAMPTZ NOT NULL,
  end_at TIMESTAMPTZ NOT NULL,
  location TEXT,
  description TEXT,
  is_all_day BOOLEAN DEFAULT false,
  synced_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(user_id, google_event_id)
);
CREATE INDEX idx_calendar_user_start ON calendar_events(user_id, start_at);

-- ============================================================
-- 9. subscriptions
-- ============================================================
CREATE TABLE subscriptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) UNIQUE,
  tier TEXT DEFAULT 'free' CHECK (tier IN ('free', 'paid')),
  stripe_customer_id TEXT,
  stripe_subscription_id TEXT,
  status TEXT DEFAULT 'active' CHECK (status IN ('active', 'cancelled', 'past_due')),
  current_period_end TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- 10. push_subscriptions
-- ============================================================
CREATE TABLE push_subscriptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  endpoint TEXT NOT NULL,
  p256dh TEXT NOT NULL,
  auth_key TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(user_id, endpoint)
);

-- ============================================================
-- 11. llm_usage (service role only, no RLS)
-- ============================================================
CREATE TABLE llm_usage (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  trace_id UUID NOT NULL,
  user_id UUID NOT NULL,
  step_id TEXT NOT NULL,
  pipeline TEXT NOT NULL,
  variant TEXT,
  model TEXT NOT NULL,
  provider TEXT NOT NULL,
  input_tokens INT NOT NULL,
  output_tokens INT NOT NULL,
  latency_ms INT NOT NULL,
  config_hash TEXT,
  ttft_ms INT,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_llm_usage_created ON llm_usage(created_at DESC);

-- Trace summary view for observability
CREATE OR REPLACE VIEW trace_summary AS
SELECT
    trace_id,
    user_id,
    pipeline,
    variant,
    config_hash,
    SUM(input_tokens) as total_input_tokens,
    SUM(output_tokens) as total_output_tokens,
    SUM(latency_ms) as total_latency_ms,
    MIN(ttft_ms) as first_token_ms,
    COUNT(*) as llm_calls,
    MIN(created_at) as started_at,
    array_agg(step_id ORDER BY created_at) as steps
FROM llm_usage
GROUP BY trace_id, user_id, pipeline, variant, config_hash;

-- ============================================================
-- 12. experiment_assignments
-- ============================================================
CREATE TABLE experiment_assignments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  experiment TEXT NOT NULL,
  variant TEXT NOT NULL,
  assigned_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(user_id, experiment)
);

-- ============================================================
-- 13. oauth_tokens
-- ============================================================
CREATE TABLE oauth_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  provider TEXT NOT NULL DEFAULT 'google',
  refresh_token TEXT NOT NULL,
  scopes TEXT[] DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(user_id, provider)
);

-- ============================================================
-- 14. memory_nodes (graph memory — facts, tasks, people, dates, feelings)
-- ============================================================
CREATE TABLE memory_nodes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  content TEXT NOT NULL,
  node_type TEXT,
  embedding halfvec(1024),
  status TEXT DEFAULT 'active',
  source_message_id UUID REFERENCES messages(id),
  created_at TIMESTAMPTZ DEFAULT now(),
  last_activated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_memory_node_user ON memory_nodes(user_id);
CREATE INDEX idx_memory_node_activated ON memory_nodes(user_id, last_activated_at DESC);
CREATE INDEX idx_memory_node_content ON memory_nodes(user_id, lower(content));
CREATE INDEX idx_memory_node_embedding ON memory_nodes
  USING hnsw (embedding halfvec_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- ============================================================
-- 15. memory_edges (graph memory — bi-temporal relationships)
-- ============================================================
CREATE TABLE memory_edges (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  from_node_id UUID NOT NULL REFERENCES memory_nodes(id) ON DELETE CASCADE,
  to_node_id UUID NOT NULL REFERENCES memory_nodes(id) ON DELETE CASCADE,
  relation_type TEXT,
  strength FLOAT DEFAULT 1.0,
  valid_from TIMESTAMPTZ DEFAULT now(),
  valid_until TIMESTAMPTZ,
  recorded_at TIMESTAMPTZ DEFAULT now(),
  decay_exempt BOOLEAN DEFAULT false,
  source_message_id UUID REFERENCES messages(id)
);
CREATE INDEX idx_memory_edge_from_current ON memory_edges(from_node_id) WHERE valid_until IS NULL;
CREATE INDEX idx_memory_edge_to_current ON memory_edges(to_node_id) WHERE valid_until IS NULL;
CREATE INDEX idx_memory_edge_user_current ON memory_edges(user_id) WHERE valid_until IS NULL;

-- ============================================================
-- 16. node_neighbors (graph memory — materialized neighbor cache)
-- ============================================================
CREATE TABLE node_neighbors (
  edge_id UUID NOT NULL REFERENCES memory_edges(id) ON DELETE CASCADE,
  node_id UUID NOT NULL REFERENCES memory_nodes(id) ON DELETE CASCADE,
  neighbor_id UUID NOT NULL REFERENCES memory_nodes(id) ON DELETE CASCADE,
  relation_type TEXT,
  strength FLOAT NOT NULL,
  direction TEXT NOT NULL,
  PRIMARY KEY (edge_id, direction)
);
CREATE INDEX idx_node_neighbors_node ON node_neighbors(node_id);
CREATE INDEX idx_node_neighbors_neighbor ON node_neighbors(neighbor_id);

-- ============================================================
-- RLS — all user-facing tables
-- ============================================================
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE items ENABLE ROW LEVEL SECURITY;
ALTER TABLE item_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE recurrences ENABLE ROW LEVEL SECURITY;
ALTER TABLE calendar_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE push_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE experiment_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE oauth_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_edges ENABLE ROW LEVEL SECURITY;
ALTER TABLE node_neighbors ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY "users_own_profile" ON user_profiles FOR ALL USING (auth.uid() = id);
CREATE POLICY "users_own_messages" ON messages FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "users_own_items" ON items FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "users_own_item_events" ON item_events FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "users_own_memories" ON memories FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "users_own_entities" ON entities FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "users_own_recurrences" ON recurrences FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "users_own_calendar" ON calendar_events FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "users_own_subscription" ON subscriptions FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "users_own_push" ON push_subscriptions FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "users_own_experiments" ON experiment_assignments FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "users_own_oauth" ON oauth_tokens FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "users_own_memory_nodes" ON memory_nodes FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "users_own_memory_edges" ON memory_edges FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "users_own_node_neighbors" ON node_neighbors FOR ALL USING (
  EXISTS (
    SELECT 1 FROM memory_edges me
    WHERE me.id = node_neighbors.edge_id
    AND me.user_id = auth.uid()
  )
);
