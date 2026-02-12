# tests/unit/test_migration_schema.py
"""Validate migrations against real SQLite — catches the exact bug class
that caused feeds to disappear (migration not applied → missing column
→ D1 errors → feeds auto-disabled).

Runs all migration files against an in-memory SQLite database and verifies
the resulting schema matches what _ensure_database_initialized() would produce.
"""

import re
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

    def test_migrations_create_applied_migrations_table(self):
        """Migration 005 creates the applied_migrations tracking table."""
        conn = sqlite3.connect(":memory:")
        _run_migrations(conn)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='applied_migrations'"
        )
        assert cursor.fetchone() is not None, "applied_migrations table should exist"

    def test_migrations_are_idempotent(self):
        """Running all migrations twice should not error."""
        conn = sqlite3.connect(":memory:")
        _run_migrations(conn)
        # Second run should succeed (idempotent)
        _run_migrations(conn)

    def test_fresh_db_matches_migrated_db(self):
        """_ensure_database_initialized schema must be a superset of migration schema.

        This catches the case where code adds a column to _ensure_database_initialized
        but forgets to create a migration for existing databases.
        """
        import inspect

        from main import Default

        # Get columns from _ensure_database_initialized CREATE TABLE
        source = inspect.getsource(Default._ensure_database_initialized)

        create_pattern = re.compile(
            r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)\s*\((.*?)\);",
            re.DOTALL | re.IGNORECASE,
        )

        fresh_schema: dict[str, set[str]] = {}
        for match in create_pattern.finditer(source):
            table_name = match.group(1)
            body = match.group(2)
            columns = set()
            for line in body.split("\n"):
                line = line.strip().rstrip(",")
                if not line:
                    continue
                if re.match(
                    r"^\s*(FOREIGN\s+KEY|UNIQUE|PRIMARY\s+KEY\s*\(|CHECK)",
                    line,
                    re.IGNORECASE,
                ):
                    continue
                col_match = re.match(r"^(\w+)\s+", line)
                if col_match:
                    col_name = col_match.group(1).lower()
                    skip = {"create", "table", "if", "not", "exists", "foreign", "unique"}
                    if col_name not in skip:
                        columns.add(col_name)
            fresh_schema[table_name] = columns

        # Compare with migration output
        conn = sqlite3.connect(":memory:")
        _run_migrations(conn)

        for table_name, fresh_cols in fresh_schema.items():
            if table_name == "applied_migrations":
                continue  # Tracking table
            migrated_cols = _get_table_columns(conn, table_name)
            in_fresh_not_migrated = fresh_cols - migrated_cols
            assert not in_fresh_not_migrated, (
                f"Table '{table_name}': columns {sorted(in_fresh_not_migrated)} exist in "
                f"_ensure_database_initialized but NOT after running migrations. "
                f"A new migration is needed."
            )
