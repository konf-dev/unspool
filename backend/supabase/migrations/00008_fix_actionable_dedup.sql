-- Fix vw_actionable to deduplicate nodes that have multiple HAS_DEADLINE edges.
-- DISTINCT ON picks the earliest deadline per node.
CREATE OR REPLACE VIEW vw_actionable AS
SELECT DISTINCT ON (n.id)
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
WHERE n.node_type IN ('action', 'concept')
ORDER BY n.id, dl_edge.metadata->>'date' ASC NULLS LAST;
