"""Tests that the migration SQL file is valid and contains expected statements."""

from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "supabase" / "migrations"


class TestMigration00003:
    def test_file_exists(self) -> None:
        path = MIGRATIONS_DIR / "00003_config_hash_and_ttft.sql"
        assert path.exists()

    def test_adds_config_hash_column(self) -> None:
        path = MIGRATIONS_DIR / "00003_config_hash_and_ttft.sql"
        sql = path.read_text()
        assert "config_hash" in sql
        assert "ALTER TABLE llm_usage" in sql

    def test_adds_ttft_ms_column(self) -> None:
        path = MIGRATIONS_DIR / "00003_config_hash_and_ttft.sql"
        sql = path.read_text()
        assert "ttft_ms" in sql

    def test_creates_trace_summary_view(self) -> None:
        path = MIGRATIONS_DIR / "00003_config_hash_and_ttft.sql"
        sql = path.read_text()
        assert "trace_summary" in sql
        assert "CREATE" in sql
        assert "VIEW" in sql

    def test_view_aggregates_correctly(self) -> None:
        path = MIGRATIONS_DIR / "00003_config_hash_and_ttft.sql"
        sql = path.read_text()
        assert "SUM(input_tokens)" in sql
        assert "SUM(output_tokens)" in sql
        assert "MIN(ttft_ms)" in sql
        assert "array_agg" in sql
        assert "GROUP BY" in sql
