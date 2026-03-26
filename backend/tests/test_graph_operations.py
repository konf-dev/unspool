"""Tests for graph CRUD operations."""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestGraphOperations:
    """Unit tests for graph.py operations using mocked sessions."""

    @pytest.mark.asyncio
    async def test_append_event(self):
        """append_event creates an EventStream record."""
        from src.core.graph import append_event

        session = AsyncMock()
        session.flush = AsyncMock()

        user_id = uuid.uuid4()
        event = await append_event(session, user_id, "TestEvent", {"key": "value"})

        session.add.assert_called_once()
        session.flush.assert_called_once()
        assert event.event_type == "TestEvent"
        assert event.user_id == user_id

    @pytest.mark.asyncio
    async def test_get_or_create_node_creates(self):
        """get_or_create_node creates when no match exists."""
        from src.core.graph import get_or_create_node

        session = AsyncMock()
        session.flush = AsyncMock()

        # Mock execute to return no existing node
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_result)

        user_id = uuid.uuid4()
        node = await get_or_create_node(session, user_id, "Test Node", "concept")

        assert node.content == "Test Node"
        assert node.node_type == "concept"
        # Should have been added to session
        assert session.add.call_count >= 1


class TestPIIScrubber:
    def test_scrubs_email(self):
        from src.telemetry.pii import scrub_pii
        assert "[EMAIL]" in scrub_pii("contact test@example.com")

    def test_scrubs_phone(self):
        from src.telemetry.pii import scrub_pii
        assert "[PHONE]" in scrub_pii("call 408-555-1234")

    def test_scrubs_ssn(self):
        from src.telemetry.pii import scrub_pii
        assert "[SSN]" in scrub_pii("SSN is 123-45-6789")

    def test_preserves_normal_text(self):
        from src.telemetry.pii import scrub_pii
        text = "Buy groceries and finish thesis"
        assert scrub_pii(text) == text
