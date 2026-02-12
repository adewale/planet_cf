# tests/unit/test_schema_consistency.py
"""
Schema-to-Query Consistency Tests.

Verifies that all column names referenced in SQL queries (INSERT, UPDATE, SELECT)
exist in the corresponding CREATE TABLE schema defined in _ensure_database_initialized().

This test would have caught the missing `last_entry_at` column bug (C2) where a query
referenced a column that didn't exist in the schema.
"""

import inspect
import re


def _extract_create_table_columns(sql: str) -> dict[str, list[str]]:
    """Extract column names from CREATE TABLE statements.

    Args:
        sql: Multi-statement SQL string containing CREATE TABLE statements

    Returns:
        Dict mapping table name to list of column names
    """
    tables: dict[str, list[str]] = {}

    # Find all CREATE TABLE statements
    create_pattern = re.compile(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)\s*\((.*?)\);",
        re.DOTALL | re.IGNORECASE,
    )

    for match in create_pattern.finditer(sql):
        table_name = match.group(1)
        body = match.group(2)

        columns = []
        for line in body.split("\n"):
            line = line.strip().rstrip(",")
            if not line:
                continue
            # Skip constraints (FOREIGN KEY, UNIQUE, PRIMARY KEY as standalone)
            if re.match(
                r"^\s*(FOREIGN\s+KEY|UNIQUE|PRIMARY\s+KEY\s*\(|CHECK)", line, re.IGNORECASE
            ):
                continue
            # Extract column name (first word that isn't a SQL keyword)
            col_match = re.match(r"^(\w+)\s+", line)
            if col_match:
                col_name = col_match.group(1).lower()
                # Skip SQL keywords that might appear at line start
                if col_name not in ("create", "table", "if", "not", "exists", "foreign", "unique"):
                    columns.append(col_name)

        tables[table_name] = columns

    return tables


def _extract_query_columns(source: str, table_name: str) -> dict[str, set[str]]:
    """Extract column names referenced in SQL queries for a given table.

    Args:
        source: Python source code containing SQL queries
        table_name: Table name to search for

    Returns:
        Dict with keys 'insert', 'update', 'select' mapping to sets of column names
    """
    result: dict[str, set[str]] = {"insert": set(), "update": set(), "select": set()}

    # Find INSERT INTO <table> (...) patterns
    insert_pattern = re.compile(
        rf"INSERT\s+INTO\s+{re.escape(table_name)}\s*\(([^)]+)\)",
        re.IGNORECASE | re.DOTALL,
    )
    for match in insert_pattern.finditer(source):
        cols_str = match.group(1)
        for col in cols_str.split(","):
            col = col.strip().lower()
            if col and not col.startswith("?"):
                result["insert"].add(col)

    # Find UPDATE <table> SET col = ... patterns
    update_pattern = re.compile(
        rf"UPDATE\s+{re.escape(table_name)}\s+SET\s+(.*?)(?:WHERE|$)",
        re.IGNORECASE | re.DOTALL,
    )
    for match in update_pattern.finditer(source):
        set_clause = match.group(1)
        for assignment in set_clause.split(","):
            col_match = re.match(r"\s*(\w+)\s*=", assignment)
            if col_match:
                col = col_match.group(1).lower()
                # Skip SQL functions/keywords
                if col not in ("current_timestamp",):
                    result["update"].add(col)

    # Find SELECT ... FROM <table> patterns
    # Handle both direct table references and aliased references
    select_pattern = re.compile(
        rf"SELECT\s+(.*?)\s+FROM\s+{re.escape(table_name)}(?:\s+\w+)?(?:\s|$|WHERE|ORDER|LIMIT|LEFT|JOIN)",
        re.IGNORECASE | re.DOTALL,
    )
    for match in select_pattern.finditer(source):
        cols_str = match.group(1).strip()
        if cols_str == "*":
            continue  # SELECT * is always valid
        for col_expr in cols_str.split(","):
            col_expr = col_expr.strip()
            if not col_expr:
                continue
            # Handle "table.column" or "table.column AS alias"
            # Handle "column AS alias"
            # Handle subqueries - skip them
            if "(" in col_expr:
                continue
            # Strip alias
            col_expr = re.split(r"\s+AS\s+", col_expr, flags=re.IGNORECASE)[0].strip()
            # Strip table prefix
            if "." in col_expr:
                col_expr = col_expr.split(".")[-1]
            col = col_expr.lower().strip()
            if col and col not in ("*",):
                result["select"].add(col)

    return result


def _get_schema_sql() -> str:
    """Get the CREATE TABLE SQL from _ensure_database_initialized()."""
    from main import Default

    source = inspect.getsource(Default._ensure_database_initialized)
    return source


def _get_main_source() -> str:
    """Get the full source of main.py for query extraction."""
    import importlib

    main_module = importlib.import_module("main")
    return inspect.getsource(main_module)


