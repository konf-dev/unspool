"""Subgraph → LLM-readable text serialization."""

import re
from datetime import datetime, timezone

import tiktoken

from src.graph.types import ActiveSubgraph, Node
from src.orchestrator.config_loader import load_config
from src.telemetry.logger import get_logger

_log = get_logger("graph.serialization")

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_STATUS_NODES = {"not done", "done", "surfaced"}

try:
    _enc = tiktoken.encoding_for_model("gpt-4")
except Exception:
    _enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_enc.encode(text))


def serialize_subgraph(subgraph: ActiveSubgraph) -> str:
    graph_config = load_config("graph")
    max_tokens = graph_config.get("serialization", {}).get("max_context_tokens", 2000)

    outgoing: dict[str, list[str]] = {}
    incoming: dict[str, list[str]] = {}
    node_map: dict[str, Node] = {}

    for node in subgraph.nodes:
        node_map[node.id] = node
        outgoing[node.id] = []
        incoming[node.id] = []

    for edge in subgraph.edges:
        from_id = edge.from_node_id
        to_id = edge.to_node_id
        if from_id in node_map:
            outgoing.setdefault(from_id, []).append(to_id)
        if to_id in node_map:
            incoming.setdefault(to_id, []).append(from_id)

    open_items = _find_open_items(subgraph, node_map, outgoing)
    date_nodes = _find_date_nodes(node_map)
    people = _find_people(node_map, outgoing, incoming)
    suppressed = _find_suppressed(subgraph, node_map)
    recent = _find_recent(node_map)

    now = datetime.now(timezone.utc)
    sections: list[tuple[str, int]] = []

    time_header = (
        f"Current time: {now.strftime('%Y-%m-%d %I:%M %p')} ({now.strftime('%A')})"
    )

    if open_items:
        lines = ["OPEN (things not done yet):"]
        for item in open_items:
            line = _format_open_item(item, node_map, outgoing, date_nodes, now)
            lines.append(f"- {line}")
        sections.append(("\n".join(lines), 90))

    schedule_items = _find_schedule(date_nodes, node_map, incoming, now)
    if schedule_items:
        lines = ["SCHEDULE:"]
        for s in schedule_items:
            lines.append(f"- {s}")
        sections.append(("\n".join(lines), 85))

    if people:
        lines = ["PEOPLE:"]
        for name, details in people.items():
            lines.append(f"- {name} — {details}")
        sections.append(("\n".join(lines), 50))

    if suppressed:
        lines = ["RECENTLY SURFACED (don't repeat these):"]
        for item in suppressed:
            lines.append(f'- "{item}"')
        sections.append(("\n".join(lines), 80))

    if recent:
        lines = ["RECENT CONTEXT:"]
        for r in recent[:5]:
            lines.append(f'- "{r}"')
        sections.append(("\n".join(lines), 20))

    sections.sort(key=lambda x: x[1], reverse=True)

    result_parts = [f"<context>\n{time_header}"]
    remaining = max_tokens - count_tokens(result_parts[0]) - 20

    for text, _priority in sections:
        tokens = count_tokens(text)
        if tokens <= remaining:
            result_parts.append(text)
            remaining -= tokens
        else:
            lines = text.split("\n")
            truncated = [lines[0]]
            for line in lines[1:]:
                t = count_tokens(line)
                if t <= remaining - 10:
                    truncated.append(line)
                    remaining -= t
                else:
                    break
            if len(truncated) > 1:
                result_parts.append("\n".join(truncated))

    result_parts.append("</context>")

    serialized = "\n\n".join(result_parts)

    _log.info(
        "graph.serialization.done",
        sections_included=len(
            [s for s in sections if any(s[0] in p for p in result_parts)]
        ),
        tokens_used=count_tokens(serialized),
        tokens_budget=max_tokens,
    )

    return serialized


def _find_open_items(
    subgraph: ActiveSubgraph, node_map: dict[str, Node], outgoing: dict[str, list[str]]
) -> list[Node]:
    items = []
    not_done_ids = {n.id for n in subgraph.nodes if n.content.lower() == "not done"}
    if not not_done_ids:
        return items

    for edge in subgraph.edges:
        from_id = edge.from_node_id
        to_id = edge.to_node_id
        if to_id in not_done_ids and edge.strength > 0.01 and from_id in node_map:
            node = node_map[from_id]
            if node.content.lower() not in _STATUS_NODES:
                items.append(node)

    return items


