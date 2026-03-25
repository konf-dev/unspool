from typing import List, Optional, Any
from pydantic import BaseModel, Field

class ExtractedNode(BaseModel):
    content: str = Field(..., description="The semantic content of the node, e.g., 'Call Mom', 'Thesis', 'Stressed'")
    node_type: str = Field(
        ..., 
        description="Soft classification of the node. Must be one of: 'concept', 'action', 'metric', 'person', 'emotion'."
    )
    
class EdgeMetadata(BaseModel):
    date: Optional[str] = Field(None, description="ISO8601 timestamp for HAS_DEADLINE or EXPERIENCED_DURING edges.")
    value: Optional[float] = Field(None, description="Numeric value for TRACKS_METRIC edges.")
    unit: Optional[str] = Field(None, description="Unit for the numeric value.")

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
