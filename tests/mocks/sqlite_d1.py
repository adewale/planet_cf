# tests/mocks/sqlite_d1.py
"""D1 test double backed by a real SQLite engine, with the schema from migrations/.

D1 is SQLite. Tests that need to know what a query *does* (which rows it selects,
updates or deletes) should run it here instead of against ``MockD1`` in
``tests/conftest.py``, which picks a table by regex, filters only on
``is_active = N``, ignores ``LIMIT``/``ORDER BY`` and discards every UPDATE/DELETE.

Fidelity to D1 (https://developers.cloudflare.com/d1/sql-api/foreign-keys/):
foreign keys are enforced, as D1 does by default. ``first()`` returns a row dict
or None, ``all()`` returns ``.results``/``.success``/``.meta``, ``run()`` reports
``meta["changes"]``. Results are plain dicts; JsProxy behaviour is covered by
``tests/unit/test_wrappers_ffi.py``, not here.
"""

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@dataclass
class SQLiteD1Result:
    results: list[dict[str, Any]]
    success: bool = True
    meta: dict[str, Any] = field(default_factory=dict)


class SQLiteD1Statement:
    def __init__(self, conn: sqlite3.Connection, sql: str):
        self._conn = conn
        self._sql = sql
        self._params: tuple = ()

    def bind(self, *args: Any) -> "SQLiteD1Statement":
        self._params = args
        return self

    def _execute(self) -> SQLiteD1Result:
        with self._conn:
            cursor = self._conn.execute(self._sql, self._params)
            rows = [dict(row) for row in cursor.fetchall()] if cursor.description else []
        return SQLiteD1Result(
            results=rows,
            meta={"changes": max(cursor.rowcount, 0), "last_row_id": cursor.lastrowid},
        )

    async def all(self) -> SQLiteD1Result:
        return self._execute()

    async def first(self) -> dict[str, Any] | None:
        rows = self._execute().results
        return rows[0] if rows else None

    async def run(self) -> SQLiteD1Result:
        return self._execute()


class SQLiteD1:
    """In-memory SQLite database exposing the D1 binding API used by src/."""

    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    @classmethod
    def from_migrations(cls) -> "SQLiteD1":
        """A database in the state production reaches after every migration."""
        db = cls()
        for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            db.conn.executescript(sql_file.read_text())
        return db

    def prepare(self, sql: str) -> SQLiteD1Statement:
        return SQLiteD1Statement(self.conn, sql)

    async def exec(self, sql: str) -> SQLiteD1Result:
        self.conn.executescript(sql)
        return SQLiteD1Result(results=[])

    # Test helpers: read and seed state directly, bypassing the code under test.

    def rows(self, sql: str, *params: Any) -> list[dict[str, Any]]:
        return [dict(row) for row in self.conn.execute(sql, params).fetchall()]

    def insert(self, table: str, **values: Any) -> int:
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        with self.conn:
            cursor = self.conn.execute(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",  # noqa: S608
                tuple(values.values()),
            )
        return cursor.lastrowid
