from typing import Annotated, TypedDict, Any
from langchain_core.messages import AnyMessage
import operator


class HotPathState(TypedDict):
    """The state of the Conversational Agent throughout its execution graph."""

    user_id: str
    session_id: str

    # The history of the conversation (Langchain message objects)
    messages: Annotated[list[AnyMessage], operator.add]

    # Track the current loop iteration to prevent infinite loops
    iteration: int

    # Current timezone and time
    current_time_iso: str
    timezone: str

    # System Context (assembled by context.py)
    context_string: str

    # Trace ID for telemetry
    trace_id: str

    # User profile dict
    profile: dict[str, Any]
