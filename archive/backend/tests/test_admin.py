from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app

_ADMIN_HEADERS = {"X-Admin-Key": "test-admin-key"}


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _patch_checks(**overrides: dict) -> tuple:
    """Return context managers that patch all _check_* helpers in admin.

    By default every service returns {"status": "ok"}.
    Pass overrides like db={"status": "error", "error": "boom"} to change one.
    """
    defaults = {
        "db": {"status": "ok"},
        "redis": {"status": "ok"},
        "qstash": {"status": "ok"},
        "llm": {"status": "ok"},
        "langfuse": {"status": "skipped", "reason": "not configured"},
    }
    defaults.update(overrides)

    patches = []
    for name, result in defaults.items():
        mock = AsyncMock(return_value=result)
        patches.append(patch(f"src.api.health_checks._check_{name}", mock))
    return tuple(patches)


def test_health_deep_all_ok(client: TestClient) -> None:
    patches = _patch_checks()
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        resp = client.get("/admin/health/deep", headers=_ADMIN_HEADERS)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "git_sha" in data
    assert "environment" in data
    assert "total_ms" in data
    assert "services" in data
    assert data["services"]["db"]["status"] == "ok"
    assert data["services"]["redis"]["status"] == "ok"
    assert data["services"]["langfuse"]["status"] == "skipped"


def test_health_deep_db_failure(client: TestClient) -> None:
    patches = _patch_checks(db={"status": "error", "error": "connection refused"})
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        resp = client.get("/admin/health/deep", headers=_ADMIN_HEADERS)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["services"]["db"]["status"] == "error"
    assert "connection refused" in data["services"]["db"]["error"]


def test_health_deep_requires_admin_key(client: TestClient) -> None:
    resp = client.get("/admin/health/deep")
    assert resp.status_code in (401, 403)
