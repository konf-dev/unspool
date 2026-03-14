"""Tests for post-processing dispatch flow — engine sets jobs, chat.py dispatches."""
import pytest

from src.orchestrator.types import Context, PostProcessingJob


class TestContextPostProcessing:
    def test_context_defaults_to_none(self) -> None:
        ctx = Context(user_id="u1", trace_id="t1", user_message="hello")
        assert ctx.post_processing_jobs is None

    def test_context_accepts_post_processing_jobs(self) -> None:
        jobs = [PostProcessingJob(job="process_conversation", delay="10s")]
        ctx = Context(
            user_id="u1", trace_id="t1", user_message="hello",
            post_processing_jobs=jobs,
        )
        assert len(ctx.post_processing_jobs) == 1
        assert ctx.post_processing_jobs[0].job == "process_conversation"
        assert ctx.post_processing_jobs[0].delay == "10s"


class TestJobsConfig:
    def test_jobs_yaml_loads(self) -> None:
        from src.orchestrator.config_loader import load_config
        config = load_config("jobs")
        assert "cron_jobs" in config
        assert "dispatch_map" in config

    def test_cron_jobs_have_required_fields(self) -> None:
        from src.orchestrator.config_loader import load_config
        config = load_config("jobs")
        for job_name, job_def in config["cron_jobs"].items():
            assert "schedule" in job_def, f"Job {job_name} missing schedule"
            assert "schedule_id" in job_def, f"Job {job_name} missing schedule_id"

    def test_all_cron_schedule_ids_unique(self) -> None:
        from src.orchestrator.config_loader import load_config
        config = load_config("jobs")
        ids = [j["schedule_id"] for j in config["cron_jobs"].values()]
        assert len(ids) == len(set(ids)), "Duplicate schedule_id values"

    def test_dispatch_map_contains_process_conversation(self) -> None:
        from src.orchestrator.config_loader import load_config
        config = load_config("jobs")
        assert "process_conversation" in config["dispatch_map"]
        assert config["dispatch_map"]["process_conversation"] == "process-conversation"

    def test_cron_expressions_valid_format(self) -> None:
        """Cron expressions should have 5 space-separated fields."""
        from src.orchestrator.config_loader import load_config
        config = load_config("jobs")
        for job_name, job_def in config["cron_jobs"].items():
            parts = job_def["schedule"].split()
            assert len(parts) == 5, (
                f"Job {job_name} cron '{job_def['schedule']}' should have 5 fields"
            )


class TestPipelinePostProcessing:
    def test_brain_dump_has_post_processing(self) -> None:
        from src.orchestrator.config_loader import load_pipeline
        pipeline = load_pipeline("brain_dump")
        assert pipeline.post_processing is not None
        assert len(pipeline.post_processing) > 0
        assert pipeline.post_processing[0].job == "process_conversation"

    def test_meta_has_no_post_processing(self) -> None:
        from src.orchestrator.config_loader import load_pipeline
        pipeline = load_pipeline("meta")
        assert pipeline.post_processing is None

    def test_post_processing_delay_is_string(self) -> None:
        from src.orchestrator.config_loader import load_pipeline
        pipeline = load_pipeline("brain_dump")
        for job in pipeline.post_processing:
            assert isinstance(job.delay, str), f"Job {job.job} delay should be a string"
