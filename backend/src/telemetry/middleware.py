import os
import subprocess
import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from src.telemetry.logger import get_logger

_log = get_logger("http")


def _get_git_sha() -> str:
    sha = os.environ.get("GIT_SHA")
    if sha:
        return sha[:8]
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


GIT_SHA = _get_git_sha()


class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint,
    ) -> Response:
        trace_id = str(uuid.uuid4())
        request.state.trace_id = trace_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(trace_id=trace_id, git_sha=GIT_SHA)

        _log.info("request.start", method=request.method, path=request.url.path)

        start = time.perf_counter()
        response = await call_next(request)
        latency_ms = round((time.perf_counter() - start) * 1000, 2)

        _log.info(
            "request.end",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            latency_ms=latency_ms,
        )

        response.headers["X-Trace-Id"] = trace_id
        return response
