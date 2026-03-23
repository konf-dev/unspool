"""Tests for hot path tools."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestQueryGraph:
    @pytest.mark.asyncio
    async def test_returns_results(self):
        """query_graph returns formatted node results."""
        from src.agents.hot_path.tools import _exec_query_graph

        mock_node = MagicMock()
        mock_node.id = "test-uuid"
        mock_node.content = "Buy groceries"
        mock_node.node_type = "action"

        with patch("src.agents.hot_path.tools._get_embedding", new_callable=AsyncMock) as mock_embed, \
             patch("src.agents.hot_path.tools.AsyncSessionLocal") as mock_session_cls:

            mock_embed.return_value = [0.1] * 1536

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session_cls.return_value = mock_session

            # Mock search_nodes_semantic
            with patch("src.agents.hot_path.tools.search_nodes_semantic", new_callable=AsyncMock) as mock_search:
                mock_search.return_value = [mock_node]

                # Mock edge query
                mock_edge_result = MagicMock()
                mock_edge_result.scalars.return_value.all.return_value = []
                mock_session.execute = AsyncMock(return_value=mock_edge_result)
                mock_session.get = AsyncMock(return_value=None)

                results = await _exec_query_graph(
                    user_id="b8a2e17e-ff55-485f-ad6c-29055a607b33",
                    semantic_query="groceries",
                )

                assert isinstance(results, list)


class TestMutateGraph:
    @pytest.mark.asyncio
    async def test_invalid_status_returns_error(self):
        """SET_STATUS with invalid value returns error."""
        from src.agents.hot_path.tools import _exec_mutate_graph

        result = await _exec_mutate_graph(
            user_id="b8a2e17e-ff55-485f-ad6c-29055a607b33",
            action="SET_STATUS",
            node_id="b8a2e17e-ff55-485f-ad6c-29055a607b33",
            value="INVALID",
        )
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_unknown_action_returns_error(self):
        """Unknown action returns error message."""
        from src.agents.hot_path.tools import _exec_mutate_graph

        result = await _exec_mutate_graph(
            user_id="b8a2e17e-ff55-485f-ad6c-29055a607b33",
            action="DESTROY",
            node_id="b8a2e17e-ff55-485f-ad6c-29055a607b33",
        )
        assert "Unknown action" in result

    @pytest.mark.asyncio
    async def test_add_edge_requires_target(self):
        """ADD_EDGE without target_node_id returns error."""
        from src.agents.hot_path.tools import _exec_mutate_graph

        result = await _exec_mutate_graph(
            user_id="b8a2e17e-ff55-485f-ad6c-29055a607b33",
            action="ADD_EDGE",
            node_id="b8a2e17e-ff55-485f-ad6c-29055a607b33",
        )
        assert "Error" in result
