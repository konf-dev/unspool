-- Error log table for centralized error tracking.
-- Queryable via /admin/errors instead of grepping Railway logs.

CREATE TABLE IF NOT EXISTS error_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id TEXT,
    user_id UUID REFERENCES auth.users(id),
    source TEXT NOT NULL,          -- e.g. 'graph.ingest', 'agent.run', 'job.detect_patterns'
    error_type TEXT NOT NULL,      -- exception class name
    error_message TEXT NOT NULL,
    stacktrace TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_error_log_created_at ON error_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_error_log_source ON error_log (source);
CREATE INDEX IF NOT EXISTS idx_error_log_user_id ON error_log (user_id);

ALTER TABLE error_log ENABLE ROW LEVEL SECURITY;

-- Admin-only access (service role key).
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename = 'error_log' AND policyname = 'Service role full access on error_log'
  ) THEN
    CREATE POLICY "Service role full access on error_log"
      ON error_log FOR ALL USING (auth.role() = 'service_role');
  END IF;
END $$;
