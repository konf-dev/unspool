from typing import List, Optional, Any
from pydantic import BaseModel, Field


class NodeMetadata(BaseModel):
    entities: list[dict] = Field(
        default=[],
        description='Recognized entities: [{"text": "Mom", "likely": "person"}, {"text": "297kr", "likely": "currency", "value": 297, "unit": "kr"}]',
    )
    temporal: dict = Field(
        default={},
        description='Temporal signals: {"tense": "past"|"present"|"future", "dates": ["2026-03-26T16:00:00Z"]}',
    )
    quantities: list[dict] = Field(
        default=[],
        description='Extracted quantities: [{"value": 5, "unit": "km"}]',
    )
    actionable: bool = Field(
        default=True,
        description="Soft signal: does this look like something to do? False for past-tense activities, emotions, facts.",
    )


class ExtractedNode(BaseModel):
    content: str = Field(..., description="The semantic content of the node, e.g., 'Call Mom', 'Thesis', 'Stressed'")
    node_type: str = Field(
        ...,
        description="Soft classification. Default 'memory' (catch-all). Use 'person' for people, 'system_status' for OPEN/DONE only."
    )
    metadata: NodeMetadata = Field(default_factory=NodeMetadata)


class EdgeMetadata(BaseModel):
    date: Optional[str] = Field(None, description="ISO8601 timestamp for HAS_DEADLINE or EXPERIENCED_DURING edges.")
    value: Optional[float] = Field(None, description="Numeric value for TRACKS_METRIC edges.")
    unit: Optional[str] = Field(None, description="Unit for the numeric value.")
    logged_at: Optional[str] = Field(None, description="When the metric event actually happened (ISO8601). For TRACKS_METRIC edges.")
    deadline_type: Optional[str] = Field(None, description="hard/soft/routine. For HAS_DEADLINE edges.")

class ExtractedEdge(BaseModel):
    source_content: str = Field(..., description="The content of the source node. MUST match a node's content exactly.")
    target_content: str = Field(..., description="The content of the target node. MUST match a node's content exactly.")
    edge_type: str = Field(
        ...,
        description="The relationship. Must be one of: 'HAS_DEADLINE', 'IS_STATUS', 'RELATES_TO', 'TRACKS_METRIC', 'EXPERIENCED_DURING', 'DEPENDS_ON', 'PART_OF'"
    )
    metadata: Optional[EdgeMetadata] = Field(
        default=None, 
        description="Optional metadata for the edge."
    )

class ExtractionResult(BaseModel):
    nodes: List[ExtractedNode] = Field(..., description="A list of all entities/concepts found in the text.")
    edges: List[ExtractedEdge] = Field(..., description="A list of relationships connecting the extracted nodes.")
