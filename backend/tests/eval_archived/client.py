import contextlib
import json
import time
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
from httpx import ASGITransport

from tests.eval.fixtures import (
    InMemoryStore,
    eval_items,
    eval_messages,
)


def _parse_sse_events(body: str) -> list[dict]:
    events = []
    for line in body.strip().split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            try:
                events.append(json.loads(line.removeprefix("data: ")))
            except json.JSONDecodeError:
                pass
    return events


def _collect_response_text(events: list[dict]) -> str:
    return "".join(e.get("content", "") for e in events if e.get("type") == "token")


class EvalResponse:
    def __init__(
        self,
        *,
        status_code: int,
        response_text: str,
        events: list[dict],
        latency_ms: float,
        ttft_ms: float | None,
        trace_id: str | None,
        intent: str | None = None,
        confidence: float | None = None,
    ) -> None:
        self.status_code = status_code
        self.response_text = response_text
        self.events = events
        self.latency_ms = latency_ms
        self.ttft_ms = ttft_ms
        self.trace_id = trace_id
        self.intent = intent
        self.confidence = confidence


class EvalClient:
    """SSE client for eval tests. Supports local (ASGI) and remote modes."""

    def __init__(
        self,
        target: str = "local",
        base_url: str = "http://test",
        auth_token: str | None = None,
        admin_key: str | None = None,
    ) -> None:
        self.target = target
        self.base_url = base_url
        self.auth_token = auth_token
        self.admin_key = admin_key
        self._captured_intent: str | None = None
        self._captured_confidence: float | None = None

    async def send_message(
        self,
        message: str,
        *,
        store: InMemoryStore | None = None,
        session_id: str = "eval-session",
    ) -> EvalResponse:
        if self.target == "local":
            return await self._send_local(message, store=store, session_id=session_id)
        resp = await self._send_remote(message, session_id=session_id)
        if store is not None and self.admin_key:
            await self._sync_store_from_remote(store)
        return resp

    async def cleanup_remote(self) -> None:
        """Delete all eval user data via admin API."""
        if not self.admin_key:
            return
        async with httpx.AsyncClient(base_url=self.base_url) as client:
            await client.delete(
                "/admin/eval-cleanup",
                headers={"X-Admin-Key": self.admin_key},
                timeout=10.0,
            )

    async def _sync_store_from_remote(self, store: InMemoryStore) -> None:
        """Fetch eval user's items from admin API into the local store."""
        from src.auth.supabase_auth import EVAL_USER_ID

        async with httpx.AsyncClient(base_url=self.base_url) as client:
            resp = await client.get(
                f"/admin/user/{EVAL_USER_ID}/items",
                headers={"X-Admin-Key": self.admin_key or ""},
                params={"status": "open"},
                timeout=10.0,
            )
            if resp.status_code == 200:
                store.items = resp.json()

    def _build_save_items_mock(self, store: InMemoryStore) -> Any:
        """Build a mock for save_items tool that routes through the InMemoryStore."""

        async def _mock_save_items(
            user_id: str,
            items: list[dict[str, Any]] | dict[str, Any] | None = None,
            source_message_id: str | None = None,
        ) -> list[dict[str, Any]]:
            if items is None:
                return []
            if isinstance(items, dict):
                items = items.get("items", [])
            if not isinstance(items, list):
                return []
            saved = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                result = await store.save_item(
                    user_id=user_id,
                    raw_text=item.get("raw_text", ""),
                    interpreted_action=item.get("interpreted_action", ""),
                    deadline_type=item.get("deadline_type"),
                    deadline_at=item.get("deadline_at"),
                    urgency_score=item.get("urgency_score", 0.0),
                    energy_estimate=item.get("energy_estimate"),
                    source_message_id=source_message_id,
                    status="open",
                )
                saved.append(result)
            return saved

        return _mock_save_items

    @staticmethod
    def _ensure_tools_registered() -> None:
        """Import all tool modules to trigger @register_tool decorators.

        In production this happens in the lifespan handler. For eval tests
        we call it eagerly since the ASGI transport may not run lifespan.
        """
        from src.tools.registry import get_tool_registry

        if "enrich_items" in get_tool_registry():
            return

        import importlib
        import pkgutil

        import src.tools as _tools_package

        for _, module_name, _ in pkgutil.iter_modules(_tools_package.__path__):
            importlib.import_module(f"src.tools.{module_name}")

    async def _send_local(
        self,
        message: str,
        *,
        store: InMemoryStore | None = None,
        session_id: str = "eval-session",
    ) -> EvalResponse:
        from src.auth.supabase_auth import get_current_user
        from src.main import app

        self._ensure_tools_registered()

        store = store or InMemoryStore(
            initial_items=eval_items(),
            initial_messages=eval_messages(),
        )

        app.dependency_overrides[get_current_user] = lambda: "eval-user-001"

        self._captured_intent = None
        self._captured_confidence = None

        stack = contextlib.ExitStack()

        # Patch DB/Redis calls in chat.py.
        # Use side_effect=store.save_message directly (async fn). Don't combine
        # new_callable=AsyncMock with a sync lambda returning a coroutine —
        # AsyncMock wraps it in a second coroutine, returning an unawaited coro.
        stack.enter_context(
            patch(
                "src.api.chat.db.save_message",
                new=AsyncMock(side_effect=store.save_message),
            )
        )
        stack.enter_context(
            patch(
                "src.api.chat.redis.session_get",
                new_callable=AsyncMock,
                return_value=None,
            )
        )
        stack.enter_context(
            patch("src.api.chat.redis.session_set", new_callable=AsyncMock)
        )
        stack.enter_context(
            patch(
                "src.api.chat.redis.rate_limit_check",
                new_callable=AsyncMock,
                return_value=(True, 99),
            )
        )
        stack.enter_context(
            patch(
                "src.api.chat.db.get_user_tier",
                new_callable=AsyncMock,
                return_value="paid",
            )
        )
        stack.enter_context(patch("src.api.chat.dispatch_job", new_callable=AsyncMock))
        stack.enter_context(patch("src.api.chat._check_gate", new_callable=AsyncMock))

        # Patch db calls used by tools. These are accessed via `db.<fn>` where
        # db is imported as `from src.db import supabase as db` in each tool module.
        # db_tools
        stack.enter_context(
            patch(
                "src.tools.db_tools.db.save_item",
                new=AsyncMock(side_effect=store.save_item),
            )
        )
        stack.enter_context(
            patch("src.tools.db_tools.db.save_item_event", new_callable=AsyncMock)
        )
        stack.enter_context(
            patch(
                "src.tools.db_tools.db.update_item",
                new_callable=AsyncMock,
                return_value={"id": "mock", "status": "done"},
            )
        )
        stack.enter_context(
            patch(
                "src.tools.db_tools.db.search_items_text",
                new=AsyncMock(side_effect=store.fetch_items),
            )
        )
        stack.enter_context(
            patch(
                "src.tools.db_tools.db.search_items_semantic",
                new_callable=AsyncMock,
                return_value=[],
            )
        )
        stack.enter_context(
            patch(
                "src.tools.db_tools.db.search_items_hybrid",
                new_callable=AsyncMock,
                return_value=[],
            )
        )
        # item_matching
        stack.enter_context(
            patch(
                "src.tools.item_matching.db.search_items_text",
                new=AsyncMock(side_effect=store.fetch_items),
            )
        )
        stack.enter_context(
            patch(
                "src.tools.item_matching.db.get_open_items",
                new=AsyncMock(side_effect=store.fetch_items),
            )
        )
        stack.enter_context(
            patch(
                "src.tools.item_matching.db.update_item",
                new_callable=AsyncMock,
                return_value={"id": "mock", "status": "done"},
            )
        )
        stack.enter_context(
            patch("src.tools.item_matching.db.save_item_event", new_callable=AsyncMock)
        )
        # scoring_tools / momentum_tools
        stack.enter_context(
            patch(
                "src.tools.momentum_tools.db.get_recently_done_count",
                new_callable=AsyncMock,
                return_value=2,
            )
        )
        # query_tools
        stack.enter_context(
            patch(
                "src.tools.query_tools.db.resolve_entity",
                new_callable=AsyncMock,
                return_value=None,
            )
        )
        stack.enter_context(
            patch(
                "src.tools.query_tools.db.get_items_filtered",
                new=AsyncMock(side_effect=store.fetch_items),
            )
        )
        stack.enter_context(
            patch(
                "src.tools.query_tools.db.get_memories_filtered",
                new_callable=AsyncMock,
                return_value=[],
            )
        )
        stack.enter_context(
            patch(
                "src.tools.query_tools.db.get_messages_filtered",
                new=AsyncMock(side_effect=store.fetch_messages),
            )
        )
        stack.enter_context(
            patch(
                "src.tools.query_tools.db.get_calendar_events_filtered",
                new_callable=AsyncMock,
                return_value=[],
            )
        )
        # embedding provider (used by search tools, avoid real API calls)
        stack.enter_context(
            patch(
                "src.tools.db_tools.get_embedding_provider",
                return_value=AsyncMock(embed=AsyncMock(return_value=[0.0] * 1536)),
            )
        )

        # Patch context loaders via _LOADERS dict. assemble_context uses
        # _LOADERS[field](user_id, ...) — patching module-level names has no
        # effect because _LOADERS holds direct references captured at import time.
        stack.enter_context(
            patch.dict(
                "src.orchestrator.context._LOADERS",
                {
                    "profile": store.fetch_profile,
                    "recent_messages": store.fetch_messages,
                    "open_items": store.fetch_items,
                    "urgent_items": store.fetch_urgent_items,
                    "entities": store.fetch_entities,
                    "memories": store.fetch_memories,
                    "calendar_events": store.fetch_calendar_events,
                    "graph_context": store.fetch_graph_context,
                },
            )
        )

        # Also patch context_tools.db.* — pipeline tool steps call the
        # tool registry functions (e.g. fetch_urgent_items), which internally
        # call db.get_urgent_items etc. These need mocking too.
        stack.enter_context(
            patch(
                "src.tools.context_tools.db.get_messages",
                new=AsyncMock(side_effect=store.fetch_messages),
            )
        )
        stack.enter_context(
            patch(
                "src.tools.context_tools.db.get_profile",
                new=AsyncMock(side_effect=store.fetch_profile),
            )
        )
        stack.enter_context(
            patch(
                "src.tools.context_tools.db.get_open_items",
                new=AsyncMock(side_effect=store.fetch_items),
            )
        )
        stack.enter_context(
            patch(
                "src.tools.context_tools.db.get_urgent_items",
                new=AsyncMock(side_effect=store.fetch_urgent_items),
            )
        )
        stack.enter_context(
            patch(
                "src.tools.context_tools.db.get_pool",
                return_value=AsyncMock(
                    fetch=AsyncMock(return_value=[]),
                ),
            )
        )
        stack.enter_context(
            patch(
                "src.tools.context_tools.db.search_memories_semantic",
                new_callable=AsyncMock,
                return_value=[],
            )
        )

        # Wrap classify_intent to capture the result.
        # chat.py imports: from src.orchestrator.intent import classify_intent
        # So we patch the module-level reference in chat.py.
        from src.orchestrator.intent import classify_intent as _real_classify

        captured = self

        async def _capturing_classify(msg: str, ctx: object) -> tuple[str, str, float]:
            result = await _real_classify(msg, ctx)
            captured._captured_intent = result[0]
            captured._captured_confidence = result[2]
            return result

        stack.enter_context(
            patch(
                "src.orchestrator.intent.classify_intent",
                side_effect=_capturing_classify,
            )
        )

        try:
            with stack:
                transport = ASGITransport(app=app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    start = time.perf_counter()
                    response = await client.post(
                        "/api/chat",
                        json={"message": message, "session_id": session_id},
                        headers={"Authorization": "Bearer eval-token"},
                        timeout=90.0,
                    )
                    latency_ms = (time.perf_counter() - start) * 1000

                events = _parse_sse_events(response.text)
                response_text = _collect_response_text(events)
                trace_id = response.headers.get("X-Trace-Id")

                return EvalResponse(
                    status_code=response.status_code,
                    response_text=response_text,
                    events=events,
                    latency_ms=latency_ms,
                    ttft_ms=None,
                    trace_id=trace_id,
                    intent=self._captured_intent,
                    confidence=self._captured_confidence,
                )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    async def _send_remote(
        self,
        message: str,
        *,
        session_id: str = "eval-session",
    ) -> EvalResponse:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        async with httpx.AsyncClient(base_url=self.base_url) as client:
            start = time.perf_counter()
            ttft_ms = None
            events: list[dict] = []

            async with client.stream(
                "POST",
                "/api/chat",
                json={"message": message, "session_id": session_id},
                headers=headers,
                timeout=90.0,
            ) as response:
                trace_id = response.headers.get("X-Trace-Id")
                status_code = response.status_code

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data: "):
                        continue

                    if ttft_ms is None:
                        ttft_ms = (time.perf_counter() - start) * 1000

                    try:
                        events.append(json.loads(line.removeprefix("data: ")))
                    except json.JSONDecodeError:
                        pass

            latency_ms = (time.perf_counter() - start) * 1000
            response_text = _collect_response_text(events)

            return EvalResponse(
                status_code=status_code,
                response_text=response_text,
                events=events,
                latency_ms=latency_ms,
                ttft_ms=ttft_ms,
                trace_id=trace_id,
            )
