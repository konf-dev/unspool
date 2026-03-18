-- graph_lab_sql schema — Postgres-native graph memory
-- Requires Postgres 14+ and pgvector extension

CREATE EXTENSION IF NOT EXISTS vector;

-- raw_stream (user/assistant message log)
CREATE TABLE IF NOT EXISTS raw_stream (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    source TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_stream_user_time ON raw_stream (user_id, created_at DESC);

-- memory_nodes (facts, tasks, people, dates, feelings)
CREATE TABLE IF NOT EXISTS memory_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    content TEXT NOT NULL,
    node_type TEXT,
    embedding vector(1536),
    status TEXT DEFAULT 'active',
    source_stream_id UUID REFERENCES raw_stream(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    last_activated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_node_user ON memory_nodes (user_id);
CREATE INDEX IF NOT EXISTS idx_node_activated ON memory_nodes (user_id, last_activated_at DESC);
CREATE INDEX IF NOT EXISTS idx_node_content ON memory_nodes (user_id, lower(content));
CREATE INDEX IF NOT EXISTS idx_node_embedding ON memory_nodes USING hnsw (embedding vector_cosine_ops);

-- memory_edges (bi-temporal relationships)
CREATE TABLE IF NOT EXISTS memory_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    from_node_id UUID NOT NULL REFERENCES memory_nodes(id) ON DELETE CASCADE,
    to_node_id UUID NOT NULL REFERENCES memory_nodes(id) ON DELETE CASCADE,
    relation_type TEXT,
    strength FLOAT DEFAULT 1.0,
    valid_from TIMESTAMPTZ DEFAULT now(),
    valid_until TIMESTAMPTZ,
    recorded_at TIMESTAMPTZ DEFAULT now(),
    decay_exempt BOOLEAN DEFAULT false,
    source_stream_id UUID REFERENCES raw_stream(id)
);
CREATE INDEX IF NOT EXISTS idx_edge_from_current ON memory_edges (from_node_id) WHERE valid_until IS NULL;
CREATE INDEX IF NOT EXISTS idx_edge_to_current ON memory_edges (to_node_id) WHERE valid_until IS NULL;
CREATE INDEX IF NOT EXISTS idx_edge_user_current ON memory_edges (user_id) WHERE valid_until IS NULL;

-- node_neighbors (materialized cache — updated on edge writes, read during retrieval)
CREATE TABLE IF NOT EXISTS node_neighbors (
    edge_id UUID NOT NULL REFERENCES memory_edges(id) ON DELETE CASCADE,
    node_id UUID NOT NULL REFERENCES memory_nodes(id) ON DELETE CASCADE,
    neighbor_id UUID NOT NULL REFERENCES memory_nodes(id) ON DELETE CASCADE,
    relation_type TEXT,
    strength FLOAT NOT NULL,
    direction TEXT NOT NULL,
    PRIMARY KEY (edge_id, direction)
);
CREATE INDEX IF NOT EXISTS idx_neighbors_node ON node_neighbors (node_id);
CREATE INDEX IF NOT EXISTS idx_neighbors_neighbor ON node_neighbors (neighbor_id);
