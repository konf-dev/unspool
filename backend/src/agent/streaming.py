import json
from typing import Any


def format_sse_event(event_type: str, **kwargs: Any) -> str:
    """Format an SSE event for the wire.

    Event types:
      token: {"type": "token", "content": "..."}
      tool_status: {"type": "tool_status", "tool": "...", "status": "running"|"done"}
      done: {"type": "done"}
      error: {"type": "error", "content": "..."}
    """
    payload: dict[str, Any] = {"type": event_type}
    for key, value in kwargs.items():
        if value is not None and value != "":
            payload[key] = value
    return f"data: {json.dumps(payload)}\n\n"
