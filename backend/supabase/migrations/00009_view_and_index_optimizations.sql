-- Fix vw_actionable: Replace DISTINCT ON with ROW_NUMBER to avoid dual-sort collision.
-- Also casts deadline to timestamptz for correct ordering.
CREATE OR REPLACE VIEW vw_actionable AS
SELECT node_id, user_id, content, node_type, created_at, deadline, deadline_type
FROM (
    SELECT
        n.id AS node_id,
        n.user_id,
        n.content,
        n.node_type,
        n.created_at,
        dl_edge.metadata->>'date' AS deadline,
        dl_edge.metadata->>'deadline_type' AS deadline_type,
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
        AND status_node.content = 'OPEN'
        AND status_node.node_type = 'system_status'
    LEFT JOIN graph_edges dl_edge
        ON dl_edge.source_node_id = n.id
        AND dl_edge.edge_type = 'HAS_DEADLINE'
    WHERE n.node_type IN ('action', 'concept')
) sub WHERE rn = 1;

-- Fix vw_messages: Remove ORDER BY from view definition — let callers sort.
CREATE OR REPLACE VIEW vw_messages AS
SELECT
    e.id,
    e.user_id,
    CASE
        WHEN e.event_type = 'MessageReceived' THEN 'user'
        WHEN e.event_type = 'AgentReplied' THEN 'assistant'
    END AS role,
    e.payload->>'content' AS content,
    e.payload->'metadata' AS metadata,
    e.created_at
FROM event_stream e
WHERE e.event_type IN ('MessageReceived', 'AgentReplied');

-- Fix vw_timeline: Remove ORDER BY from view definition.
CREATE OR REPLACE VIEW vw_timeline AS
SELECT
    n.id AS node_id,
    n.user_id,
    n.content,
    n.node_type,
    dl_edge.metadata->>'date' AS deadline,
    dl_edge.metadata->>'deadline_type' AS deadline_type,
    n.created_at
FROM graph_nodes n
JOIN graph_edges dl_edge
    ON dl_edge.source_node_id = n.id
    AND dl_edge.edge_type = 'HAS_DEADLINE'
WHERE dl_edge.metadata->>'date' IS NOT NULL;

-- Fix vw_metrics: Remove ORDER BY from view definition.
CREATE OR REPLACE VIEW vw_metrics AS
SELECT
    metric_node.id AS metric_node_id,
    metric_node.user_id,
    metric_node.content AS metric_name,
    entry_node.content AS entry_content,
    track_edge.metadata->>'value' AS value,
    track_edge.metadata->>'unit' AS unit,
    entry_node.created_at AS logged_at
FROM graph_nodes metric_node
JOIN graph_edges track_edge
    ON track_edge.target_node_id = metric_node.id
    AND track_edge.edge_type = 'TRACKS_METRIC'
JOIN graph_nodes entry_node
    ON entry_node.id = track_edge.source_node_id;

-- Composite indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_graph_nodes_user_type ON graph_nodes(user_id, node_type);
CREATE INDEX IF NOT EXISTS idx_graph_edges_source_type ON graph_edges(source_node_id, edge_type);
