"""Tests for simulation types, configuration, and smoke test for the pipeline."""

from unittest.mock import AsyncMock, patch

import pytest
from graph_lab.src.config import load_persona
from graph_lab.src.types import (
    EvaluationResult,
    SimulationResult,
    SimulationTurn,
    TurnPerf,
)

# --- Model tests ---


def test_simulation_turn_model():
    turn = SimulationTurn(
        day=1,
        time_of_day="evening",
        user_message="hey, I need to email my advisor",
        unspool_response="Got it. Want to do that now or later?",
        user_state={"energy": "medium", "mood": "neutral"},
        graph_stats={"nodes": 5, "edges": 3, "stream_entries": 2},
    )
    assert turn.day == 1
    assert "email" in turn.user_message


def test_simulation_turn_with_perf():
    perf = TurnPerf(
        ingest_ms=150.5,
        retrieval_ms=80.2,
        reasoning_ms=2100.0,
        feedback_ms=300.0,
        total_ms=2630.7,
    )
    turn = SimulationTurn(
        day=1,
        time_of_day="morning",
        user_message="hi",
        unspool_response="hey!",
        perf=perf,
    )
    assert turn.perf.total_ms == 2630.7
    assert turn.perf.ingest_ms == 150.5


def test_turn_perf_defaults():
    perf = TurnPerf()
    assert perf.total_ms == 0
    assert perf.user_sim_ms == 0


def test_evaluation_result_model():
    result = EvaluationResult(
        scores={
            "surfacing_quality": 7.5,
            "emotional_intelligence": 8.0,
            "memory_accuracy": 6.0,
        },
        overall_score=7.2,
        assessment="Good emotional awareness, needs better memory.",
    )
    assert result.overall_score == 7.2
    assert len(result.scores) == 3


def test_simulation_result_model():
    result = SimulationResult(
        persona="maya",
        turns=[
            SimulationTurn(
                day=1,
                time_of_day="evening",
                user_message="hi",
                unspool_response="hey!",
            ),
        ],
        evaluation=EvaluationResult(overall_score=7.0),
        final_graph_stats={"nodes": 10, "edges": 8, "stream_entries": 4},
    )
    assert result.persona == "maya"
    assert len(result.turns) == 1


def test_simulation_result_serializes_to_json():
    result = SimulationResult(
        persona="maya",
        turns=[
            SimulationTurn(
                day=1,
                time_of_day="evening",
                user_message="hi",
                unspool_response="hey!",
                perf=TurnPerf(total_ms=1500),
            ),
        ],
        evaluation=EvaluationResult(
            scores={"surfacing_quality": 7.0},
            overall_score=7.0,
        ),
        final_graph_stats={"nodes": 5, "edges": 3},
    )
    json_str = result.model_dump_json(indent=2)
    assert '"persona": "maya"' in json_str
    assert '"total_ms": 1500' in json_str
    assert '"surfacing_quality": 7.0' in json_str


# --- Persona tests ---


def test_persona_config_loads_maya():
    persona = load_persona("maya")
    assert persona.name == "Maya"
    assert persona.age == 27
    assert persona.simulation.duration_days == 30
    assert len(persona.behavior_patterns) > 0


def test_persona_config_loads_marcus():
    persona = load_persona("marcus")
    assert persona.name == "Marcus"
    assert persona.simulation.messages_per_day == [2, 6]


def test_persona_config_loads_priya():
    persona = load_persona("priya")
    assert persona.name == "Priya"
    assert persona.simulation.bad_day_probability == 0.25


def test_persona_config_missing_raises():
    with pytest.raises(FileNotFoundError):
        load_persona("nonexistent_persona")


# --- Simulation config tests ---


def test_simulation_config_loads():
    from graph_lab.src.config import load_simulation_config

    config = load_simulation_config()
    assert "simulator" in config
    assert "evaluator" in config
    assert "model" in config["simulator"]
    assert "scoring_dimensions" in config


# --- Transcript formatting tests ---


def test_format_transcript_md():
    from graph_lab.simulate import _format_transcript_md

    result = SimulationResult(
        persona="maya",
        turns=[
            SimulationTurn(
                day=1,
                time_of_day="evening",
                user_message="I need to do laundry",
                unspool_response="Want to tackle that now?",
                perf=TurnPerf(ingest_ms=100, retrieval_ms=50, reasoning_ms=2000, total_ms=2150),
                graph_stats={"nodes": 3, "edges": 2, "stream_entries": 2},
            ),
            SimulationTurn(
                day=2,
                time_of_day="morning",
                user_message="done with laundry",
                unspool_response="Nice!",
                perf=TurnPerf(total_ms=1800),
                graph_stats={"nodes": 5, "edges": 4, "stream_entries": 4},
            ),
        ],
        evaluation=EvaluationResult(
            scores={"surfacing_quality": 8.0},
            overall_score=8.0,
            assessment="Good job.",
        ),
        final_graph_stats={"nodes": 5, "edges": 4},
    )
    md = _format_transcript_md(result)
    assert "# Simulation: maya" in md
    assert "## Day 1" in md
    assert "## Day 2" in md
    assert "I need to do laundry" in md
    assert "ingest=100ms" in md
    assert "## Evaluation" in md
    assert "surfacing_quality" in md


