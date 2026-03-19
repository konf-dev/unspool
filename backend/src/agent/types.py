from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str = ""


@dataclass
class ToolResult:
    tool_call_id: str
    name: str
    output: str
    is_error: bool = False


@dataclass
class StreamEvent:
    type: str  # text_delta | tool_call_start | tool_call_delta | tool_call_done | done
    content: str = ""
    tool_call_id: str = ""
    tool_name: str = ""
    arguments_delta: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class AgentState:
    user_id: str
    trace_id: str
    user_message: str
    should_ingest: bool = False
    saved_items: bool = False
    tool_calls_made: list[dict[str, Any]] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    response_text: str = ""