class TestSchemaConsistency:
    """Verify that SQL queries reference columns that exist in the schema."""

    def test_schema_extraction(self):
        """Verify we can extract CREATE TABLE columns from the schema."""
        schema_sql = _get_schema_sql()
        tables = _extract_create_table_columns(schema_sql)

        assert "feeds" in tables, "Should find feeds table in schema"
        assert "entries" in tables, "Should find entries table in schema"
        assert "admins" in tables, "Should find admins table in schema"
        assert "audit_log" in tables, "Should find audit_log table in schema"

        # Verify key columns exist
        assert "url" in tables["feeds"], "feeds table should have 'url' column"
        assert "title" in tables["feeds"], "feeds table should have 'title' column"
        assert "guid" in tables["entries"], "entries table should have 'guid' column"
        assert "github_username" in tables["admins"], "admins table should have 'github_username'"

    def test_feeds_query_columns_exist_in_schema(self):
        """Every column referenced in feeds queries must exist in CREATE TABLE feeds."""
        schema_sql = _get_schema_sql()
        tables = _extract_create_table_columns(schema_sql)
        schema_columns = set(tables["feeds"])

        main_source = _get_main_source()
        query_columns = _extract_query_columns(main_source, "feeds")

        # Check INSERT columns
        for col in query_columns["insert"]:
            assert col in schema_columns, (
                f"INSERT INTO feeds references column '{col}' "
                f"which does not exist in CREATE TABLE feeds. "
                f"Schema columns: {sorted(schema_columns)}"
            )

        # Check UPDATE columns
        for col in query_columns["update"]:
            assert col in schema_columns, (
                f"UPDATE feeds references column '{col}' "
                f"which does not exist in CREATE TABLE feeds. "
                f"Schema columns: {sorted(schema_columns)}"
            )

    def test_entries_query_columns_exist_in_schema(self):
        """Every column referenced in entries queries must exist in CREATE TABLE entries."""
        schema_sql = _get_schema_sql()
        tables = _extract_create_table_columns(schema_sql)
        schema_columns = set(tables["entries"])

        main_source = _get_main_source()
        query_columns = _extract_query_columns(main_source, "entries")

        # Check INSERT columns
        for col in query_columns["insert"]:
            assert col in schema_columns, (
                f"INSERT INTO entries references column '{col}' "
                f"which does not exist in CREATE TABLE entries. "
                f"Schema columns: {sorted(schema_columns)}"
            )

        # Check UPDATE columns
        for col in query_columns["update"]:
            assert col in schema_columns, (
                f"UPDATE entries references column '{col}' "
                f"which does not exist in CREATE TABLE entries. "
                f"Schema columns: {sorted(schema_columns)}"
            )

    def test_admins_query_columns_exist_in_schema(self):
        """Every column referenced in admins queries must exist in CREATE TABLE admins."""
        schema_sql = _get_schema_sql()
        tables = _extract_create_table_columns(schema_sql)
        schema_columns = set(tables["admins"])

        main_source = _get_main_source()
        query_columns = _extract_query_columns(main_source, "admins")

        # Check UPDATE columns
        for col in query_columns["update"]:
            assert col in schema_columns, (
                f"UPDATE admins references column '{col}' "
                f"which does not exist in CREATE TABLE admins. "
                f"Schema columns: {sorted(schema_columns)}"
            )

    def test_audit_log_query_columns_exist_in_schema(self):
        """Every column referenced in audit_log queries must exist in CREATE TABLE audit_log."""
        schema_sql = _get_schema_sql()
        tables = _extract_create_table_columns(schema_sql)
        schema_columns = set(tables["audit_log"])

        main_source = _get_main_source()
        query_columns = _extract_query_columns(main_source, "audit_log")

        # Check INSERT columns
        for col in query_columns["insert"]:
            assert col in schema_columns, (
                f"INSERT INTO audit_log references column '{col}' "
                f"which does not exist in CREATE TABLE audit_log. "
                f"Schema columns: {sorted(schema_columns)}"
            )

    def test_last_entry_at_exists_in_feeds_schema(self):
        """Regression test: last_entry_at must exist in feeds schema.

        This column was missing in an earlier version (C2 bug), causing
        UPDATE feeds SET last_entry_at = ... to fail at runtime.
        """
        schema_sql = _get_schema_sql()
        tables = _extract_create_table_columns(schema_sql)

        assert "last_entry_at" in tables["feeds"], (
            "feeds table must have 'last_entry_at' column. "
            "This was the C2 bug: queries referenced last_entry_at but the "
            "CREATE TABLE was missing it."
        )

    def test_feeds_schema_has_all_expected_columns(self):
        """Verify the feeds table has all columns we know are needed."""
        schema_sql = _get_schema_sql()
        tables = _extract_create_table_columns(schema_sql)
        schema_columns = set(tables["feeds"])

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

        missing = expected - schema_columns
        assert not missing, (
            f"feeds table is missing expected columns: {sorted(missing)}. "
            f"Actual columns: {sorted(schema_columns)}"
        )

    def test_entries_schema_has_all_expected_columns(self):
        """Verify the entries table has all columns we know are needed."""
        schema_sql = _get_schema_sql()
        tables = _extract_create_table_columns(schema_sql)
        schema_columns = set(tables["entries"])

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

        missing = expected - schema_columns
        assert not missing, (
            f"entries table is missing expected columns: {sorted(missing)}. "
            f"Actual columns: {sorted(schema_columns)}"
        )

    def test_runtime_expected_columns_match_schema(self):
        """_EXPECTED_COLUMNS in PlanetCF must match the CREATE TABLE schema.

        The runtime schema drift check uses _EXPECTED_COLUMNS to detect
        missing columns in production. If this dict drifts from the actual
        CREATE TABLE schema, the check becomes ineffective.
        """
        from src.main import PlanetCF

        schema_sql = _get_schema_sql()
        tables = _extract_create_table_columns(schema_sql)

        for table_name, expected_cols in PlanetCF._EXPECTED_COLUMNS.items():
            schema_cols = set(tables.get(table_name, []))
            assert expected_cols == schema_cols, (
                f"_EXPECTED_COLUMNS['{table_name}'] does not match CREATE TABLE schema.\n"
                f"  In _EXPECTED_COLUMNS but not in schema: {sorted(expected_cols - schema_cols)}\n"
                f"  In schema but not in _EXPECTED_COLUMNS: {sorted(schema_cols - expected_cols)}"
            )
