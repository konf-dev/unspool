"""Automated API smoke test — tests every endpoint after deploy.

Usage:
    BASE_URL=https://api.unspool.life EVAL_API_KEY=xxx ADMIN_API_KEY=xxx python eval/smoke_test.py

Exit code 0 = all pass, 1 = any failures.
"""

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
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


async def get(client: httpx.AsyncClient, path: str, **kwargs: Any) -> httpx.Response:
    return await client.get(f"{BASE_URL}{path}", **kwargs)


async def post(client: httpx.AsyncClient, path: str, **kwargs: Any) -> httpx.Response:
    return await client.post(f"{BASE_URL}{path}", **kwargs)


async def delete(client: httpx.AsyncClient, path: str, **kwargs: Any) -> httpx.Response:
    return await client.delete(f"{BASE_URL}{path}", **kwargs)


def auth_header(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def eval_auth() -> dict[str, str]:
    return auth_header(f"eval:{EVAL_API_KEY}")


def admin_auth() -> dict[str, str]:
    return {"X-Admin-Key": ADMIN_API_KEY}


def timed(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


# ── Section 1: Infrastructure ──


async def test_infrastructure(client: httpx.AsyncClient):
    print("\n--- Section 1: Infrastructure ---")

    t = time.perf_counter()
    r = await get(client, "/health")
    record("1.1", "Health endpoint", r.status_code == 200, timed(t))

    t = time.perf_counter()
    r = await get(client, "/admin/health/deep", headers=admin_auth())
    ok = r.status_code == 200
    detail = ""
    if ok:
        data = r.json()
        svc = data.get("services", {})
        statuses = [svc.get(s, {}).get("status") == "ok" for s in ["db", "redis", "qstash", "langfuse"]]
        ok = all(statuses)
        if not ok:
            detail = f"services: {svc}"
    record("1.2", "Deep health - all services ok", ok, timed(t), detail)


# ── Section 2: Authentication ──


async def test_authentication(client: httpx.AsyncClient):
    print("\n--- Section 2: Authentication ---")

    t = time.perf_counter()
    r = await post(client, "/api/chat", json={"message": "hi", "session_id": "test"})
    record("2.1", "No auth token → 401", r.status_code == 401, timed(t))

    t = time.perf_counter()
    r = await post(client, "/api/chat", json={"message": "hi", "session_id": "test"},
                   headers=auth_header("bad-jwt-token"))
    record("2.2", "Bad JWT → 401", r.status_code == 401, timed(t))

    t = time.perf_counter()
    r = await post(client, "/api/chat", json={"message": "hi", "session_id": "test"},
                   headers=auth_header("eval:wrong-key"))
    record("2.3", "Bad eval key → 401", r.status_code == 401, timed(t))

    if EVAL_API_KEY:
        t = time.perf_counter()
        r = await post(client, "/api/chat", json={"message": "hi", "session_id": "test"},
                       headers=eval_auth())
        record("2.4", "Valid eval key → 200/SSE", r.status_code == 200, timed(t))
    else:
        record("2.4", "Valid eval key → 200/SSE", False, 0, "EVAL_API_KEY not set")

    t = time.perf_counter()
    r = await get(client, "/admin/jobs/recent")
    record("2.5", "Admin no key → 403", r.status_code in (401, 403), timed(t))

    if ADMIN_API_KEY:
        t = time.perf_counter()
        r = await get(client, "/admin/jobs/recent", headers=admin_auth())
        record("2.6", "Admin valid key → 200", r.status_code == 200, timed(t))
    else:
        record("2.6", "Admin valid key → 200", False, 0, "ADMIN_API_KEY not set")

    t = time.perf_counter()
    r = await post(client, "/jobs/process-message", json={"user_id": "x", "message": "hi"})
    record("2.7", "Jobs no QStash sig → 403", r.status_code in (401, 403), timed(t))


# ── Section 3: Input Validation ──


async def test_input_validation(client: httpx.AsyncClient):
    print("\n--- Section 3: Input Validation ---")

    t = time.perf_counter()
    r = await post(client, "/api/chat", json={"message": "", "session_id": "test"},
                   headers=eval_auth())
    record("3.1", "Empty message → 422", r.status_code == 422, timed(t))

    t = time.perf_counter()
    r = await post(client, "/api/chat", json={"message": "hi"},
                   headers=eval_auth())
    record("3.2", "Missing session_id → 422", r.status_code == 422, timed(t))

    t = time.perf_counter()
    r = await post(client, "/api/chat", json={"message": "x" * 10001, "session_id": "test"},
                   headers=eval_auth())
    record("3.3", "Oversized message → 422", r.status_code == 422, timed(t))


# ── Section 4: Chat Pipeline ──


async def test_chat_pipeline(client: httpx.AsyncClient) -> tuple[str, str]:
    """Returns (trace_id, session_id) for downstream tests."""
    print("\n--- Section 4: Chat Pipeline ---")

    session_id = f"smoke-{int(time.time())}"
    trace_id = ""
    response_text = ""

    t = time.perf_counter()
    try:
        async with client.stream(
            "POST", f"{BASE_URL}/api/chat",
            json={"message": "I need to buy groceries and finish the report by Friday", "session_id": session_id},
            headers=eval_auth(),
            timeout=30.0,
        ) as r:
            trace_id = r.headers.get("x-trace-id", "")
            events = []
            has_done = False
            async for line in r.aiter_lines():
                if line.startswith("data: "):
                    try:
                        evt = json.loads(line[6:])
                        events.append(evt)
                        if evt.get("type") == "token":
                            response_text += evt.get("content", "")
                        if evt.get("type") == "done":
                            has_done = True
                    except json.JSONDecodeError:
                        pass

        ms = timed(t)
        record("4.1", "Chat SSE stream", r.status_code == 200 and len(events) > 0, ms)
        record("4.2", "Has done event", has_done, ms)
        record("4.3", "Response time < 30s", ms < 30000, ms)
        record("4.4", "Non-empty response text", len(response_text.strip()) > 0, ms,
               f"got {len(response_text)} chars")
    except Exception as e:
        ms = timed(t)
        record("4.1", "Chat SSE stream", False, ms, str(e))
        record("4.2", "Has done event", False, ms, "stream failed")
        record("4.3", "Response time < 30s", False, ms)
        record("4.4", "Non-empty response text", False, ms)

    # Check messages persisted
    if ADMIN_API_KEY:
        t = time.perf_counter()
        r = await get(client, f"/admin/user/{EVAL_USER_ID}/messages", headers=admin_auth())
        if r.status_code == 200:
            msgs = r.json() if isinstance(r.json(), list) else r.json().get("messages", [])
            has_user = any(m.get("role") == "user" for m in msgs[-5:])
            has_asst = any(m.get("role") == "assistant" for m in msgs[-5:])
            record("4.5", "Messages persisted", has_user and has_asst, timed(t))
        else:
            record("4.5", "Messages persisted", False, timed(t), f"status={r.status_code}")
    else:
        record("4.5", "Messages persisted", False, 0, "ADMIN_API_KEY not set")

    return trace_id, session_id


# ── Section 5: Cold Path Verification ──


async def test_cold_path(client: httpx.AsyncClient):
    print("\n--- Section 5: Cold Path Verification ---")

    if not ADMIN_API_KEY:
        record("5.1", "Cold path nodes", False, 0, "ADMIN_API_KEY not set")
        record("5.2", "Cold path edges", False, 0, "ADMIN_API_KEY not set")
        return

    # Wait for QStash dispatch + processing
    print("  Waiting 15s for cold path processing...")
    await asyncio.sleep(15)

    t = time.perf_counter()
    r = await get(client, f"/admin/user/{EVAL_USER_ID}/graph", headers=admin_auth())
    if r.status_code == 200:
        data = r.json()
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        record("5.1", "Cold path nodes", len(nodes) >= 1, timed(t),
               f"got {len(nodes)} nodes")
        record("5.2", "Cold path edges", len(edges) >= 1, timed(t),
               f"got {len(edges)} edges")
    else:
        record("5.1", "Cold path nodes", False, timed(t), f"status={r.status_code}")
        record("5.2", "Cold path edges", False, timed(t), f"status={r.status_code}")


# ── Section 6: Graph Context (second chat) ──


async def test_graph_context(client: httpx.AsyncClient, session_id: str):
    print("\n--- Section 6: Graph Context ---")

    response_text = ""
    has_query_graph = False

    t = time.perf_counter()
    try:
        async with client.stream(
            "POST", f"{BASE_URL}/api/chat",
            json={"message": "what do I need to do?", "session_id": session_id},
            headers=eval_auth(),
            timeout=30.0,
        ) as r:
            async for line in r.aiter_lines():
                if line.startswith("data: "):
                    try:
                        evt = json.loads(line[6:])
                        if evt.get("type") == "token":
                            response_text += evt.get("content", "")
                        if evt.get("type") == "tool_start" and "query_graph" in evt.get("calls", []):
                            has_query_graph = True
                    except json.JSONDecodeError:
                        pass

        ms = timed(t)
        record("6.1", "Second chat response", len(response_text) > 0, ms)
        record("6.2", "query_graph tool used", has_query_graph, ms,
               "" if has_query_graph else "no tool_start for query_graph")
    except Exception as e:
        ms = timed(t)
        record("6.1", "Second chat response", False, ms, str(e))
        record("6.2", "query_graph tool used", False, ms)


# ── Section 7: Admin Endpoints ──


async def test_admin_endpoints(client: httpx.AsyncClient, trace_id: str):
    print("\n--- Section 7: Admin Endpoints ---")

    if not ADMIN_API_KEY:
        for i, name in enumerate(["Trace lookup", "User messages", "User graph",
                                   "User profile", "Recent jobs", "Errors", "Error summary"], 1):
            record(f"7.{i}", name, False, 0, "ADMIN_API_KEY not set")
        return

    tests = [
        (f"/admin/trace/{trace_id}" if trace_id else "/admin/trace/none", "Trace lookup"),
        (f"/admin/user/{EVAL_USER_ID}/messages", "User messages"),
        (f"/admin/user/{EVAL_USER_ID}/graph", "User graph"),
        (f"/admin/user/{EVAL_USER_ID}/profile", "User profile"),
        ("/admin/jobs/recent", "Recent jobs"),
        ("/admin/errors", "Errors"),
        ("/admin/errors/summary", "Error summary"),
    ]

    for i, (path, name) in enumerate(tests, 1):
        t = time.perf_counter()
        r = await get(client, path, headers=admin_auth())
        record(f"7.{i}", name, r.status_code == 200, timed(t),
               "" if r.status_code == 200 else f"status={r.status_code}")


# ── Section 8: Subscriptions & Webhooks ──


async def test_subscriptions_webhooks(client: httpx.AsyncClient):
    print("\n--- Section 8: Subscriptions & Webhooks ---")

    t = time.perf_counter()
    r = await post(client, "/api/push/subscribe",
                   json={"endpoint": "https://example.com", "keys": {"p256dh": "x", "auth": "y"}},
                   headers=eval_auth())
    # Could be 200 (subscribed) or 404 (route doesn't exist) or 422
    record("8.1", "Push subscribe", r.status_code in (200, 201), timed(t),
           f"status={r.status_code}")

    t = time.perf_counter()
    r = await post(client, "/api/subscribe", headers=eval_auth())
    # No Stripe key configured → error or checkout URL
    record("8.2", "Stripe subscribe", r.status_code in (200, 400, 422, 500), timed(t),
           f"status={r.status_code}")

    t = time.perf_counter()
    r = await post(client, "/api/webhooks/stripe", content=b"{}")
    record("8.3", "Stripe webhook no sig → 400", r.status_code in (400, 401, 403), timed(t),
           f"status={r.status_code}")

    t = time.perf_counter()
    r = await post(client, "/webhooks/email/inbound", content=b"{}")
    record("8.4", "Email webhook no secret → 403", r.status_code in (400, 401, 403, 404), timed(t),
           f"status={r.status_code}")


# ── Section 9: Feeds ──


async def test_feeds(client: httpx.AsyncClient):
    print("\n--- Section 9: Feeds ---")

    t = time.perf_counter()
    r = await get(client, "/api/feed/nonexistent.ics")
    record("9.1", "Nonexistent feed → 404", r.status_code == 404, timed(t),
           f"status={r.status_code}")


# ── Section 10: GDPR Deletion ──


async def test_gdpr_deletion(client: httpx.AsyncClient):
    print("\n--- Section 10: GDPR Deletion ---")

    t = time.perf_counter()
    r = await delete(client, "/api/account", headers=eval_auth())
    ok = r.status_code == 200
    detail = ""
    if ok:
        data = r.json()
        detail = json.dumps(data)[:100]
    record("10.1", "Account deletion", ok, timed(t), detail if not ok else "")

    # Verify deletion
    if ADMIN_API_KEY:
        t = time.perf_counter()
        r = await get(client, f"/admin/user/{EVAL_USER_ID}/messages", headers=admin_auth())
        if r.status_code == 200:
            msgs = r.json() if isinstance(r.json(), list) else r.json().get("messages", [])
            record("10.2", "Messages empty post-deletion", len(msgs) == 0, timed(t),
                   f"got {len(msgs)} messages")
        else:
            record("10.2", "Messages empty post-deletion", False, timed(t), f"status={r.status_code}")

        t = time.perf_counter()
        r = await get(client, f"/admin/user/{EVAL_USER_ID}/graph", headers=admin_auth())
        if r.status_code == 200:
            data = r.json()
            nodes = data.get("nodes", [])
            record("10.3", "Graph empty post-deletion", len(nodes) == 0, timed(t),
                   f"got {len(nodes)} nodes")
        else:
            record("10.3", "Graph empty post-deletion", False, timed(t), f"status={r.status_code}")
    else:
        record("10.2", "Messages empty post-deletion", False, 0, "ADMIN_API_KEY not set")
        record("10.3", "Graph empty post-deletion", False, 0, "ADMIN_API_KEY not set")


# ── Main ──


async def main():
    print(f"=== Unspool API Smoke Test ===")
    print(f"Target: {BASE_URL}")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print(f"Eval key: {'set' if EVAL_API_KEY else 'NOT SET'}")
    print(f"Admin key: {'set' if ADMIN_API_KEY else 'NOT SET'}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        await test_infrastructure(client)
        await test_authentication(client)
        await test_input_validation(client)
        trace_id, session_id = await test_chat_pipeline(client)
        await test_cold_path(client)
        await test_graph_context(client, session_id)
        await test_admin_endpoints(client, trace_id)
        await test_subscriptions_webhooks(client)
        await test_feeds(client)
        await test_gdpr_deletion(client)

    # Summary
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    total = len(results)

    print(f"\n{'=' * 40}")
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
