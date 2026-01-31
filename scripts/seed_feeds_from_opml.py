#!/usr/bin/env python3
"""Seed feeds from an OPML file into a D1 database.

This script fetches an OPML file from a URL, parses it to extract feed URLs,
and inserts them into a D1 database using wrangler.

Usage:
    # Using URL directly:
    uv run python scripts/seed_feeds_from_opml.py --url https://planetpython.org/opml.xml --db planet-python-db

    # Using wrangler config (reads OPML_SOURCE_URL from config):
    uv run python scripts/seed_feeds_from_opml.py --config examples/planet-python/wrangler.jsonc

    # Dry run (don't insert, just show feeds):
    uv run python scripts/seed_feeds_from_opml.py --url https://planetpython.org/opml.xml --db planet-python-db --dry-run

Requirements:
    - wrangler CLI installed and authenticated
    - uv for running with dependencies (feedparser, httpx)
"""

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


def fetch_opml(url: str) -> str:
    """Fetch OPML content from a URL."""
    print(f"Fetching OPML from: {url}")
    try:
        # Use a reasonable User-Agent
        req = Request(url, headers={"User-Agent": "PlanetCF-Seeder/1.0"})
        with urlopen(req, timeout=30) as response:
            return response.read().decode("utf-8")
    except URLError as e:
        print(f"Error fetching OPML: {e}", file=sys.stderr)
        sys.exit(1)


def parse_opml(content: str) -> list[dict]:
    """Parse OPML content and extract feed information.

    Returns a list of dicts with 'url', 'title', and 'site_url' keys.
    """
    feeds = []

    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        print(f"Error parsing OPML: {e}", file=sys.stderr)
        sys.exit(1)

    # Find all outline elements with xmlUrl (RSS/Atom feeds)
    for outline in root.iter("outline"):
        xml_url = outline.get("xmlUrl")
        if xml_url:
            feed = {
                "url": xml_url,
                "title": outline.get("title") or outline.get("text") or xml_url,
                "site_url": outline.get("htmlUrl") or "",
            }
            feeds.append(feed)

    return feeds


def strip_jsonc_comments(content: str) -> str:
    """Remove JSONC comments from content.

    Handles:
    - Single line comments: // comment
    - Multi-line comments: /* comment */
    - Preserves strings that might contain // or /*
    """
    result = []
    i = 0
    in_string = False
    string_char = None

    while i < len(content):
        # Handle string boundaries
        if content[i] in "\"'":
            if not in_string:
                in_string = True
                string_char = content[i]
            elif content[i] == string_char and (i == 0 or content[i - 1] != "\\"):
                in_string = False
            result.append(content[i])
            i += 1
        # Handle single-line comments (only outside strings)
        elif not in_string and content[i : i + 2] == "//":
            # Skip until end of line
            while i < len(content) and content[i] != "\n":
                i += 1
        # Handle multi-line comments (only outside strings)
        elif not in_string and content[i : i + 2] == "/*":
            i += 2
            while i < len(content) - 1 and content[i : i + 2] != "*/":
                i += 1
            i += 2  # Skip closing */
        else:
            result.append(content[i])
            i += 1

    return "".join(result)


def read_wrangler_config(config_path: str) -> tuple[str, str]:
    """Read database name and OPML URL from wrangler config.

    Returns (database_name, opml_url) tuple.
    """
    path = Path(config_path)
    if not path.exists():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    content = path.read_text()

    # Remove JSONC comments
    content_no_comments = strip_jsonc_comments(content)

    try:
        config = json.loads(content_no_comments)
    except json.JSONDecodeError as e:
        print(f"Error parsing config file: {e}", file=sys.stderr)
        sys.exit(1)

    # Extract database name
    db_name = None
    d1_databases = config.get("d1_databases", [])
    for db in d1_databases:
        if db.get("binding") == "DB":
            db_name = db.get("database_name")
            break

    if not db_name:
        print("Error: Could not find D1 database name in config", file=sys.stderr)
        sys.exit(1)

    # Extract OPML source URL
    opml_url = config.get("vars", {}).get("OPML_SOURCE_URL")
    if not opml_url:
        print("Error: OPML_SOURCE_URL not found in config vars", file=sys.stderr)
        sys.exit(1)

    return db_name, opml_url


