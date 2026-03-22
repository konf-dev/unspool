"""Tests that the migration SQL file is valid and contains expected statements."""

from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "supabase" / "migrations"
SCHEMA_PATH = MIGRATIONS_DIR / "00001_full_schema.sql"


class TestFullSchema:
    def test_file_exists(self) -> None:
        assert SCHEMA_PATH.exists()

    def test_creates_core_tables(self) -> None:
        sql = SCHEMA_PATH.read_text()
        for table in [
            "user_profiles",
            "messages",
            "items",
            "item_events",
            "memories",
            "entities",
            "recurrences",
            "calendar_events",
            "subscriptions",
            "push_subscriptions",
            "llm_usage",
            "experiment_assignments",
            "oauth_tokens",
        ]:
            assert f"CREATE TABLE {table}" in sql, f"Missing table: {table}"

    def test_creates_graph_tables(self) -> None:
        sql = SCHEMA_PATH.read_text()
        assert "CREATE TABLE memory_nodes" in sql
        assert "CREATE TABLE memory_edges" in sql
        assert "CREATE TABLE node_neighbors" in sql

    def test_graph_uses_halfvec(self) -> None:
        sql = SCHEMA_PATH.read_text()
        assert "halfvec(1536)" in sql
        assert "halfvec_cosine_ops" in sql

    def test_enables_rls_on_all_tables(self) -> None:
        sql = SCHEMA_PATH.read_text()
        for table in [
            "user_profiles",
            "messages",
            "items",
            "memories",
            "memory_nodes",
            "memory_edges",
            "node_neighbors",
        ]:
            assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in sql, (
                f"Missing RLS on: {table}"
            )

    def test_creates_trace_summary_view(self) -> None:
        sql = SCHEMA_PATH.read_text()
        assert "trace_summary" in sql
        assert "SUM(input_tokens)" in sql
        assert "MIN(ttft_ms)" in sql

    def test_config_hash_and_ttft_columns(self) -> None:
        sql = SCHEMA_PATH.read_text()
        assert "config_hash" in sql
        assert "ttft_ms" in sql

    def test_migration_files_sequential(self) -> None:
        files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        assert len(files) >= 1
        assert files[0].name == "00001_full_schema.sql"
        # Verify sequential numbering
        for i, f in enumerate(files):
            expected_prefix = f"{i + 1:05d}_"
            assert f.name.startswith(expected_prefix), (
                f"Migration {f.name} doesn't follow sequential numbering"
            )
