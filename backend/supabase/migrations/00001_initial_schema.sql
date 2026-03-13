-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. user_profiles
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

-- 2. messages
CREATE TABLE messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  metadata JSONB DEFAULT '{}'
);
CREATE INDEX idx_messages_user_created ON messages(user_id, created_at DESC);

-- 3. items (with recurrence_id FK added after recurrences table)
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
  embedding vector(1536)
);
CREATE INDEX idx_items_user_status ON items(user_id, status);
CREATE INDEX idx_items_user_deadline ON items(user_id, deadline_at) WHERE status = 'open';

-- 4. item_events (user_id denormalized for RLS)
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

-- 5. memories
CREATE TABLE memories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  type TEXT NOT NULL CHECK (type IN ('semantic', 'episodic')),
  content TEXT NOT NULL,
  source_message_id UUID REFERENCES messages(id),
  confidence FLOAT DEFAULT 1.0,
  last_validated_at TIMESTAMPTZ,
  superseded_by UUID REFERENCES memories(id),
  embedding vector(1536),
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_memories_user_type ON memories(user_id, type);

-- 6. entities
CREATE TABLE entities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  name TEXT NOT NULL,
  type TEXT CHECK (type IN ('person', 'project', 'place', 'organization')),
  aliases TEXT[] DEFAULT '{}',
  context TEXT,
  emotional_valence TEXT,
  last_mentioned_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_entities_user ON entities(user_id);

-- 7. recurrences
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

-- 8. calendar_events
CREATE TABLE calendar_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  google_event_id TEXT NOT NULL,
  title TEXT NOT NULL,
  start_at TIMESTAMPTZ NOT NULL,
  end_at TIMESTAMPTZ NOT NULL,
  synced_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(user_id, google_event_id)
);
CREATE INDEX idx_calendar_user_start ON calendar_events(user_id, start_at);

-- 9. subscriptions
CREATE TABLE subscriptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) UNIQUE,
  tier TEXT DEFAULT 'free' CHECK (tier IN ('free', 'paid')),
  stripe_customer_id TEXT,
  stripe_subscription_id TEXT,
  status TEXT DEFAULT 'active' CHECK (status IN ('active', 'cancelled', 'past_due')),
  current_period_end TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- 10. push_subscriptions
CREATE TABLE push_subscriptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  endpoint TEXT NOT NULL,
  p256dh TEXT NOT NULL,
  auth_key TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(user_id, endpoint)
);

-- 11. llm_usage (service role only, no RLS)
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
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_llm_usage_created ON llm_usage(created_at DESC);

-- 12. experiment_assignments
CREATE TABLE experiment_assignments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  experiment TEXT NOT NULL,
  variant TEXT NOT NULL,
  assigned_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(user_id, experiment)
);

-- 13. oauth_tokens
CREATE TABLE oauth_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) UNIQUE,
  provider TEXT NOT NULL DEFAULT 'google',
  refresh_token TEXT NOT NULL,
  scopes TEXT[] DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
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

-- RLS on all user-facing tables
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

-- RLS Policies (all user-facing tables)
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
