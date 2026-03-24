-- Migration: Switch embedding dimension from 1536 (OpenAI) to 768 (Gemini gemini-embedding-001)
-- Pre-launch: safe to wipe existing embeddings (no production data)

-- Wipe existing embeddings
UPDATE graph_nodes SET embedding = NULL;

-- Change column dimension
ALTER TABLE graph_nodes ALTER COLUMN embedding TYPE vector(768);

-- Recreate HNSW index for new dimension
DROP INDEX IF EXISTS idx_graph_nodes_embedding;
CREATE INDEX idx_graph_nodes_embedding ON graph_nodes USING hnsw (embedding vector_cosine_ops);