def insert_feeds(
    feeds: list[dict],
    db_name: str,
    config_path: str | None = None,
    dry_run: bool = False,
    batch_size: int = 20,
) -> int:
    """Insert feeds into D1 database using wrangler.

    Args:
        feeds: List of feed dicts with 'url', 'title', 'site_url'
        db_name: D1 database name
        config_path: Optional path to wrangler config file
        dry_run: If True, don't actually insert
        batch_size: Number of feeds to insert per wrangler command

    Returns the number of feeds successfully inserted.
    """
    success_count = 0

    if dry_run:
        for feed in feeds:
            print(f"  [DRY RUN] Would insert: {feed['title']} ({feed['url']})")
            success_count += 1
        return success_count

    # Process in batches
    for i in range(0, len(feeds), batch_size):
        batch = feeds[i : i + batch_size]

        # Build batch SQL
        sql_statements = []
        for feed in batch:
            # Escape single quotes in strings
            title_escaped = feed["title"].replace("'", "''")
            site_url_escaped = feed["site_url"].replace("'", "''")
            url_escaped = feed["url"].replace("'", "''")

            sql_statements.append(f"""INSERT INTO feeds (url, title, site_url, is_active, consecutive_failures, created_at, updated_at)
VALUES ('{url_escaped}', '{title_escaped}', '{site_url_escaped}', 1, 0, datetime('now'), datetime('now'))
ON CONFLICT(url) DO UPDATE SET title = excluded.title, site_url = excluded.site_url, updated_at = datetime('now')""")

        batch_sql = ";\n".join(sql_statements) + ";"

        # Write to temp file for execution
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
            f.write(batch_sql)
            temp_file = f.name

        try:
            cmd = ["npx", "wrangler", "d1", "execute", db_name, "--file", temp_file, "--remote"]
            if config_path:
                cmd.extend(["--config", config_path])

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                for feed in batch:
                    print(f"  [OK] {feed['title']}")
                    success_count += 1
            else:
                # Try individual inserts for the batch that failed
                print("  [WARN] Batch failed, trying individual inserts...")
                for feed in batch:
                    title_escaped = feed["title"].replace("'", "''")
                    site_url_escaped = feed["site_url"].replace("'", "''")
                    url_escaped = feed["url"].replace("'", "''")

                    single_sql = f"""INSERT INTO feeds (url, title, site_url, is_active, consecutive_failures, created_at, updated_at)
VALUES ('{url_escaped}', '{title_escaped}', '{site_url_escaped}', 1, 0, datetime('now'), datetime('now'))
ON CONFLICT(url) DO UPDATE SET title = excluded.title, site_url = excluded.site_url, updated_at = datetime('now');"""

                    single_cmd = [
                        "npx",
                        "wrangler",
                        "d1",
                        "execute",
                        db_name,
                        "--command",
                        single_sql,
                        "--remote",
                    ]
                    if config_path:
                        single_cmd.extend(["--config", config_path])

                    single_result = subprocess.run(single_cmd, capture_output=True, text=True)
                    if single_result.returncode == 0:
                        print(f"  [OK] {feed['title']}")
                        success_count += 1
                    else:
                        print(f"  [FAIL] {feed['title']}: {single_result.stderr}", file=sys.stderr)
        finally:
            import os

            os.unlink(temp_file)

        # Progress indicator
        print(f"  Progress: {min(i + batch_size, len(feeds))}/{len(feeds)}")

    return success_count


def main():
    parser = argparse.ArgumentParser(
        description="Seed feeds from an OPML file into a D1 database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Using URL directly:
    python scripts/seed_feeds_from_opml.py --url https://planetpython.org/opml.xml --db planet-python-db

    # Using wrangler config:
    python scripts/seed_feeds_from_opml.py --config examples/planet-python/wrangler.jsonc

    # Dry run:
    python scripts/seed_feeds_from_opml.py --config examples/planet-python/wrangler.jsonc --dry-run
""",
    )

    parser.add_argument("--url", help="URL of the OPML file to fetch")
    parser.add_argument("--db", help="Name of the D1 database")
    parser.add_argument(
        "--config", help="Path to wrangler config file (reads OPML_SOURCE_URL and database name)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be inserted without actually inserting",
    )

    args = parser.parse_args()

    # Determine source of configuration
    if args.config:
        db_name, opml_url = read_wrangler_config(args.config)
        config_path = args.config
    elif args.url and args.db:
        opml_url = args.url
        db_name = args.db
        config_path = None
    else:
        parser.error("Either --config OR both --url and --db are required")

    print(f"Database: {db_name}")
    print(f"OPML URL: {opml_url}")
    if args.dry_run:
        print("Mode: DRY RUN")
    print()

    # Fetch and parse OPML
    opml_content = fetch_opml(opml_url)
    feeds = parse_opml(opml_content)

    if not feeds:
        print("No feeds found in OPML file")
        return

    print(f"Found {len(feeds)} feeds in OPML")
    print()

    # Insert feeds
    print("Inserting feeds...")
    success_count = insert_feeds(feeds, db_name, config_path, args.dry_run)

    print()
    print(f"Done! {success_count}/{len(feeds)} feeds processed successfully.")


if __name__ == "__main__":
    main()
