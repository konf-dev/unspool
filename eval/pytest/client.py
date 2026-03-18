from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import httpx


@dataclass
class EvalResponse:
    status_code: int
    response_text: str
    events: list[dict] = field(default_factory=list)
    latency_ms: float = 0.0
    ttft_ms: float | None = None
    trace_id: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


class EvalClient:
    def __init__(self, base_url: str, auth_token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token

    async def send_message(
        self,
        message: str,
        *,
        session_id: str = "eval-session",
        timeout: float = 60.0,
    ) -> EvalResponse:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.auth_token}",
        }
        body = {"message": message, "session_id": session_id}

        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=timeout
        ) as http:
            start = time.perf_counter()
            ttft_ms: float | None = None
            events: list[dict] = []

            async with http.stream(
                "POST", "/api/chat", json=body, headers=headers
            ) as response:
                trace_id = response.headers.get("x-trace-id")
                status_code = response.status_code
                resp_headers = dict(response.headers)

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
            response_text = "".join(
                e.get("content", "")
                for e in events
                if e.get("type") == "token"
            )

            return EvalResponse(
                status_code=status_code,
                response_text=response_text,
                events=events,
                latency_ms=latency_ms,
                ttft_ms=ttft_ms,
                trace_id=trace_id,
                headers=resp_headers,
            )
