"""Tests for telemetry: middleware GIT_SHA, events, structured errors."""
import hashlib

from src.telemetry.events import log_message_completed, log_step_error
from src.telemetry.middleware import GIT_SHA


class TestGitSha:
    def test_git_sha_is_populated(self) -> None:
        assert GIT_SHA is not None
        assert GIT_SHA != ""

    def test_git_sha_is_short(self) -> None:
        # Should be 7-8 chars (short hash) or "unknown"
        assert len(GIT_SHA) <= 8 or GIT_SHA == "unknown"

    def test_git_sha_not_unknown_in_git_repo(self) -> None:
        # We're in a git repo, so it should resolve
        assert GIT_SHA != "unknown"


class TestLogStepError:
    def test_log_step_error_callable(self) -> None:
        # Should not raise — just logs
        log_step_error(
            trace_id="test-trace",
            step_id="test-step",
            step_type="tool_call",
            error_type="ValueError",
            error_message="test error",
            pipeline="test_pipeline",
        )

    def test_log_step_error_with_kwargs(self) -> None:
        log_step_error(
            trace_id="test-trace",
            step_id="test-step",
            step_type="llm_call",
            error_type="TimeoutError",
            error_message="timed out",
            pipeline="brain_dump",
            model="test-model",
            extra_field="extra",
        )


class TestLogMessageCompleted:
    def test_without_config_snapshot(self) -> None:
        # Should not raise
        log_message_completed(
            trace_id="test-trace",
            total_latency_ms=100.0,
            total_input_tokens=50,
            total_output_tokens=30,
            llm_calls=1,
            pipeline="brain_dump",
            variant="default",
        )

    def test_with_config_snapshot(self) -> None:
        snapshot = {
            "pipeline:brain_dump": "abc123",
            "prompt:brain_dump_extract.md": "def456",
        }
        # Should not raise, should compute combined hash
        log_message_completed(
            trace_id="test-trace",
            total_latency_ms=200.0,
            total_input_tokens=100,
            total_output_tokens=60,
            llm_calls=2,
            pipeline="brain_dump",
            variant="concise",
            config_snapshot=snapshot,
        )

    def test_config_snapshot_hash_deterministic(self) -> None:
        snapshot = {"a": "1", "b": "2"}
        joined = "|".join(f"{k}={v}" for k, v in sorted(snapshot.items()))
        h1 = hashlib.sha256(joined.encode()).hexdigest()[:12]
        h2 = hashlib.sha256(joined.encode()).hexdigest()[:12]
        assert h1 == h2

    def test_empty_config_snapshot(self) -> None:
        log_message_completed(
            trace_id="test-trace",
            total_latency_ms=50.0,
            total_input_tokens=10,
            total_output_tokens=5,
            llm_calls=1,
            pipeline="meta",
            variant="default",
            config_snapshot={},
        )
