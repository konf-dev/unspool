-- Error log (operational, no RLS — admin-only access)
CREATE TABLE IF NOT EXISTS error_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trace_id TEXT,
    user_id TEXT,
    source TEXT NOT NULL,
    error_type TEXT NOT NULL,
    error_message TEXT,
    stacktrace TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_error_log_created ON error_log(created_at DESC);
CREATE INDEX idx_error_log_source ON error_log(source);

-- LLM usage tracking (operational, no RLS — admin-only access)
CREATE TABLE IF NOT EXISTS llm_usage (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trace_id TEXT,
    user_id TEXT,
    pipeline TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_llm_usage_created ON llm_usage(created_at DESC);
CREATE INDEX idx_llm_usage_user ON llm_usage(user_id);
