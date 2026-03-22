-- Enable pgvector extension if not already enabled
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ==========================================
-- 1. EVENT STREAM (The immutable source of truth)
-- ==========================================
CREATE TABLE IF NOT EXISTS event_stream (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
    event_type TEXT NOT NULL,          -- e.g., 'MessageReceived', 'NodeCreated', 'EdgeAdded', 'StatusUpdated'
    payload JSONB NOT NULL DEFAULT '{}'::jsonb, -- The data associated with the event
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for quickly fetching a user's recent events (helpful for the Archiver to check state)
CREATE INDEX idx_event_stream_user_id_created_at ON event_stream(user_id, created_at DESC);

-- ==========================================
-- 2. GRAPH NODES (The Entities/Concepts)
-- ==========================================
CREATE TABLE IF NOT EXISTS graph_nodes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
    content TEXT NOT NULL,             -- The actual text/concept (e.g., 'Buy milk', 'Sarah', 'Thesis')
    node_type TEXT NOT NULL,           -- Soft categorization (e.g., 'concept', 'action', 'metric', 'person', 'message')
    embedding vector(1536),            -- OpenAI small embeddings (or halfvec if supported)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- HNSW Index for fast semantic vector search over nodes
CREATE INDEX idx_graph_nodes_embedding ON graph_nodes USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_graph_nodes_user_id ON graph_nodes(user_id);
CREATE INDEX idx_graph_nodes_node_type ON graph_nodes(node_type);

-- ==========================================
-- 3. GRAPH EDGES (The Relationships)
-- ==========================================
CREATE TABLE IF NOT EXISTS graph_edges (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
    source_node_id UUID NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
    target_node_id UUID NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
    edge_type TEXT NOT NULL,           -- e.g., 'HAS_DEADLINE', 'IS_STATUS', 'RELATES_TO', 'TRACKS_METRIC'
    weight FLOAT DEFAULT 1.0,          -- Can decay over time to prune old/weak connections
    metadata JSONB DEFAULT '{}'::jsonb,-- e.g., {"date": "2024-05-12T00:00:00Z"} for deadlines, or {"value": 3} for metrics
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Prevent exact duplicate edges between the same two nodes
    UNIQUE(source_node_id, target_node_id, edge_type)
);

CREATE INDEX idx_graph_edges_user_id ON graph_edges(user_id);
CREATE INDEX idx_graph_edges_source ON graph_edges(source_node_id);
CREATE INDEX idx_graph_edges_target ON graph_edges(target_node_id);
CREATE INDEX idx_graph_edges_type ON graph_edges(edge_type);

-- ==========================================
-- 4. TRIGGERS for updated_at
-- ==========================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
   NEW.updated_at = NOW();
   RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_graph_nodes_updated_at
BEFORE UPDATE ON graph_nodes
FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

CREATE TRIGGER update_graph_edges_updated_at
BEFORE UPDATE ON graph_edges
FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

-- ==========================================
-- 5. ROW LEVEL SECURITY (Zero-Trust)
-- ==========================================
-- Enable RLS on all tables
ALTER TABLE event_stream ENABLE ROW LEVEL SECURITY;
ALTER TABLE graph_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE graph_edges ENABLE ROW LEVEL SECURITY;

-- Policies for event_stream
CREATE POLICY "Users can view their own events" 
ON event_stream FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own events" 
ON event_stream FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Policies for graph_nodes
CREATE POLICY "Users can view their own nodes" 
ON graph_nodes FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own nodes" 
ON graph_nodes FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own nodes" 
ON graph_nodes FOR UPDATE USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete their own nodes" 
ON graph_nodes FOR DELETE USING (auth.uid() = user_id);

-- Policies for graph_edges
CREATE POLICY "Users can view their own edges" 
ON graph_edges FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own edges" 
ON graph_edges FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own edges" 
ON graph_edges FOR UPDATE USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete their own edges" 
ON graph_edges FOR DELETE USING (auth.uid() = user_id);
