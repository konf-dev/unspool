"""Tests for corpus generation, validation, and replay."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from graph_lab.corpus.generate import (
    generate_message,
    generate_persona_corpus,
    load_all_scenarios,
    load_corpus_config,
    schedule_scenarios,
)
from graph_lab.corpus.types import (
    CorpusConfig,
    CorpusMessage,
    DayMarker,
    ReplayResult,
    ReplayTurn,
    ScenarioDef,
    ScenarioStep,
)
from graph_lab.corpus.validate import validate_corpus_dir, validate_corpus_file
from graph_lab.src.config import load_persona


class TestCorpusTypes:
    def test_corpus_message(self):
        msg = CorpusMessage(
            id="maya-d001-m000",
            persona="maya",
            day=1,
            message_index=0,
            time_of_day="morning",
            energy="medium",
            mood="neutral",
            content="i need to email my advisor",
            scenario_tag=None,
            generation_model="qwen2.5:7b",
        )
        assert msg.persona == "maya"
        assert msg.day == 1
        assert msg.scenario_tag is None

    def test_day_marker(self):
        marker = DayMarker(
            id="maya-d004-skip",
            persona="maya",
            day=4,
            skipped=True,
        )
        assert marker.type == "day_marker"
        assert marker.skipped is True

    def test_corpus_message_json_roundtrip(self):
        msg = CorpusMessage(
            id="test-d001-m000",
            persona="test",
            day=1,
            message_index=0,
            time_of_day="evening",
            energy="low",
            mood="bad",
            content="ugh forgot again",
            scenario_tag="time_change",
            generation_model="qwen2.5:7b",
        )
        json_str = msg.model_dump_json()
        parsed = CorpusMessage(**json.loads(json_str))
        assert parsed.id == msg.id
        assert parsed.scenario_tag == "time_change"

    def test_replay_turn(self):
        turn = ReplayTurn(
            corpus_id="maya-d001-m000",
            day=1,
            user_message="test",
            unspool_response="hi",
            total_ms=150.0,
        )
        assert turn.total_ms == 150.0

    def test_replay_result(self):
        result = ReplayResult(
            persona="maya",
            corpus_path="/tmp/test.jsonl",
        )
        assert result.total_messages == 0
        assert result.turns == []

    def test_corpus_config_defaults(self):
        config = CorpusConfig()
        assert config.default_model == "qwen2.5:7b"
        assert config.concurrency == 2

    def test_scenario_def(self):
        sd = ScenarioDef(
            id="test_scenario",
            description="A test",
            inject_at={"day_range": [3, 8], "count": 1},
            steps=[
                ScenarioStep(instruction="Do something"),
                ScenarioStep(instruction="Do another thing", delay_messages=[2, 5]),
            ],
        )
        assert len(sd.steps) == 2
        assert sd.steps[1].delay_messages == [2, 5]


class TestCorpusConfig:
    def test_load_corpus_config(self):
        config = load_corpus_config()
        assert config.default_model == "qwen2.5:7b"
        assert "tomoko" in config.persona_models
        assert "jaden" in config.hardcoded_messages
        assert "maya" in config.open_ended
        assert config.open_ended["diego"] == 0.35

    def test_load_all_scenarios(self):
        scenarios = load_all_scenarios()
        assert len(scenarios) > 0
        ids = {s.id for s in scenarios}
        assert "time_change" in ids
        assert "completion_reversal" in ids
        assert "wall_of_text" in ids
        assert "topic_resurrection" in ids


class TestNewPersonas:
    @pytest.mark.parametrize(
        "name",
        ["elena", "jaden", "tomoko", "diego", "ruth", "sam", "kwame"],
    )
    def test_persona_loads(self, name: str):
        persona = load_persona(name)
        assert persona.name
        assert persona.age > 0
        assert persona.background
        assert persona.simulation.duration_days == 90


class TestScenarioScheduling:
    def test_schedule_basic(self):
        import random

        scenario = ScenarioDef(
            id="test",
            description="test",
            inject_at={"day_range": [1, 10], "count": 1},
            steps=[ScenarioStep(instruction="do something")],
        )
        rng = random.Random(42)
        scheduled = schedule_scenarios([scenario], "maya", 30, rng)
        assert len(scheduled) == 1
        assert 1 <= scheduled[0].start_day <= 10

    def test_schedule_multiple_count(self):
        import random

        scenario = ScenarioDef(
            id="test",
            description="test",
            inject_at={"day_range": [1, 30], "count": 3},
            steps=[ScenarioStep(instruction="do something")],
        )
        rng = random.Random(42)
        scheduled = schedule_scenarios([scenario], "maya", 30, rng)
        assert len(scheduled) == 3

    def test_schedule_clamped_to_total_days(self):
        import random

        scenario = ScenarioDef(
            id="test",
            description="test",
            inject_at={"day_range": [80, 90], "count": 1},
            steps=[ScenarioStep(instruction="do something")],
        )
        rng = random.Random(42)
        scheduled = schedule_scenarios([scenario], "maya", 10, rng)
        # day_hi clamped to 10, day_lo 80 > 10, so no scheduling
        assert len(scheduled) == 0


class TestGeneration:
    @pytest.mark.asyncio
    async def test_generate_message_basic(self):
        persona = {"name": "Test", "age": 25, "background": "test persona"}
        with patch("graph_lab.src.llm.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "i need to buy groceries"
            state = {
                "day": 1,
                "energy": "medium",
                "mood": "neutral",
                "time_of_day": "morning",
            }
            result = await generate_message(
                persona,
                [],
                state,
                "qwen2.5:7b",
                0.9,
            )
            assert result == "i need to buy groceries"
            mock_gen.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_message_skip(self):
        with patch("graph_lab.src.llm.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "SKIP"
            state = {
                "day": 1,
                "energy": "low",
                "mood": "bad",
                "time_of_day": "morning",
            }
            result = await generate_message(
                {"name": "Test"},
                [],
                state,
                "qwen2.5:7b",
                0.9,
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_generate_message_with_injection(self):
        with patch("graph_lab.src.llm.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "meeting at 2pm thursday"
            result = await generate_message(
                {"name": "Test"},
                [],
                {"day": 3, "energy": "medium", "mood": "neutral", "time_of_day": "afternoon"},
                "qwen2.5:7b",
                0.9,
                scenario_instruction="Mention a meeting at 2pm on Thursday",
            )
            assert result == "meeting at 2pm thursday"
            # Verify injection was in the prompt
            call_args = mock_gen.call_args
            msgs = call_args.kwargs.get("messages", call_args[1].get("messages", [{}]))
            prompt_content = msgs[0]["content"]
            assert "IMPORTANT" in prompt_content
            assert "Mention a meeting" in prompt_content

    @pytest.mark.asyncio
    async def test_generate_message_open_ended(self):
        with patch("graph_lab.src.llm.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "just vibing honestly"
            result = await generate_message(
                {"name": "Sam", "age": 22, "background": "non-binary AuDHD"},
                ["checked my mushrooms this morning"],
                {"day": 5, "energy": "medium", "mood": "neutral", "time_of_day": "afternoon"},
                "qwen2.5:7b",
                0.9,
                open_ended=True,
            )
            assert result == "just vibing honestly"
            # Open-ended prompt should NOT contain the structured guidance list
            call_args = mock_gen.call_args
            prompt = call_args.kwargs.get("messages", call_args[1].get("messages", [{}]))[0][
                "content"
            ]
            assert "ADHD brain dumps are messy" not in prompt
            assert "Be completely natural" in prompt

    @pytest.mark.asyncio
    async def test_generate_message_strips_quotes(self):
        with patch("graph_lab.src.llm.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = '"hey can you remind me about the thing"'
            result = await generate_message(
                {"name": "Test"},
                [],
                {"day": 1, "energy": "medium", "mood": "neutral", "time_of_day": "morning"},
                "qwen2.5:7b",
                0.9,
            )
            assert result == "hey can you remind me about the thing"

    @pytest.mark.asyncio
    async def test_generate_persona_corpus(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            config = CorpusConfig(default_model="test-model", temperature=0.5)
            msg_counter = 0

            async def _mock_generate(messages, model=None, temperature=None):
                nonlocal msg_counter
                msg_counter += 1
                return f"test message {msg_counter}"

            with patch("graph_lab.corpus.generate.llm.generate", side_effect=_mock_generate):
                path = await generate_persona_corpus(
                    "maya",
                    3,
                    config,
                    [],
                    output_dir,
                    seed=42,
                )

            assert path.exists()
            lines = path.read_text().strip().split("\n")
            assert len(lines) > 0

            # Verify JSONL structure
            for line in lines:
                data = json.loads(line)
                assert "id" in data
                assert "persona" in data or "type" in data


class TestValidation:
    def test_validate_good_corpus(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            # Write valid corpus
            marker = DayMarker(id="test-d001-start", persona="test", day=1, skipped=False)
            f.write(marker.model_dump_json() + "\n")
            for i in range(3):
                msg = CorpusMessage(
                    id=f"test-d001-m{i:03d}",
                    persona="test",
                    day=1,
                    message_index=i,
                    time_of_day="morning",
                    energy="medium",
                    mood="neutral",
                    content=f"unique message number {i}",
                    scenario_tag=None,
                    generation_model="test-model",
                )
                f.write(msg.model_dump_json() + "\n")
            path = Path(f.name)

        report = validate_corpus_file(path)
        assert report["valid"] is True
        assert report["message_count"] == 3
        path.unlink()

    def test_validate_duplicate_messages(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for i in range(2):
                msg = CorpusMessage(
                    id=f"test-d001-m{i:03d}",
                    persona="test",
                    day=1,
                    message_index=i,
                    time_of_day="morning",
                    energy="medium",
                    mood="neutral",
                    content="same message repeated",
                    scenario_tag=None,
                    generation_model="test-model",
                )
                f.write(msg.model_dump_json() + "\n")
            path = Path(f.name)

        report = validate_corpus_file(path)
        assert report["valid"] is False
        assert any("Consecutive identical" in issue for issue in report["issues"])
        path.unlink()

    def test_validate_empty_corpus(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write("")
            path = Path(f.name)

        report = validate_corpus_file(path)
        assert report["valid"] is False
        assert report["message_count"] == 0
        path.unlink()

    def test_validate_corpus_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a valid corpus file
            path = Path(tmpdir) / "test.jsonl"
            with open(path, "w") as f:
                msg = CorpusMessage(
                    id="test-d001-m000",
                    persona="test",
                    day=1,
                    message_index=0,
                    time_of_day="morning",
                    energy="medium",
                    mood="neutral",
                    content="hello",
                    scenario_tag=None,
                    generation_model="test-model",
                )
                f.write(msg.model_dump_json() + "\n")

            reports = validate_corpus_dir(Path(tmpdir))
            assert len(reports) == 1
            assert reports[0]["valid"] is True
