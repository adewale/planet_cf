# tests/unit/test_schema_consistency.py
"""
Schema-to-Query Consistency Tests.

Verifies that all column names referenced in SQL queries (INSERT, UPDATE, SELECT)
exist in the corresponding CREATE TABLE schema defined in _ensure_database_initialized().

This test would have caught the missing `last_entry_at` column bug (C2) where a query
referenced a column that didn't exist in the schema.
"""

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "migrations"


def _get_expected_columns() -> dict[str, set[str]]:
    """Get expected columns from PlanetCF._EXPECTED_COLUMNS."""
    from main import PlanetCF

    return PlanetCF._EXPECTED_COLUMNS


def _run_migrations_and_get_columns() -> dict[str, set[str]]:
    """Run all migration SQL files and return actual column names per table."""
    conn = sqlite3.connect(":memory:")
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sql = sql_file.read_text()
        try:
            conn.executescript(sql)
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e).lower():
                raise

    tables: dict[str, set[str]] = {}
    for table_name in ("feeds", "entries", "admins", "audit_log"):
        cursor = conn.execute(f"PRAGMA table_info({table_name})")  # noqa: S608
        columns = {row[1] for row in cursor.fetchall()}
        if columns:
            tables[table_name] = columns
    conn.close()
    return tables


class TestSchemaConsistency:
    """Verify that the schema (via migrations and _EXPECTED_COLUMNS) is consistent.

    Uses behavioral testing: runs migrations against SQLite and compares
    actual column names to _EXPECTED_COLUMNS, rather than parsing source code.
    """

    def test_schema_has_required_tables(self):
        """Verify migrations produce all required tables."""
        tables = _run_migrations_and_get_columns()

        assert "feeds" in tables, "Should find feeds table in schema"
        assert "entries" in tables, "Should find entries table in schema"
        assert "admins" in tables, "Should find admins table in schema"
        assert "audit_log" in tables, "Should find audit_log table in schema"

        # Verify key columns exist
        assert "url" in tables["feeds"], "feeds table should have 'url' column"
        assert "title" in tables["feeds"], "feeds table should have 'title' column"
        assert "guid" in tables["entries"], "entries table should have 'guid' column"
        assert "github_username" in tables["admins"], "admins table should have 'github_username'"

    def test_feeds_columns_match_expected(self):
        """Migrated feeds columns must match _EXPECTED_COLUMNS['feeds']."""
        expected = _get_expected_columns()
        actual = _run_migrations_and_get_columns()

        missing = expected["feeds"] - actual["feeds"]
        assert not missing, (
            f"Migrations don't produce all expected feeds columns.\n"
            f"Missing: {sorted(missing)}\n"
            f"Schema columns: {sorted(actual['feeds'])}"
        )

    def test_entries_columns_match_expected(self):
        """Migrated entries columns must match _EXPECTED_COLUMNS['entries']."""
        expected = _get_expected_columns()
        actual = _run_migrations_and_get_columns()

        missing = expected["entries"] - actual["entries"]
        assert not missing, (
            f"Migrations don't produce all expected entries columns.\n"
            f"Missing: {sorted(missing)}\n"
            f"Schema columns: {sorted(actual['entries'])}"
        )

    def test_admins_columns_match_expected(self):
        """Migrated admins columns must match _EXPECTED_COLUMNS['admins']."""
        expected = _get_expected_columns()
        actual = _run_migrations_and_get_columns()

        missing = expected["admins"] - actual["admins"]
        assert not missing, (
            f"Migrations don't produce all expected admins columns.\n"
            f"Missing: {sorted(missing)}\n"
            f"Schema columns: {sorted(actual['admins'])}"
        )

    def test_audit_log_columns_match_expected(self):
        """Migrated audit_log columns must match _EXPECTED_COLUMNS['audit_log']."""
        expected = _get_expected_columns()
        actual = _run_migrations_and_get_columns()

        missing = expected["audit_log"] - actual["audit_log"]
        assert not missing, (
            f"Migrations don't produce all expected audit_log columns.\n"
            f"Missing: {sorted(missing)}\n"
            f"Schema columns: {sorted(actual['audit_log'])}"
        )

    def test_last_entry_at_exists_in_feeds_schema(self):
        """Regression test: last_entry_at must exist in feeds schema.

        This column was missing in an earlier version (C2 bug), causing
        UPDATE feeds SET last_entry_at = ... to fail at runtime.
        """
        actual = _run_migrations_and_get_columns()

        assert "last_entry_at" in actual["feeds"], (
            "feeds table must have 'last_entry_at' column. "
            "This was the C2 bug: queries referenced last_entry_at but the "
            "CREATE TABLE was missing it."
        )

    def test_feeds_schema_has_all_expected_columns(self):
        """Verify the feeds table has all columns we know are needed."""
        actual = _run_migrations_and_get_columns()

        expected = {
            "id",
            "url",
            "title",
            "site_url",
            "author_name",
            "author_email",
            "etag",
            "last_modified",
            "last_fetch_at",
            "last_success_at",
            "last_entry_at",
            "fetch_error",
            "fetch_error_count",
            "consecutive_failures",
            "is_active",
            "created_at",
            "updated_at",
        }

        missing = expected - actual["feeds"]
        assert not missing, (
            f"feeds table is missing expected columns: {sorted(missing)}. "
            f"Actual columns: {sorted(actual['feeds'])}"
        )

    def test_entries_schema_has_all_expected_columns(self):
        """Verify the entries table has all columns we know are needed."""
        actual = _run_migrations_and_get_columns()

        expected = {
            "id",
            "feed_id",
            "guid",
            "url",
            "title",
            "author",
            "content",
            "summary",
            "published_at",
            "updated_at",
            "first_seen",
            "created_at",
        }

        missing = expected - actual["entries"]
        assert not missing, (
            f"entries table is missing expected columns: {sorted(missing)}. "
            f"Actual columns: {sorted(actual['entries'])}"
        )

    def test_runtime_expected_columns_match_migration_schema(self):
        """_EXPECTED_COLUMNS in PlanetCF must match the migration-produced schema.

        The runtime schema drift check uses _EXPECTED_COLUMNS to detect
        missing columns in production. If this dict drifts from the actual
        migration-produced schema, the check becomes ineffective.
        """
        expected = _get_expected_columns()
        actual = _run_migrations_and_get_columns()

        for table_name, expected_cols in expected.items():
            actual_cols = actual.get(table_name, set())
            assert expected_cols == actual_cols, (
                f"_EXPECTED_COLUMNS['{table_name}'] does not match migration schema.\n"
                f"  In _EXPECTED_COLUMNS but not in migrations: {sorted(expected_cols - actual_cols)}\n"
                f"  In migrations but not in _EXPECTED_COLUMNS: {sorted(actual_cols - expected_cols)}"
            )
