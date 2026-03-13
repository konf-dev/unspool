-- HNSW indexes for vector similarity search
-- m=16, ef_construction=64 is a good default for <1M rows
CREATE INDEX idx_items_embedding ON items
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_memories_embedding ON memories
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- Full-text search columns for hybrid retrieval
ALTER TABLE items ADD COLUMN search_text tsvector
  GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(raw_text, '') || ' ' || coalesce(interpreted_action, ''))
  ) STORED;

ALTER TABLE memories ADD COLUMN search_text tsvector
  GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(content, ''))
  ) STORED;

CREATE INDEX idx_items_search ON items USING gin(search_text);
CREATE INDEX idx_memories_search ON memories USING gin(search_text);

-- Fix calendar_events: rename title -> summary, add missing columns
-- to match Google Calendar API field names used in code
ALTER TABLE calendar_events RENAME COLUMN title TO summary;
ALTER TABLE calendar_events ADD COLUMN location TEXT;
ALTER TABLE calendar_events ADD COLUMN description TEXT;
ALTER TABLE calendar_events ADD COLUMN is_all_day BOOLEAN DEFAULT false;
ALTER TABLE calendar_events ADD COLUMN updated_at TIMESTAMPTZ DEFAULT now();

-- Add updated_at to subscriptions (referenced in update_subscription)
ALTER TABLE subscriptions ADD COLUMN updated_at TIMESTAMPTZ DEFAULT now();

-- Add unique constraint on oauth_tokens (user_id, provider) for upsert
-- Drop the existing user_id unique constraint first since we want per-provider uniqueness
ALTER TABLE oauth_tokens DROP CONSTRAINT IF EXISTS oauth_tokens_user_id_key;
ALTER TABLE oauth_tokens ADD CONSTRAINT oauth_tokens_user_provider_unique UNIQUE(user_id, provider);

-- Add updated_at to entities (referenced in save_entity upsert)
ALTER TABLE entities ADD COLUMN updated_at TIMESTAMPTZ DEFAULT now();

-- Add unique constraint on entities for upsert in save_entity
ALTER TABLE entities ADD CONSTRAINT entities_user_name_type_unique UNIQUE(user_id, name, type);