def _find_date_nodes(node_map: dict[str, Node]) -> dict[str, datetime]:
    dates = {}
    for nid, node in node_map.items():
        if _ISO_DATE.match(node.content):
            try:
                dates[nid] = datetime.strptime(node.content, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                pass
    return dates


def _find_people(
    node_map: dict[str, Node],
    outgoing: dict[str, list[str]],
    incoming: dict[str, list[str]],
) -> dict[str, str]:
    people = {}
    for nid, node in node_map.items():
        content = node.content
        if content.lower() in _STATUS_NODES or _ISO_DATE.match(content):
            continue
        words = content.split()
        if len(words) <= 2 and words[0][0].isupper():
            connections = len(outgoing.get(nid, [])) + len(incoming.get(nid, []))
            if connections >= 2:
                connected_contents = []
                for cid in (outgoing.get(nid, []) + incoming.get(nid, []))[:3]:
                    if (
                        cid in node_map
                        and node_map[cid].content.lower() not in _STATUS_NODES
                    ):
                        connected_contents.append(node_map[cid].content)
                desc = (
                    ", ".join(connected_contents) if connected_contents else "mentioned"
                )
                people[content] = desc
    return people


def _find_suppressed(subgraph: ActiveSubgraph, node_map: dict[str, Node]) -> list[str]:
    surfaced_ids = {n.id for n in subgraph.nodes if n.content.lower() == "surfaced"}
    items = []
    for edge in subgraph.edges:
        from_id = edge.from_node_id
        to_id = edge.to_node_id
        if to_id in surfaced_ids and from_id in node_map:
            items.append(node_map[from_id].content)
    return items


def _find_recent(node_map: dict[str, Node]) -> list[str]:
    nodes = sorted(
        node_map.values(),
        key=lambda n: n.last_activated_at,
        reverse=True,
    )
    return [
        n.content
        for n in nodes[:10]
        if n.content.lower() not in _STATUS_NODES and not _ISO_DATE.match(n.content)
    ]


def _format_open_item(
    item: Node,
    node_map: dict[str, Node],
    outgoing: dict[str, list[str]],
    date_nodes: dict[str, datetime],
    now: datetime,
) -> str:
    parts = [f'"{item.content}"']

    for connected_id in outgoing.get(item.id, []):
        if connected_id in date_nodes:
            deadline = date_nodes[connected_id]
            delta = deadline - now
            if delta.days < 0:
                parts.append(f"overdue by {abs(delta.days)} days")
            elif delta.days == 0:
                parts.append("due today")
            elif delta.days == 1:
                parts.append("due tomorrow")
            else:
                parts.append(
                    f"due in {delta.days} days ({deadline.strftime('%Y-%m-%d')})"
                )

    for connected_id in outgoing.get(item.id, []):
        if connected_id in node_map:
            content = node_map[connected_id].content.lower()
            if content in ("hard deadline", "late fee", "urgent"):
                parts.append(content)

    age = now - item.created_at
    if age.days > 0:
        parts.append(f"mentioned {age.days}d ago")
    elif age.seconds > 3600:
        parts.append(f"mentioned {age.seconds // 3600}h ago")

    return " — ".join(parts)


def _find_schedule(
    date_nodes: dict[str, datetime],
    node_map: dict[str, Node],
    incoming: dict[str, list[str]],
    now: datetime,
) -> list[str]:
    items = []
    for nid, dt in sorted(date_nodes.items(), key=lambda x: x[1]):
        delta = dt - now
        if -1 <= delta.days <= 1:
            connected = [
                node_map[cid].content
                for cid in incoming.get(nid, [])
                if cid in node_map
                and node_map[cid].content.lower() not in _STATUS_NODES
            ]
            if connected:
                when = "today" if delta.days <= 0 else "tomorrow"
                items.append(
                    f"{', '.join(connected)} — {when} ({dt.strftime('%Y-%m-%d')})"
                )
    return items
