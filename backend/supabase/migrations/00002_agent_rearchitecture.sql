-- Agent rearchitecture migration
-- Drops unused tables, simplifies llm_usage, adds conversation_summaries

-- ============================================================
-- 1. Drop unused tables
-- ============================================================
DROP TABLE IF EXISTS experiment_assignments;

-- ============================================================
-- 2. Simplify llm_usage (pipeline/variant are pipeline-era columns)
-- ============================================================
ALTER TABLE llm_usage ALTER COLUMN step_id DROP NOT NULL;
ALTER TABLE llm_usage ADD COLUMN IF NOT EXISTS tool_name TEXT;

-- Drop pipeline and variant columns (data preserved in Langfuse traces)
ALTER TABLE llm_usage DROP COLUMN IF EXISTS pipeline;
ALTER TABLE llm_usage DROP COLUMN IF EXISTS variant;

-- Recreate trace_summary view without pipeline/variant
DROP VIEW IF EXISTS trace_summary;
CREATE OR REPLACE VIEW trace_summary AS
SELECT
    trace_id,
    user_id,
    tool_name,
    config_hash,
    SUM(input_tokens) as total_input_tokens,
    SUM(output_tokens) as total_output_tokens,
    SUM(latency_ms) as total_latency_ms,
    MIN(ttft_ms) as first_token_ms,
    COUNT(*) as llm_calls,
    MIN(created_at) as started_at,
    array_agg(step_id ORDER BY created_at) as steps
FROM llm_usage
GROUP BY trace_id, user_id, tool_name, config_hash;

-- ============================================================
-- 3. Add conversation_summaries table
-- ============================================================
CREATE TABLE IF NOT EXISTS conversation_summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    summary TEXT NOT NULL,
    message_range_start TIMESTAMPTZ NOT NULL,
    message_range_end TIMESTAMPTZ NOT NULL,
    message_count INT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conv_summary_user
    ON conversation_summaries(user_id, message_range_end DESC);

ALTER TABLE conversation_summaries ENABLE ROW LEVEL SECURITY;
CREATE POLICY IF NOT EXISTS "users_own_summaries"
    ON conversation_summaries FOR ALL USING (auth.uid() = user_id);
