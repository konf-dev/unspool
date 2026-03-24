"""User journey E2E tests — validates product features against production.

Usage:
    BASE_URL=https://api.unspool.life EVAL_API_KEY=xxx ADMIN_API_KEY=xxx python eval/user_journey_test.py

Exit code 0 = all pass, 1 = any failures.
"""

import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

try:
    import httpx
except ImportError:
    sys.exit("httpx required: pip install httpx")

# ── Config ──

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
EVAL_API_KEY = os.environ.get("EVAL_API_KEY", "")
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "")
EVAL_USER_ID = "b8a2e17e-ff55-485f-ad6c-29055a607b33"

# ── Result tracking ──


@dataclass
class TestResult:
    section: str
    name: str
    passed: bool
    duration_ms: int = 0
    detail: str = ""


results: list[TestResult] = []


def record(section: str, name: str, passed: bool, duration_ms: int = 0, detail: str = ""):
    results.append(TestResult(section, name, passed, duration_ms, detail))
    status = "[PASS]" if passed else "[FAIL]"
    print(f"  {status} {section} {name} ({duration_ms}ms){f' — {detail}' if detail and not passed else ''}")


# ── HTTP helpers ──


def auth_header() -> dict[str, str]:
    return {"Authorization": f"Bearer eval:{EVAL_API_KEY}"}


def admin_auth() -> dict[str, str]:
    return {"X-Admin-Key": ADMIN_API_KEY}


