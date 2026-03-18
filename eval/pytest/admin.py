from __future__ import annotations

from typing import Any

import httpx


class AdminClient:
    def __init__(self, base_url: str, admin_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.admin_key = admin_key

    def _headers(self) -> dict[str, str]:
        return {"X-Admin-Key": self.admin_key}

    async def cleanup(self) -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=30
        ) as http:
            r = await http.delete("/admin/eval-cleanup", headers=self._headers())
            r.raise_for_status()
            return r.json()

    async def get_items(
        self, user_id: str, status: str = "open"
    ) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=30
        ) as http:
            r = await http.get(
                f"/admin/user/{user_id}/items",
                params={"status": status},
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json()

    async def get_messages(
        self, user_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=30
        ) as http:
            r = await http.get(
                f"/admin/user/{user_id}/messages",
                params={"limit": limit},
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json()

    async def get_trace(self, trace_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=30
        ) as http:
            r = await http.get(
                f"/admin/trace/{trace_id}",
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json()
