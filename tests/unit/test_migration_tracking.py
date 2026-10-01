"""Tests for migration tracking infrastructure.

Ensures migration files are properly numbered, the tracking table exists,
and the deployment script will catch migration failures.
"""

from pathlib import Path

from tests.conftest import MockEnv, MockQueue
from tests.mocks.sqlite_d1 import SQLiteD1

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

    def test_every_migration_is_recorded_in_applied_migrations(self):
        """After all migrations run, applied_migrations lists every migration file.

        Runs the SQL on SQLite, so a seed row that is commented out or fails to
        insert is caught, which a text search of 005 would miss.
        """
        db = SQLiteD1.from_migrations()

        recorded = {r["migration_name"] for r in db.rows("SELECT * FROM applied_migrations")}

        assert recorded == {f.name for f in (PROJECT_ROOT / "migrations").glob("*.sql")}


def _table_columns(db: SQLiteD1) -> dict[str, set[str]]:
    tables = [r["name"] for r in db.rows("SELECT name FROM sqlite_master WHERE type = 'table'")]
    return {
        t: {c["name"] for c in db.rows(f"PRAGMA table_info({t})")}  # noqa: S608
        for t in tables
        if t != "sqlite_sequence"
    }


class TestEnsureDbInitIncludesTracking:
    """_ensure_database_initialized builds a fresh database equivalent to the migrations."""

    async def test_fresh_database_gets_the_migrated_schema(self):
        """On an empty database, auto-init creates the same tables and columns as
        running every migration, including applied_migrations."""
        from src.main import PlanetCF

        empty = SQLiteD1()
        worker = PlanetCF()
        worker.env = MockEnv(
            DB=empty,
            FEED_QUEUE=MockQueue(),
            DEAD_LETTER_QUEUE=MockQueue(),
            SEARCH_INDEX=None,
            AI=None,
        )

        await worker._ensure_database_initialized()

        assert _table_columns(empty) == _table_columns(SQLiteD1.from_migrations())


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
