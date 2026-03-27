-- V2 Memory System: metadata column + updated views for rich extraction

-- Add metadata column to graph_nodes if not exists
ALTER TABLE graph_nodes ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';

-- Drop and recreate vw_actionable (column type changes: deadline TEXT → TIMESTAMPTZ, new columns)
DROP VIEW IF EXISTS vw_actionable;
CREATE VIEW vw_actionable AS
SELECT node_id, user_id, content, node_type, created_at, deadline, deadline_type, actionable, tense
FROM (
    SELECT
        n.id AS node_id,
        n.user_id,
        n.content,
        n.node_type,
        n.created_at,
        (dl_edge.metadata->>'date')::timestamptz AS deadline,
        COALESCE(dl_edge.metadata->>'deadline_type', 'soft') AS deadline_type,
        COALESCE((n.metadata->>'actionable')::boolean, true) AS actionable,
        COALESCE(n.metadata->'temporal'->>'tense', 'future') AS tense,
        ROW_NUMBER() OVER (
            PARTITION BY n.id
            ORDER BY (dl_edge.metadata->>'date')::timestamptz ASC NULLS LAST
        ) AS rn
    FROM graph_nodes n
    JOIN graph_edges status_edge
        ON status_edge.source_node_id = n.id
        AND status_edge.edge_type = 'IS_STATUS'
    JOIN graph_nodes status_node
        ON status_node.id = status_edge.target_node_id
        AND UPPER(status_node.content) = 'OPEN'
    LEFT JOIN graph_edges dl_edge
        ON dl_edge.source_node_id = n.id
        AND dl_edge.edge_type = 'HAS_DEADLINE'
    WHERE n.node_type IN ('memory', 'action', 'concept')  -- backward compat
      AND COALESCE((n.metadata->>'actionable')::boolean, true) = true
      AND COALESCE(n.metadata->'temporal'->>'tense', 'future') != 'past'
) sub WHERE rn = 1;

-- Drop and recreate vw_metrics (column type changes: value TEXT → NUMERIC, logged_at → event_time)
DROP VIEW IF EXISTS vw_metrics;
CREATE VIEW vw_metrics AS
SELECT
    metric_node.id AS metric_node_id,
    metric_node.user_id,
    metric_node.content AS metric_name,
    entry_node.content AS entry_content,
    (track_edge.metadata->>'value')::numeric AS value,
    track_edge.metadata->>'unit' AS unit,
    COALESCE(
        (track_edge.metadata->>'logged_at')::timestamptz,
        entry_node.created_at
    ) AS event_time
FROM graph_nodes metric_node
JOIN graph_edges track_edge
    ON track_edge.target_node_id = metric_node.id
    AND track_edge.edge_type = 'TRACKS_METRIC'
JOIN graph_nodes entry_node
    ON entry_node.id = track_edge.source_node_id;

-- Index on metadata for actionable flag queries
CREATE INDEX IF NOT EXISTS idx_graph_nodes_metadata_actionable
    ON graph_nodes USING btree (((metadata->>'actionable')::boolean))
    WHERE metadata->>'actionable' IS NOT NULL;
