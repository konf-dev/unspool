from typing import Annotated, TypedDict, List
from langchain_core.messages import AnyMessage
import operator

class HotPathState(TypedDict):
    """The state of the Conversational Agent throughout its execution graph."""
    
    user_id: str
    session_id: str
    
    # The history of the conversation (Langchain message objects)
    messages: Annotated[List[AnyMessage], operator.add]
    
    # Track the current loop iteration to prevent infinite loops
    iteration: int
    
    # Current timezone and time
    current_time_iso: str
    timezone: str
    
    # System Context (e.g. recent memories fetched proactively)
    context_string: str
