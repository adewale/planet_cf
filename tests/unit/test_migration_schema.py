# tests/unit/test_migration_schema.py
"""Validate migrations against real SQLite — catches the exact bug class
that caused feeds to disappear (migration not applied → missing column
→ D1 errors → feeds auto-disabled).

Runs all migration files against an in-memory SQLite database and verifies
the resulting schema matches what _ensure_database_initialized() would produce.
"""

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "migrations"


def _get_expected_columns() -> dict[str, set[str]]:
    """Get expected columns from PlanetCF._EXPECTED_COLUMNS."""
    from main import PlanetCF

    return PlanetCF._EXPECTED_COLUMNS


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Run all migration SQL files against a SQLite connection."""
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sql = sql_file.read_text()
        # Use executescript which handles multi-statement SQL properly
        try:
            conn.executescript(sql)
        except sqlite3.OperationalError as e:
            # Allow "duplicate column" errors (idempotent migrations)
            if "duplicate column" not in str(e).lower():
                raise


def _get_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    """Get column names from a SQLite table."""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")  # noqa: S608
    return {row[1] for row in cursor.fetchall()}


class TestMigrationSchemaMatchesCode:
    """Verify that running all migrations produces the same schema as
    _ensure_database_initialized()."""

    def test_migrations_produce_expected_feeds_columns(self):
        """After all migrations, feeds table has all expected columns."""
        conn = sqlite3.connect(":memory:")
        _run_migrations(conn)
        actual = _get_table_columns(conn, "feeds")
        expected = _get_expected_columns()["feeds"]
        missing = expected - actual
        assert not missing, (
            f"Migrations don't produce all expected feeds columns.\n"
            f"Missing: {sorted(missing)}\n"
            f"This means a migration needs to be created or an ALTER TABLE is missing."
        )
        # Verify no unexpected extra columns crept in
        extra = actual - expected
        assert not extra, (
            f"Feeds table has unexpected columns not in _EXPECTED_COLUMNS: {sorted(extra)}"
        )
        # Verify critical columns exist individually
        assert "id" in actual
        assert "url" in actual
        assert "is_active" in actual
        assert "last_entry_at" in actual  # Added by migration 004

    def test_migrations_produce_expected_entries_columns(self):
        """After all migrations, entries table has all expected columns."""
        conn = sqlite3.connect(":memory:")
        _run_migrations(conn)
        actual = _get_table_columns(conn, "entries")
        expected = _get_expected_columns()["entries"]
        missing = expected - actual
        assert not missing, (
            f"Migrations don't produce all expected entries columns.\nMissing: {sorted(missing)}"
        )
        extra = actual - expected
        assert not extra, f"Entries table has unexpected columns: {sorted(extra)}"
        # Verify critical columns including the one added by migration 003
        assert "first_seen" in actual
        assert "feed_id" in actual
        assert "guid" in actual
        assert "published_at" in actual

    def test_migrations_produce_expected_admins_columns(self):
        """After all migrations, admins table has all expected columns."""
        conn = sqlite3.connect(":memory:")
        _run_migrations(conn)
        actual = _get_table_columns(conn, "admins")
        expected = _get_expected_columns()["admins"]
        missing = expected - actual
        assert not missing, (
            f"Migrations don't produce all expected admins columns.\nMissing: {sorted(missing)}"
        )
        extra = actual - expected
        assert not extra, f"Admins table has unexpected columns: {sorted(extra)}"
        assert "github_username" in actual
        assert "github_id" in actual
        assert "is_active" in actual

    def test_migrations_produce_expected_audit_log_columns(self):
        """After all migrations, audit_log table has all expected columns."""
        conn = sqlite3.connect(":memory:")
        _run_migrations(conn)
        actual = _get_table_columns(conn, "audit_log")
        expected = _get_expected_columns()["audit_log"]
        missing = expected - actual
        assert not missing, (
            f"Migrations don't produce all expected audit_log columns.\nMissing: {sorted(missing)}"
        )
        extra = actual - expected
        assert not extra, f"Audit_log table has unexpected columns: {sorted(extra)}"
        assert "action" in actual
        assert "admin_id" in actual
        assert "created_at" in actual

    def test_migrations_create_applied_migrations_table(self):
        """Migration 005 creates the applied_migrations tracking table."""
        conn = sqlite3.connect(":memory:")
        _run_migrations(conn)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='applied_migrations'"
        )
        assert cursor.fetchone() is not None, "applied_migrations table should exist"
        # Verify the table has the expected columns
        am_columns = _get_table_columns(conn, "applied_migrations")
        assert "id" in am_columns
        assert "migration_name" in am_columns
        assert "applied_at" in am_columns
        # Verify all 5 migrations are seeded as applied
        cursor = conn.execute("SELECT COUNT(*) FROM applied_migrations")
        count = cursor.fetchone()[0]
        assert count == 5, f"Expected 5 seeded migrations, got {count}"

    def test_migrations_are_idempotent(self):
        """Running all migrations twice should not error."""
        conn = sqlite3.connect(":memory:")
        _run_migrations(conn)
        # Capture schema after first run
        tables_before = set()
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables_before = {row[0] for row in cursor.fetchall()}
        cols_before = {t: _get_table_columns(conn, t) for t in tables_before}
        # Second run should succeed (idempotent)
        _run_migrations(conn)
        # Schema should be identical after second run
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables_after = {row[0] for row in cursor.fetchall()}
        assert tables_before == tables_after, "Tables changed after idempotent re-run"
        for table in tables_before:
            cols_after = _get_table_columns(conn, table)
            assert cols_before[table] == cols_after, (
                f"Columns in {table} changed after idempotent re-run"
            )

    def test_expected_columns_match_migrated_db(self):
        """_EXPECTED_COLUMNS must be a superset of migration schema.

        This catches the case where code adds a column to _EXPECTED_COLUMNS
        but forgets to create a migration for existing databases.
        """
        expected = _get_expected_columns()

        # Compare with migration output
        conn = sqlite3.connect(":memory:")
        _run_migrations(conn)

        for table_name, expected_cols in expected.items():
            migrated_cols = _get_table_columns(conn, table_name)
            in_expected_not_migrated = expected_cols - migrated_cols
            assert not in_expected_not_migrated, (
                f"Table '{table_name}': columns {sorted(in_expected_not_migrated)} exist in "
                f"_EXPECTED_COLUMNS but NOT after running migrations. "
                f"A new migration is needed."
            )
            # Also check the reverse: migrations shouldn't add columns unknown to code
            in_migrated_not_expected = migrated_cols - expected_cols
            assert not in_migrated_not_expected, (
                f"Table '{table_name}': columns {sorted(in_migrated_not_expected)} exist "
                f"after migrations but NOT in _EXPECTED_COLUMNS. "
                f"Update _EXPECTED_COLUMNS or remove the migration column."
            )
        # Verify all expected tables are covered
        assert set(expected.keys()) == {"feeds", "entries", "admins", "audit_log"}
