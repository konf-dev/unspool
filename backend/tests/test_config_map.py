"""Tests for the config map generator script."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestConfigMapGenerator:
    def test_script_runs_successfully(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "scripts.config_map"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert "Generated" in result.stdout

    def test_output_file_created(self) -> None:
        subprocess.run(
            [sys.executable, "-m", "scripts.config_map"],
            cwd=ROOT,
            capture_output=True,
        )
        output = ROOT.parent / "docs" / "CONFIG_MAP.md"
        assert output.exists()
        content = output.read_text()
        assert "# Config Map" in content
        assert "auto-generated" in content

    def test_all_intents_present(self) -> None:
        subprocess.run(
            [sys.executable, "-m", "scripts.config_map"],
            cwd=ROOT,
            capture_output=True,
        )
        output = ROOT.parent / "docs" / "CONFIG_MAP.md"
        content = output.read_text()
        expected_intents = [
            "brain_dump",
            "conversation",
            "emotional",
            "meta",
            "onboarding",
            "query_next",
            "query_search",
            "query_upcoming",
            "status_cant",
            "status_done",
        ]
        for intent in expected_intents:
            assert f"## {intent}" in content, f"Missing intent: {intent}"

    def test_hashes_are_hex(self) -> None:
        subprocess.run(
            [sys.executable, "-m", "scripts.config_map"],
            cwd=ROOT,
            capture_output=True,
        )
        output = ROOT.parent / "docs" / "CONFIG_MAP.md"
        content = output.read_text()
        # Find hash patterns like (abc123def456)
        import re

        hashes = re.findall(r"\(([0-9a-f]{12})\)", content)
        assert len(hashes) > 10, "Expected many hashes in output"

    def test_unreferenced_prompts_section(self) -> None:
        subprocess.run(
            [sys.executable, "-m", "scripts.config_map"],
            cwd=ROOT,
            capture_output=True,
        )
        output = ROOT.parent / "docs" / "CONFIG_MAP.md"
        content = output.read_text()
        # system.md and classify_intent.md are not referenced by pipelines
        assert "Unreferenced Prompts" in content
        assert "system.md" in content
        assert "classify_intent.md" in content

    def test_config_files_section(self) -> None:
        subprocess.run(
            [sys.executable, "-m", "scripts.config_map"],
            cwd=ROOT,
            capture_output=True,
        )
        output = ROOT.parent / "docs" / "CONFIG_MAP.md"
        content = output.read_text()
        assert "## Config Files" in content
        assert "intents.yaml" in content
        assert "scoring.yaml" in content

    def test_context_rules_shown(self) -> None:
        subprocess.run(
            [sys.executable, "-m", "scripts.config_map"],
            cwd=ROOT,
            capture_output=True,
        )
        output = ROOT.parent / "docs" / "CONFIG_MAP.md"
        content = output.read_text()
        # brain_dump should show its context rules
        assert "profile, recent_messages" in content
