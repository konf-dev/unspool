import os
import subprocess
import time
import uuid
from collections.abc import MutableMapping
from typing import Any

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.telemetry.logger import get_logger

_log = get_logger("http")


def _get_git_sha() -> str:
    sha = os.environ.get("GIT_SHA") or os.environ.get("RAILWAY_GIT_COMMIT_SHA")
    if sha:
        return sha[:8]
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


GIT_SHA = _get_git_sha()


class TraceMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        trace_id = str(uuid.uuid4())

        state: MutableMapping[str, Any] = scope.setdefault("state", {})
        state["trace_id"] = trace_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(trace_id=trace_id, git_sha=GIT_SHA)

        method = scope.get("method", "")
        path = scope.get("path", "")
        _log.info("request.start", method=method, path=path)

        start = time.perf_counter()

        status_code = 0

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
                headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                headers.append((b"x-trace-id", trace_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)

        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        _log.info(
            "request.end",
            method=method,
            path=path,
            status_code=status_code,
            latency_ms=latency_ms,
        )