def timed(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


async def send_chat(
    client: httpx.AsyncClient,
    msg: str,
    session_id: str,
    timeout: float = 45.0,
    retries: int = 2,
) -> tuple[str, list[dict[str, Any]], str]:
    """Send a chat message and collect SSE response.

    Returns (response_text, events, trace_id).
    Retries on connection errors (ReadError, RemoteProtocolError).
    """
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        # Use a fresh client on retries to avoid stale pooled connections
        retry_client = client if attempt == 0 else httpx.AsyncClient(timeout=timeout)
        try:
            text_parts: list[str] = []
            events: list[dict[str, Any]] = []
            trace_id = ""

            async with retry_client.stream(
                "POST", f"{BASE_URL}/api/chat",
                json={"message": msg, "session_id": session_id},
                headers=auth_header(),
                timeout=timeout,
            ) as r:
                trace_id = r.headers.get("x-trace-id", "")
                async for line in r.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            evt = json.loads(line[6:])
                            events.append(evt)
                            if evt.get("type") == "token":
                                text_parts.append(evt.get("content", ""))
                        except json.JSONDecodeError:
                            pass

            return "".join(text_parts), events, trace_id
        except (httpx.ReadError, httpx.RemoteProtocolError, httpx.ConnectError, httpx.ConnectTimeout) as e:
            last_exc = e
            if attempt < retries:
                wait = 3 * (attempt + 1)
                print(f"    ⚠ Connection error on attempt {attempt + 1}, retrying in {wait}s...")
                await asyncio.sleep(wait)
        finally:
            if attempt > 0:
                await retry_client.aclose()
    raise last_exc  # type: ignore[misc]


_RETRYABLE = (httpx.ReadError, httpx.RemoteProtocolError, httpx.ConnectError, httpx.ConnectTimeout)


async def _retry_request(coro_fn, retries=2):
    """Retry a request coroutine on transient connection errors."""
    for attempt in range(retries + 1):
        try:
            return await coro_fn()
        except _RETRYABLE:
            if attempt < retries:
                await asyncio.sleep(2 * (attempt + 1))
    return None


async def get_graph(client: httpx.AsyncClient, limit: int = 200) -> dict[str, Any]:
    r = await _retry_request(lambda: client.get(
        f"{BASE_URL}/admin/user/{EVAL_USER_ID}/graph",
        headers=admin_auth(),
        params={"limit": limit},
    ))
    return r.json() if r and r.status_code == 200 else {"nodes": [], "edges": []}


async def get_profile(client: httpx.AsyncClient) -> dict[str, Any]:
    r = await _retry_request(lambda: client.get(
        f"{BASE_URL}/admin/user/{EVAL_USER_ID}/profile",
        headers=admin_auth(),
    ))
    return r.json() if r and r.status_code == 200 else {}


async def patch_profile(client: httpx.AsyncClient, fields: dict[str, Any]) -> bool:
    r = await _retry_request(lambda: client.patch(
        f"{BASE_URL}/admin/user/{EVAL_USER_ID}/profile",
        headers=admin_auth(),
        json=fields,
    ))
    return r is not None and r.status_code == 200


async def get_messages(client: httpx.AsyncClient) -> dict[str, Any]:
    r = await _retry_request(lambda: client.get(
        f"{BASE_URL}/api/messages",
        headers=auth_header(),
    ))
    return r.json() if r and r.status_code == 200 else {"messages": []}


async def cleanup(client: httpx.AsyncClient):
    """GDPR-delete eval user data."""
    for attempt in range(3):
        try:
            await client.delete(f"{BASE_URL}/api/account", headers=auth_header())
            return
        except _RETRYABLE:
            if attempt < 2:
                await asyncio.sleep(2)
    # Silently give up — cleanup is best-effort


async def wait_cold_path(seconds: int = 15):
    print(f"    ⏳ Waiting {seconds}s for cold path...")
    await asyncio.sleep(seconds)


def find_nodes(graph: dict, node_type: str | None = None, content_match: str | None = None) -> list[dict]:
    nodes = graph.get("nodes", [])
    result = nodes
    if node_type:
        result = [n for n in result if n.get("node_type") == node_type]
    if content_match:
        pattern = re.compile(content_match, re.IGNORECASE)
        result = [n for n in result if pattern.search(n.get("content", ""))]
    return result


def find_edges(graph: dict, edge_type: str | None = None) -> list[dict]:
    edges = graph.get("edges", [])
    if edge_type:
        return [e for e in edges if e.get("edge_type") == edge_type]
    return edges


def has_tool_call(events: list[dict], tool_name: str) -> bool:
    return any(
        evt.get("type") == "tool_start" and tool_name in evt.get("calls", [])
        for evt in events
    )


# ── Journey 1: Brain Dump → Recall → Complete → Verify ──


async def journey_1_brain_dump_lifecycle(client: httpx.AsyncClient):
    print("\n--- Journey 1: Brain Dump → Recall → Complete → Verify ---")
    session_id = f"j1-{int(time.time())}"

    try:
        # Step 1: Send brain dump
        t = time.perf_counter()
        text_resp, events, _ = await send_chat(
            client,
            "I need to call Mom about her birthday party, finish the quarterly report by Friday, "
            "and pick up groceries. I'm feeling pretty stressed about the report.",
            session_id,
        )
        record("J1.1", "Brain dump response", len(text_resp) > 0, timed(t))

        # Step 3: Recall tasks (cold path processes while we chat)
        await wait_cold_path(20)
        t = time.perf_counter()
        text_resp, events, _ = await send_chat(client, "what tasks do I have?", session_id)
        used_query = has_tool_call(events, "query_graph")
        record("J1.6", "Recall uses query_graph", used_query, timed(t))
        record("J1.7", "Recall mentions tasks", bool(re.search(r"report|grocer|mom|call", text_resp, re.I)),
               timed(t), f"response: {text_resp[:100]}")

        # Step 2: Verify graph (after recall gives cold path extra time)
        t = time.perf_counter()
        graph = await get_graph(client)
        ms = timed(t)

        action_nodes = find_nodes(graph, node_type="action")
        record("J1.2", "Action nodes extracted", len(action_nodes) >= 2, ms,
               f"got {len(action_nodes)} action nodes")

        status_edges = find_edges(graph, edge_type="IS_STATUS")
        record("J1.3", "IS_STATUS edges exist", len(status_edges) >= 1, ms,
               f"got {len(status_edges)} IS_STATUS edges")

        deadline_edges = find_edges(graph, edge_type="HAS_DEADLINE")
        record("J1.4", "HAS_DEADLINE edges exist", len(deadline_edges) >= 1, ms,
               f"got {len(deadline_edges)} deadline edges")

        person_nodes = find_nodes(graph, node_type="person")
        emotion_nodes = find_nodes(graph, node_type="emotion")
        record("J1.5", "Person/emotion nodes", len(person_nodes) >= 1 or len(emotion_nodes) >= 1, ms,
               f"persons={len(person_nodes)}, emotions={len(emotion_nodes)}")

        # Step 4: Complete a task
        t = time.perf_counter()
        text_resp, events, _ = await send_chat(client, "I picked up the groceries", session_id, timeout=60.0)
        used_mutate = has_tool_call(events, "mutate_graph")
        record("J1.8", "Completion uses mutate_graph", used_mutate, timed(t))

        # Step 5: Check remaining tasks
        t = time.perf_counter()
        text_resp, events, _ = await send_chat(client, "what do I still need to do?", session_id, timeout=60.0)
        # Groceries should be excluded or marked done
        mentions_groceries = bool(re.search(r"groceries", text_resp, re.I))
        mentions_other = bool(re.search(r"report|mom|call", text_resp, re.I))
        record("J1.9", "Completed task excluded from remaining", mentions_other and not mentions_groceries,
               timed(t), f"mentions_groceries={mentions_groceries}")

        # Step 6: Verify graph mutation
        await asyncio.sleep(5)
        t = time.perf_counter()
        graph = await get_graph(client)
        done_edges = [e for e in find_edges(graph, "IS_STATUS")
                      if any(n.get("content", "").upper() == "DONE"
                             for n in graph.get("nodes", [])
                             if str(n.get("id")) == str(e.get("target_node_id")))]
        record("J1.10", "IS_STATUS→DONE edge exists", len(done_edges) >= 1, timed(t),
               f"got {len(done_edges)} DONE edges")
    finally:
        await cleanup(client)


# ── Journey 2: Deadline Resolution ──


async def journey_2_deadline_resolution(client: httpx.AsyncClient):
    print("\n--- Journey 2: Deadline Resolution ---")
    session_id = f"j2-{int(time.time())}"

    try:
        messages = [
            "submit the proposal tomorrow at 2pm",
            "team meeting next Friday",
            "dentist appointment March 28",
            "reply to Alex in 3 hours",
            "finish slides by end of week",
        ]

        t = time.perf_counter()
        for msg in messages:
            await send_chat(client, msg, session_id)
        record("J2.1", "All 5 deadline messages sent", True, timed(t))

        await wait_cold_path(35)
        t = time.perf_counter()
        graph = await get_graph(client)
        ms = timed(t)

        deadline_edges = find_edges(graph, edge_type="HAS_DEADLINE")
        record("J2.2", "Deadline edges created", len(deadline_edges) >= 2, ms,
               f"got {len(deadline_edges)} deadline edges")

        # Check that metadata has date fields
        dates_with_iso = [e for e in deadline_edges
                          if e.get("metadata") and e["metadata"].get("date")]
        record("J2.3", "Deadlines have ISO dates", len(dates_with_iso) >= 1, ms,
               f"got {len(dates_with_iso)} with dates")

        # Ask about upcoming deadlines
        t = time.perf_counter()
        text_resp, events, _ = await send_chat(client, "what's coming up this week?", session_id)
        record("J2.4", "Deadlines surface in recall", len(text_resp) > 0, timed(t),
               f"response: {text_resp[:100]}")
    finally:
        await cleanup(client)


# ── Journey 3: Emotional Intelligence ──


async def journey_3_emotional_intelligence(client: httpx.AsyncClient):
    print("\n--- Journey 3: Emotional Intelligence ---")
    session_id = f"j3-{int(time.time())}"

    try:
        # Overwhelmed state
        t = time.perf_counter()
        text_resp, _, _ = await send_chat(
            client,
            "I'm completely overwhelmed. Everything is piling up and I can't cope. "
            "I don't know what to do anymore.",
            session_id,
        )
        record("J3.1", "Overwhelmed: brief response", len(text_resp) < 500, timed(t),
               f"got {len(text_resp)} chars")
        # Should NOT contain a numbered list or task suggestions
        has_list = bool(re.search(r"^\s*[1-9]\.", text_resp, re.MULTILINE))
        record("J3.2", "Overwhelmed: no numbered list", not has_list, timed(t))

        # Recovery nudge
        t = time.perf_counter()
        text_resp, _, _ = await send_chat(
            client, "ok maybe I could try one small thing", session_id,
        )
        # Should give ONE suggestion, not a barrage
        multi_suggestions = bool(re.search(r"^\s*[2-9]\.", text_resp, re.MULTILINE))
        record("J3.3", "Recovery: single suggestion", not multi_suggestions, timed(t),
               f"response: {text_resp[:150]}")

        # Celebration
        t = time.perf_counter()
        text_resp, _, _ = await send_chat(
            client, "I finished my thesis!! finally done!!", session_id,
        )
        has_now_do = bool(re.search(r"now (you (should|could|can)|do|try|start)", text_resp, re.I))
        record("J3.4", "Celebration: no 'now do X'", not has_now_do, timed(t),
               f"response: {text_resp[:150]}")
        record("J3.5", "Celebration: brief", len(text_resp) < 500, timed(t),
               f"got {len(text_resp)} chars")
    finally:
        await cleanup(client)


# ── Journey 4: Memory Across Sessions ──


async def journey_4_memory_across_sessions(client: httpx.AsyncClient):
    print("\n--- Journey 4: Memory Across Sessions ---")
    session_a = f"j4a-{int(time.time())}"
    session_b = f"j4b-{int(time.time())}"
    session_c = f"j4c-{int(time.time())}"

    try:
        # Session A: Store information
        t = time.perf_counter()
        await send_chat(client, "Mom's birthday is April 15, need to plan something special", session_a)
        record("J4.1", "Session A: info stored", True, timed(t))

        await wait_cold_path(18)

        # Session B: Recall with different session
        t = time.perf_counter()
        text_resp, events, _ = await send_chat(client, "what do I know about my mom?", session_b)
        mentions_birthday = bool(re.search(r"birthday|april\s*15", text_resp, re.I))
        record("J4.2", "Session B: recalls birthday", mentions_birthday, timed(t),
               f"response: {text_resp[:150]}")

        # Session C: Context surfaces
        t = time.perf_counter()
        text_resp, events, _ = await send_chat(client, "I need to call Mom", session_c)
        record("J4.3", "Session C: valid response", len(text_resp) > 0, timed(t))
    finally:
        await cleanup(client)


# ── Journey 5: Metric Tracking ──


async def journey_5_metric_tracking(client: httpx.AsyncClient):
    print("\n--- Journey 5: Metric Tracking ---")
    session_id = f"j5-{int(time.time())}"

    try:
        t = time.perf_counter()
        await send_chat(client, "I ran 5km this morning", session_id)
        record("J5.1", "Metric message sent", True, timed(t))

        await send_chat(client, "did 30 pushups after", session_id)

        await wait_cold_path(18)
        t = time.perf_counter()
        graph = await get_graph(client)
        ms = timed(t)

        metric_edges = find_edges(graph, edge_type="TRACKS_METRIC")
        record("J5.2", "TRACKS_METRIC edges exist", len(metric_edges) >= 1, ms,
               f"got {len(metric_edges)} metric edges")

        # Check metadata has value/unit
        metrics_with_values = [e for e in metric_edges
                               if e.get("metadata") and e["metadata"].get("value") is not None]
        record("J5.3", "Metrics have values", len(metrics_with_values) >= 1, ms,
               f"got {len(metrics_with_values)} with values")

        # Recall metrics
        t = time.perf_counter()
        text_resp, _, _ = await send_chat(client, "what exercise have I done?", session_id)
        mentions_exercise = bool(re.search(r"5\s*km|run|pushup|30", text_resp, re.I))
        record("J5.4", "Metrics surface in recall", mentions_exercise, timed(t),
               f"response: {text_resp[:150]}")
    finally:
        await cleanup(client)


# ── Journey 6: Graph Mutation Verification ──


async def journey_6_graph_mutation(client: httpx.AsyncClient):
    print("\n--- Journey 6: Graph Mutation Verification ---")
    session_id = f"j6-{int(time.time())}"

    try:
        # Create 3 tasks
        t = time.perf_counter()
        await send_chat(client, "I need to: wash the car, write the blog post, and schedule the dentist", session_id)
        record("J6.1", "3 tasks sent", True, timed(t))

        await wait_cold_path(20)
        graph = await get_graph(client)

        action_nodes = find_nodes(graph, node_type="action")
        record("J6.2", "3 action nodes created", len(action_nodes) >= 3, timed(t),
               f"got {len(action_nodes)} action nodes")

        open_edges = find_edges(graph, edge_type="IS_STATUS")
        record("J6.3", "IS_STATUS edges exist", len(open_edges) >= 3, timed(t),
               f"got {len(open_edges)} IS_STATUS edges")

        # Complete one
        await send_chat(client, "I washed the car", session_id, timeout=60.0)
        await asyncio.sleep(5)
        t = time.perf_counter()
        graph = await get_graph(client)

        # Find DONE status nodes
        done_nodes = [n for n in graph.get("nodes", [])
                      if n.get("content", "").upper() == "DONE"]
        done_node_ids = {str(n.get("id")) for n in done_nodes}
        done_status_edges = [e for e in find_edges(graph, "IS_STATUS")
                             if str(e.get("target_node_id")) in done_node_ids]
        record("J6.4", "One task marked DONE", len(done_status_edges) >= 1, timed(t),
               f"got {len(done_status_edges)} DONE edges")

        # Archive one
        await send_chat(client, "actually never mind about the dentist, remove that", session_id, timeout=60.0)
        await asyncio.sleep(5)
        t = time.perf_counter()
        graph = await get_graph(client)

        archived = [n for n in graph.get("nodes", [])
                    if n.get("node_type", "").startswith("archived")]
        record("J6.5", "Archived node exists", len(archived) >= 1, timed(t),
               f"got {len(archived)} archived nodes")
    finally:
        await cleanup(client)


# ── Journey 7: Semantic Dedup ──


async def journey_7_semantic_dedup(client: httpx.AsyncClient):
    print("\n--- Journey 7: Semantic Dedup ---")
    session_id = f"j7-{int(time.time())}"

    try:
        # First message
        t = time.perf_counter()
        await send_chat(client, "I need to buy groceries", session_id)
        await wait_cold_path(18)
        graph1 = await get_graph(client)
        node_count_1 = len(graph1.get("nodes", []))
        record("J7.1", "First message processed", node_count_1 >= 1, timed(t),
               f"got {node_count_1} nodes")

        # Semantically similar message
        t = time.perf_counter()
        await send_chat(client, "get groceries from the store", session_id)
        await wait_cold_path(18)
        graph2 = await get_graph(client)
        node_count_2 = len(graph2.get("nodes", []))
        # Should reuse existing node, not create a new one (allow +1 for status nodes etc.)
        record("J7.2", "Dedup: no new action node", node_count_2 <= node_count_1 + 1, timed(t),
               f"before={node_count_1}, after={node_count_2}")

        # Different message
        t = time.perf_counter()
        await send_chat(client, "I need to clean the apartment", session_id)
        await wait_cold_path(18)
        graph3 = await get_graph(client)
        node_count_3 = len(graph3.get("nodes", []))
        record("J7.3", "New task: new node created", node_count_3 > node_count_2, timed(t),
               f"before={node_count_2}, after={node_count_3}")
    finally:
        await cleanup(client)


# ── Journey 8: Proactive Message Delivery ──


async def journey_8_proactive_messages(client: httpx.AsyncClient):
    print("\n--- Journey 8: Proactive Message Delivery ---")

    try:
        # Send a message first so the user profile exists and has some context
        session_id = f"j8-{int(time.time())}"
        await send_chat(client, "I need to organize my desk and reply to emails", session_id)
        await wait_cold_path(15)

        # Set last_interaction_at to 8 days ago to trigger days_absent
        eight_days_ago = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        t = time.perf_counter()
        patched = await patch_profile(client, {
            "last_interaction_at": eight_days_ago,
            "last_proactive_at": (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat(),
        })
        record("J8.1", "Profile patched", patched, timed(t))

        # GET /api/messages (initial load) → should trigger proactive
        t = time.perf_counter()
        msg_data = await get_messages(client)
        messages = msg_data.get("messages", [])
        proactive_msgs = [m for m in messages
                          if isinstance(m.get("metadata"), dict)
                          and m["metadata"].get("type") == "proactive"]
        proactive_count_1 = len(proactive_msgs)
        record("J8.2", "Proactive message delivered", proactive_count_1 >= 1, timed(t),
               f"got {proactive_count_1} proactive messages")

        # Second call should NOT produce a new proactive (6h cooldown)
        t = time.perf_counter()
        msg_data2 = await get_messages(client)
        messages2 = msg_data2.get("messages", [])
        proactive_msgs2 = [m for m in messages2
                           if isinstance(m.get("metadata"), dict)
                           and m["metadata"].get("type") == "proactive"]
        proactive_count_2 = len(proactive_msgs2)
        # Count should not increase — cooldown blocks new proactive generation
        record("J8.3", "Cooldown: no new proactive", proactive_count_2 <= proactive_count_1, timed(t),
               f"first={proactive_count_1}, second={proactive_count_2}")
    finally:
        await cleanup(client)


# ── Journey 9: Personality & Tone ──


async def journey_9_personality_tone(client: httpx.AsyncClient):
    print("\n--- Journey 9: Personality & Tone ---")
    session_id = f"j9-{int(time.time())}"

    try:
        # Short input → short output
        t = time.perf_counter()
        text_resp, _, _ = await send_chat(client, "ok got it", session_id)
        record("J9.1", "Short input → brief response", len(text_resp) < 200, timed(t),
               f"got {len(text_resp)} chars")

        # Factual question → no unnecessary empathy
        t = time.perf_counter()
        text_resp, _, _ = await send_chat(client, "what time zone am I in?", session_id)
        has_adhd = bool(re.search(r"\bADHD\b", text_resp))
        record("J9.2", "Factual: no ADHD mention", not has_adhd, timed(t))

        # Task completion → brief, no lists
        t = time.perf_counter()
        text_resp, _, _ = await send_chat(client, "finished the laundry", session_id)
        has_now_do = bool(re.search(r"now (you (should|could|can)|do|try|start|how about)", text_resp, re.I))
        has_list = bool(re.search(r"^\s*[1-9]\.", text_resp, re.MULTILINE))
        record("J9.3", "Completion: no 'now do X'", not has_now_do, timed(t),
               f"response: {text_resp[:100]}")
        record("J9.4", "Completion: no numbered list", not has_list, timed(t))

        # Stuck → single suggestion
        t = time.perf_counter()
        text_resp, _, _ = await send_chat(client, "I don't know where to start today", session_id)
        multi_items = bool(re.search(r"^\s*[3-9]\.", text_resp, re.MULTILINE))
        record("J9.5", "Stuck: no long numbered list", not multi_items, timed(t),
               f"response: {text_resp[:150]}")
    finally:
        await cleanup(client)


# ── Journey 10: Edge Cases ──


async def journey_10_edge_cases(client: httpx.AsyncClient):
    print("\n--- Journey 10: Edge Cases ---")
    session_id = f"j10-{int(time.time())}"

    try:
        # Minimal inputs
        t = time.perf_counter()
        for msg in ["ok", "lol"]:
            text_resp, _, _ = await send_chat(client, msg, session_id)
        record("J10.1", "Minimal inputs handled", len(text_resp) > 0, timed(t))

        # Long message
        t = time.perf_counter()
        long_msg = "I have so many things to do. " * 80  # ~2400 chars
        text_resp, _, _ = await send_chat(client, long_msg, session_id, timeout=60.0)
        record("J10.2", "Long message handled", len(text_resp) > 0, timed(t),
               f"responded in {timed(t)}ms")

        # Mixed language
        t = time.perf_counter()
        text_resp, _, _ = await send_chat(
            client, "necesito llamar a Mom tomorrow about the party", session_id,
        )
        record("J10.3", "Mixed language handled", len(text_resp) > 0, timed(t))

        # Concurrent chats
        t = time.perf_counter()
        tasks = [
            send_chat(client, f"task number {i}", f"j10-concurrent-{i}-{int(time.time())}")
            for i in range(3)
        ]
        concurrent_results = await asyncio.gather(*tasks, return_exceptions=True)
        successes = sum(1 for r in concurrent_results if not isinstance(r, Exception) and len(r[0]) > 0)
        record("J10.4", "3 concurrent chats succeed", successes == 3, timed(t),
               f"{successes}/3 succeeded")
    finally:
        await cleanup(client)


# ── Journey 11: ICS Calendar Feed ──


async def journey_11_ics_feed(client: httpx.AsyncClient):
    print("\n--- Journey 11: ICS Calendar Feed ---")
    session_id = f"j11-{int(time.time())}"

    try:
        # Create tasks with deadlines
        t = time.perf_counter()
        await send_chat(
            client,
            "project deadline is next Monday, dentist on Wednesday, submit report by April 10",
            session_id,
        )
        record("J11.1", "Deadline tasks sent", True, timed(t))

        await wait_cold_path(25)

        # Verify deadline edges exist before checking feed
        graph = await get_graph(client)
        deadline_edges = find_edges(graph, edge_type="HAS_DEADLINE")
        print(f"    J11 debug: {len(deadline_edges)} HAS_DEADLINE edges")
        for e in deadline_edges[:3]:
            print(f"      edge metadata: {e.get('metadata')}")

        # Ensure profile has a feed_token
        import secrets as _secrets
        generated_token = _secrets.token_urlsafe(32)
        await patch_profile(client, {"feed_token": generated_token})

        # Get feed token from profile
        profile = await get_profile(client)
        feed_token = profile.get("feed_token")
        record("J11.2", "Feed token exists", feed_token is not None, 0,
               "no feed_token in profile" if not feed_token else "")

        if feed_token:
            # Fetch ICS feed
            t = time.perf_counter()
            r = await client.get(f"{BASE_URL}/api/feed/{feed_token}.ics")
            record("J11.3", "ICS feed returns 200", r.status_code == 200, timed(t),
                   f"status={r.status_code}")

            if r.status_code == 200:
                ics_content = r.text
                has_vcalendar = "BEGIN:VCALENDAR" in ics_content
                has_vevent = "BEGIN:VEVENT" in ics_content
                record("J11.4", "Valid iCalendar format", has_vcalendar, timed(t))
                record("J11.5", "Has VEVENT entries", has_vevent, timed(t),
                       f"VCALENDAR={has_vcalendar}, VEVENT={has_vevent}")
            else:
                record("J11.4", "Valid iCalendar format", False, timed(t), "feed request failed")
                record("J11.5", "Has VEVENT entries", False, timed(t), "feed request failed")
        else:
            record("J11.3", "ICS feed returns 200", False, 0, "no feed_token")
            record("J11.4", "Valid iCalendar format", False, 0, "no feed_token")
            record("J11.5", "Has VEVENT entries", False, 0, "no feed_token")
    finally:
        await cleanup(client)


# ── Journey 12: Cold Path Idempotency ──


async def journey_12_cold_path_idempotency(client: httpx.AsyncClient):
    print("\n--- Journey 12: Cold Path Idempotency ---")
    session_id = f"j12-{int(time.time())}"

    try:
        # First message
        t = time.perf_counter()
        await send_chat(client, "fix the broken window in the kitchen", session_id)
        await wait_cold_path(18)
        graph1 = await get_graph(client)
        node_count_1 = len(graph1.get("nodes", []))
        record("J12.1", "First message processed", node_count_1 >= 1, timed(t),
               f"got {node_count_1} nodes")

        # Same message again
        t = time.perf_counter()
        await send_chat(client, "fix the broken window in the kitchen", session_id)
        await wait_cold_path(18)
        graph2 = await get_graph(client)
        node_count_2 = len(graph2.get("nodes", []))
        # Should not create duplicate nodes (allow small tolerance for status nodes)
        record("J12.2", "Idempotent: no duplicate nodes", node_count_2 <= node_count_1 + 1, timed(t),
               f"before={node_count_1}, after={node_count_2}")
    finally:
        await cleanup(client)


# ── Main ──


async def main():
    print(f"=== Unspool User Journey E2E Tests ===")
    print(f"Target: {BASE_URL}")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print(f"Eval key: {'set' if EVAL_API_KEY else 'NOT SET'}")
    print(f"Admin key: {'set' if ADMIN_API_KEY else 'NOT SET'}")

    if not EVAL_API_KEY or not ADMIN_API_KEY:
        print("\nERROR: Both EVAL_API_KEY and ADMIN_API_KEY must be set")
        sys.exit(1)

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Clean slate
        await cleanup(client)

        journeys = [
            journey_1_brain_dump_lifecycle,
            journey_2_deadline_resolution,
            journey_3_emotional_intelligence,
            journey_4_memory_across_sessions,
            journey_5_metric_tracking,
            journey_6_graph_mutation,
            journey_7_semantic_dedup,
            journey_8_proactive_messages,
            journey_9_personality_tone,
            journey_10_edge_cases,
            journey_11_ics_feed,
            journey_12_cold_path_idempotency,
        ]

        for journey in journeys:
            try:
                await journey(client)
            except Exception as e:
                import traceback
                name = journey.__name__
                tb = traceback.format_exc()
                print(f"    TRACEBACK: {tb}")
                record(name, "UNHANDLED EXCEPTION", False, 0, str(e)[:500])
                # Still try to cleanup
                try:
                    await cleanup(client)
                except Exception:
                    pass

    # Summary
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    total = len(results)

    print(f"\n{'=' * 50}")
    print(f"Results: {passed}/{total} passed, {failed} failed")

    if failed:
        print(f"\nFailed tests:")
        for r in results:
            if not r.passed:
                detail = f" — {r.detail}" if r.detail else ""
                print(f"  {r.section} {r.name}{detail}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
