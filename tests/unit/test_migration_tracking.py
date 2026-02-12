"""Tests for migration tracking infrastructure.

Ensures migration files are properly numbered, the tracking table exists,
and the deployment script will catch migration failures.
"""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestMigrationFiles:
    """Verify migration files are well-structured."""

    def test_migration_files_sequentially_numbered(self):
        """Migration files must be sequentially numbered with no gaps."""
        migrations_dir = PROJECT_ROOT / "migrations"
        assert migrations_dir.exists(), "migrations/ directory not found"

        sql_files = sorted(migrations_dir.glob("*.sql"))
        assert len(sql_files) > 0, "No migration files found"

        expected_num = 1
        for sql_file in sql_files:
            name = sql_file.name
            num = int(name.split("_")[0])
            assert num == expected_num, (
                f"Gap in migration numbering: expected {expected_num:03d}_*, found {name}"
            )
            expected_num = num + 1

    def test_migration_005_creates_tracking_table(self):
        """Migration 005 should create the applied_migrations table."""
        migration = PROJECT_ROOT / "migrations" / "005_create_applied_migrations.sql"
        assert migration.exists(), "migrations/005_create_applied_migrations.sql not found"

        content = migration.read_text()
        assert "CREATE TABLE" in content
        assert "applied_migrations" in content
        assert "migration_name" in content

    def test_migration_005_seeds_all_migrations(self):
        """Migration 005 should seed entries for all existing migrations."""
        migration = PROJECT_ROOT / "migrations" / "005_create_applied_migrations.sql"
        content = migration.read_text()

        # Check each migration file is seeded
        migrations_dir = PROJECT_ROOT / "migrations"
        for sql_file in sorted(migrations_dir.glob("*.sql")):
            assert sql_file.name in content, (
                f"Migration 005 should seed '{sql_file.name}' into applied_migrations"
            )


class TestEnsureDbInitIncludesTracking:
    """Verify _ensure_database_initialized creates the tracking table."""

    def test_applied_migrations_in_schema(self):
        """The inline schema in _ensure_database_initialized must include applied_migrations."""
        source = (PROJECT_ROOT / "src" / "main.py").read_text()

        # Find the _ensure_database_initialized method
        match = re.search(
            r"async def _ensure_database_initialized.*?self\._db_initialized = True",
            source,
            re.DOTALL,
        )
        assert match, "Could not find _ensure_database_initialized"
        method_source = match.group()

        assert "applied_migrations" in method_source, (
            "_ensure_database_initialized must CREATE TABLE applied_migrations "
            "so fresh databases also have migration tracking"
        )


class TestDeployScriptBlocksOnFailure:
    """Verify deploy_instance.sh fails on migration errors."""

    def test_deploy_script_exits_on_migration_failure(self):
        """deploy_instance.sh should abort if a migration fails."""
        script = (PROJECT_ROOT / "scripts" / "deploy_instance.sh").read_text()

        assert "FAILED_MIGRATIONS" in script, "Deploy script should track failed migrations"
        assert "Aborting deployment" in script, "Deploy script should abort on migration failure"
        assert "exit 1" in script, "Deploy script should exit with error code on migration failure"

    def test_deploy_script_allows_already_applied(self):
        """deploy_instance.sh should allow 'already exists' errors (idempotent)."""
        script = (PROJECT_ROOT / "scripts" / "deploy_instance.sh").read_text()

        assert "already exists" in script.lower() or "duplicate column" in script.lower(), (
            "Deploy script should handle 'already exists' errors gracefully"
        )