# --- Smoke test (mocked LLM, real types) ---


@pytest.mark.asyncio
async def test_smoke_graph_chat_pipeline():
    """Smoke test: mock LLM + DB, verify the pipeline doesn't crash."""
    from graph_lab.simulate import _graph_chat

    mock_stream_entry = {"id": "raw_stream:test123", "content": "test"}
    mock_node = {"id": "node:abc", "content": "test task", "user_id": "smoke"}
    mock_subgraph_nodes = [mock_node]

    with (
        patch("graph_lab.simulate.db") as mock_db,
        patch("graph_lab.simulate.quick_ingest", new_callable=AsyncMock) as mock_ingest,
        patch("graph_lab.simulate.generate_embedding", new_callable=AsyncMock) as mock_emb,
        patch("graph_lab.simulate.build_active_subgraph", new_callable=AsyncMock) as mock_retrieval,
        patch("graph_lab.simulate.reason_and_respond_full", new_callable=AsyncMock) as mock_reason,
        patch("graph_lab.simulate.detect_feedback", new_callable=AsyncMock) as mock_feedback,
        patch("graph_lab.simulate.apply_feedback", new_callable=AsyncMock),
    ):
        mock_db.save_stream_entry = AsyncMock(return_value=mock_stream_entry)
        mock_ingest.return_value = [mock_node]
        mock_emb.return_value = [0.1] * 1536
        mock_retrieval.return_value = AsyncMock(
            nodes=mock_subgraph_nodes, edges=[], trigger_results=[]
        )
        mock_reason.return_value = "Got it, I'll remember that."
        mock_feedback.return_value = AsyncMock(
            surfaced_node_ids=[], completions_acknowledged=[], suppressions=[]
        )

        response, perf = await _graph_chat("smoke-user", "I have a meeting tomorrow")

        assert response == "Got it, I'll remember that."
        assert perf.total_ms > 0
        assert perf.ingest_ms >= 0
        mock_ingest.assert_called_once()
        mock_reason.assert_called_once()


@pytest.mark.asyncio
async def test_smoke_graph_chat_handles_embedding_failure():
    """Pipeline should work even if embedding generation fails."""
    from graph_lab.simulate import _graph_chat

    with (
        patch("graph_lab.simulate.db") as mock_db,
        patch("graph_lab.simulate.quick_ingest", new_callable=AsyncMock) as mock_ingest,
        patch("graph_lab.simulate.generate_embedding", new_callable=AsyncMock) as mock_emb,
        patch("graph_lab.simulate.build_active_subgraph", new_callable=AsyncMock) as mock_retrieval,
        patch("graph_lab.simulate.reason_and_respond_full", new_callable=AsyncMock) as mock_reason,
        patch("graph_lab.simulate.detect_feedback", new_callable=AsyncMock) as mock_feedback,
        patch("graph_lab.simulate.apply_feedback", new_callable=AsyncMock),
    ):
        mock_db.save_stream_entry = AsyncMock(return_value={"id": "raw_stream:x"})
        mock_ingest.return_value = []
        mock_emb.side_effect = Exception("API down")
        mock_retrieval.return_value = AsyncMock(nodes=[], edges=[], trigger_results=[])
        mock_reason.return_value = "Hey, what's up?"
        mock_feedback.return_value = AsyncMock(
            surfaced_node_ids=[], completions_acknowledged=[], suppressions=[]
        )

        response, perf = await _graph_chat("smoke-user", "hey")

        assert response == "Hey, what's up?"
        # Embedding failed but pipeline continued
        mock_retrieval.assert_called_once()
        call_args = mock_retrieval.call_args
        assert call_args[0][2] is None  # message_embedding is None


@pytest.mark.asyncio
async def test_smoke_graph_chat_handles_feedback_failure():
    """Pipeline should return response even if feedback detection fails."""
    from graph_lab.simulate import _graph_chat

    with (
        patch("graph_lab.simulate.db") as mock_db,
        patch("graph_lab.simulate.quick_ingest", new_callable=AsyncMock) as mock_ingest,
        patch("graph_lab.simulate.generate_embedding", new_callable=AsyncMock) as mock_emb,
        patch("graph_lab.simulate.build_active_subgraph", new_callable=AsyncMock) as mock_retrieval,
        patch("graph_lab.simulate.reason_and_respond_full", new_callable=AsyncMock) as mock_reason,
        patch("graph_lab.simulate.detect_feedback", new_callable=AsyncMock) as mock_feedback,
        patch("graph_lab.simulate.apply_feedback", new_callable=AsyncMock),
    ):
        mock_db.save_stream_entry = AsyncMock(return_value={"id": "raw_stream:x"})
        mock_ingest.return_value = []
        mock_emb.return_value = [0.1] * 1536
        mock_retrieval.return_value = AsyncMock(nodes=[], edges=[], trigger_results=[])
        mock_reason.return_value = "Here's what I think."
        mock_feedback.side_effect = Exception("Feedback LLM failed")

        response, perf = await _graph_chat("smoke-user", "what should I do")

        assert response == "Here's what I think."
        assert perf.total_ms > 0
