-- Migration tracking table
-- Records which migrations have been applied, when, and by whom.
-- This is the bootstrap migration — once applied, the runner tracks everything automatically.

CREATE TABLE IF NOT EXISTS public.schema_migrations (
  version    TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ DEFAULT now(),
  checksum   TEXT,
  applied_by TEXT DEFAULT current_user
);

-- Backfill: mark all existing migrations (00001-00011) as already applied.
-- Checksums are omitted for backfilled entries (can't verify retroactively).
INSERT INTO public.schema_migrations (version, applied_at, checksum) VALUES
  ('00001_v2_core_schema', now(), NULL),
  ('00002_user_profiles', now(), NULL),
  ('00003_subscriptions_and_push', now(), NULL),
  ('00004_proactive_and_scheduled', now(), NULL),
  ('00005_operational', now(), NULL),
  ('00006_graph_views', now(), NULL),
  ('00007_gemini_embeddings', now(), NULL),
  ('00008_fix_actionable_dedup', now(), NULL),
  ('00009_view_and_index_optimizations', now(), NULL),
  ('00010_graph_node_unique_constraint', now(), NULL),
  ('00011_migration_tracking', now(), NULL)
ON CONFLICT (version) DO NOTHING;
