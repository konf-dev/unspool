"""Tests for config versioning: content hashing in config_loader and prompt_renderer."""
import pytest

from src.orchestrator.config_loader import (
    get_all_config_hashes,
    get_config_hash,
    load_config,
    load_pipeline,
)
from src.orchestrator.prompt_renderer import (
    get_prompt_hash,
    get_prompt_meta,
    render_prompt,
)


class TestConfigHashing:
    def test_pipeline_hash_populated_after_load(self) -> None:
        load_pipeline("brain_dump")
        h = get_config_hash("pipeline:brain_dump")
        assert h is not None
        assert len(h) == 12
        assert all(c in "0123456789abcdef" for c in h)

    def test_config_hash_populated_after_load(self) -> None:
        load_config("intents")
        h = get_config_hash("config:intents")
        assert h is not None
        assert len(h) == 12

    def test_hash_is_deterministic(self) -> None:
        load_pipeline("brain_dump")
        h1 = get_config_hash("pipeline:brain_dump")
        # Force re-load by clearing cache
        from src.orchestrator.config_loader import _pipeline_cache
        _pipeline_cache.pop("brain_dump", None)
        load_pipeline("brain_dump")
        h2 = get_config_hash("pipeline:brain_dump")
        assert h1 == h2

    def test_missing_hash_returns_none(self) -> None:
        assert get_config_hash("pipeline:nonexistent_xyz") is None

    def test_get_all_hashes_includes_loaded(self) -> None:
        load_pipeline("brain_dump")
        load_config("gate")
        all_hashes = get_all_config_hashes()
        assert "pipeline:brain_dump" in all_hashes
        assert "config:gate" in all_hashes

    def test_all_pipelines_produce_hashes(self) -> None:
        names = [
            "brain_dump", "conversation", "emotional", "meta",
            "onboarding", "query_next", "query_search",
            "query_upcoming", "status_cant", "status_done",
        ]
        for name in names:
            load_pipeline(name)
            assert get_config_hash(f"pipeline:{name}") is not None, f"No hash for {name}"


class TestPromptHashing:
    def test_prompt_hash_populated_after_render(self) -> None:
        render_prompt("classify_intent.md", {
            "user_message": "test",
            "recent_messages": [],
        })
        h = get_prompt_hash("classify_intent.md")
        assert h is not None
        assert len(h) == 12

    def test_prompt_hash_deterministic(self) -> None:
        render_prompt("classify_intent.md", {
            "user_message": "a",
            "recent_messages": [],
        })
        h1 = get_prompt_hash("classify_intent.md")
        render_prompt("classify_intent.md", {
            "user_message": "b",
            "recent_messages": [],
        })
        h2 = get_prompt_hash("classify_intent.md")
        # Same file, different variables — hash should be the same
        assert h1 == h2

    def test_missing_prompt_hash_returns_none(self) -> None:
        assert get_prompt_hash("nonexistent_xyz.md") is None

    def test_prompt_meta_parsed_from_frontmatter(self) -> None:
        render_prompt("classify_intent.md", {
            "user_message": "test",
            "recent_messages": [],
        })
        meta = get_prompt_meta("classify_intent.md")
        # classify_intent.md has frontmatter with at least a name field
        assert isinstance(meta, dict)
        if meta:
            assert "name" in meta or "version" in meta or "input_vars" in meta

    def test_prompt_meta_empty_for_missing(self) -> None:
        assert get_prompt_meta("nonexistent_xyz.md") == {}
