"""DB extraction verification: send messages, verify items saved via admin API."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from .admin import AdminClient
from .client import EvalClient
from .conftest import EVAL_USER_ID


@pytest.fixture(autouse=True)
async def cleanup_before(admin: AdminClient) -> None:
    await admin.cleanup()
    # Brief delay for cleanup to propagate
    await asyncio.sleep(0.5)


@pytest.mark.asyncio
async def test_single_task_saved(client: EvalClient, admin: AdminClient) -> None:
    resp = await client.send_message(
        "I need to buy milk",
        session_id=f"extract-{uuid.uuid4().hex[:8]}",
    )
    assert resp.status_code == 200
    assert "went wrong" not in resp.response_text.lower()

    # Wait for save to complete (synchronous in pipeline, but allow margin)
    await asyncio.sleep(1)

    items = await admin.get_items(EVAL_USER_ID)
    assert len(items) >= 1, f"Expected at least 1 item, got {len(items)}"


@pytest.mark.asyncio
async def test_multi_task_saved(client: EvalClient, admin: AdminClient) -> None:
    resp = await client.send_message(
        "buy groceries, call the dentist, and finish the report",
        session_id=f"extract-{uuid.uuid4().hex[:8]}",
    )
    assert resp.status_code == 200

    await asyncio.sleep(1)

    items = await admin.get_items(EVAL_USER_ID)
    assert len(items) >= 3, f"Expected at least 3 items, got {len(items)}"


@pytest.mark.asyncio
async def test_hard_deadline_saved(client: EvalClient, admin: AdminClient) -> None:
    resp = await client.send_message(
        "the tax return is due April 15th, can't miss it",
        session_id=f"extract-{uuid.uuid4().hex[:8]}",
    )
    assert resp.status_code == 200

    await asyncio.sleep(1)

    items = await admin.get_items(EVAL_USER_ID)
    assert len(items) >= 1
    item = items[0]
    assert item.get("deadline_type") == "hard", (
        f"Expected hard deadline, got {item.get('deadline_type')}"
    )


@pytest.mark.asyncio
async def test_deadline_at_populated(client: EvalClient, admin: AdminClient) -> None:
    resp = await client.send_message(
        "submit the proposal by Friday",
        session_id=f"extract-{uuid.uuid4().hex[:8]}",
    )
    assert resp.status_code == 200

    await asyncio.sleep(1)

    items = await admin.get_items(EVAL_USER_ID)
    assert len(items) >= 1
    assert items[0].get("deadline_at") is not None, "Expected deadline_at to be set"


@pytest.mark.asyncio
async def test_low_energy_estimate(client: EvalClient, admin: AdminClient) -> None:
    resp = await client.send_message(
        "I need to text my mom back",
        session_id=f"extract-{uuid.uuid4().hex[:8]}",
    )
    assert resp.status_code == 200

    await asyncio.sleep(1)

    items = await admin.get_items(EVAL_USER_ID)
    assert len(items) >= 1
    assert items[0].get("energy_estimate") == "low", (
        f"Expected low energy, got {items[0].get('energy_estimate')}"
    )


@pytest.mark.asyncio
async def test_high_energy_estimate(client: EvalClient, admin: AdminClient) -> None:
    resp = await client.send_message(
        "I need to write the entire project proposal from scratch",
        session_id=f"extract-{uuid.uuid4().hex[:8]}",
    )
    assert resp.status_code == 200

    await asyncio.sleep(1)

    items = await admin.get_items(EVAL_USER_ID)
    assert len(items) >= 1
    assert items[0].get("energy_estimate") == "high", (
        f"Expected high energy, got {items[0].get('energy_estimate')}"
    )


@pytest.mark.asyncio
async def test_soft_deadline(client: EvalClient, admin: AdminClient) -> None:
    resp = await client.send_message(
        "should probably get the oil change done sometime this week",
        session_id=f"extract-{uuid.uuid4().hex[:8]}",
    )
    assert resp.status_code == 200

    await asyncio.sleep(1)

    items = await admin.get_items(EVAL_USER_ID)
    assert len(items) >= 1
    assert items[0].get("deadline_type") == "soft", (
        f"Expected soft deadline, got {items[0].get('deadline_type')}"
    )


@pytest.mark.asyncio
async def test_implicit_task_captured(
    client: EvalClient, admin: AdminClient
) -> None:
    resp = await client.send_message(
        "my car registration expires next month",
        session_id=f"extract-{uuid.uuid4().hex[:8]}",
    )
    assert resp.status_code == 200

    await asyncio.sleep(1)

    items = await admin.get_items(EVAL_USER_ID)
    assert len(items) >= 1, "Expected implicit task to be captured"


@pytest.mark.asyncio
async def test_relative_date_tomorrow(
    client: EvalClient, admin: AdminClient
) -> None:
    resp = await client.send_message(
        "I need to call the doctor tomorrow",
        session_id=f"extract-{uuid.uuid4().hex[:8]}",
    )
    assert resp.status_code == 200
    assert "went wrong" not in resp.response_text.lower()

    await asyncio.sleep(1)

    items = await admin.get_items(EVAL_USER_ID)
    assert len(items) >= 1
    assert items[0].get("deadline_at") is not None, (
        "Expected deadline_at for 'tomorrow'"
    )


@pytest.mark.asyncio
async def test_mixed_items_count(client: EvalClient, admin: AdminClient) -> None:
    resp = await client.send_message(
        "text sarah back, write the quarterly report by Wednesday, "
        "and maybe clean the garage sometime",
        session_id=f"extract-{uuid.uuid4().hex[:8]}",
    )
    assert resp.status_code == 200

    await asyncio.sleep(1)

    items = await admin.get_items(EVAL_USER_ID)
    assert len(items) >= 3, f"Expected at least 3 items, got {len(items)}"
