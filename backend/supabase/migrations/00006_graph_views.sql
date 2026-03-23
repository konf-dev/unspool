-- vw_messages: Projects MessageReceived/AgentReplied events into a chat history view
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
WHERE e.event_type IN ('MessageReceived', 'AgentReplied')
ORDER BY e.created_at;

-- vw_actionable: OPEN action nodes with optional deadlines
CREATE OR REPLACE VIEW vw_actionable AS
SELECT
    n.id AS node_id,
    n.user_id,
    n.content,
    n.node_type,
    n.created_at,
    dl_edge.metadata->>'date' AS deadline,
    dl_edge.metadata->>'deadline_type' AS deadline_type
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
WHERE n.node_type IN ('action', 'concept');

-- vw_timeline: Nodes with deadlines ordered by date
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
WHERE dl_edge.metadata->>'date' IS NOT NULL
ORDER BY dl_edge.metadata->>'date';

-- vw_metrics: Metric tracking aggregation
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
    ON entry_node.id = track_edge.source_node_id
ORDER BY entry_node.created_at DESC;
