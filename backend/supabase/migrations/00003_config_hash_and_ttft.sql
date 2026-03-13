-- Add config versioning and TTFT columns to llm_usage
ALTER TABLE llm_usage ADD COLUMN IF NOT EXISTS config_hash TEXT;
ALTER TABLE llm_usage ADD COLUMN IF NOT EXISTS ttft_ms INT;

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
