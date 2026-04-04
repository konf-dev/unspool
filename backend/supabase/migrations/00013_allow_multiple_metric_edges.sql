-- Allow multiple TRACKS_METRIC edges between the same source and target nodes.
-- Each metric entry (e.g., "spent $50", "spent $30") must be its own edge row
-- with a unique logged_at timestamp, rather than being upserted into a single row.
--
-- Replace the blanket unique constraint with a partial unique index that only
-- enforces uniqueness for non-metric edge types. Metric edges are append-only.

-- Drop the original constraint
ALTER TABLE graph_edges
    DROP CONSTRAINT IF EXISTS graph_edges_source_node_id_target_node_id_edge_type_key;

-- Enforce uniqueness only for non-metric edges (status, deadline, relates_to, etc.)
CREATE UNIQUE INDEX graph_edges_unique_non_metric
    ON graph_edges (source_node_id, target_node_id, edge_type)
    WHERE edge_type != 'TRACKS_METRIC';
