#!/usr/bin/env python3
"""Seed test data into a test-planet D1 database.

Reads fixture data from tests/fixtures/blog_posts.json and seeds admins,
feeds, and entries into the D1 database. All operations are idempotent
(INSERT ON CONFLICT).

Usage:
    # Seed to local D1 database
    uv run python scripts/seed_test_data.py --local

    # Seed to remote D1 database (default config)
    uv run python scripts/seed_test_data.py

    # Seed with custom wrangler config
    uv run python scripts/seed_test_data.py --config examples/test-planet/wrangler.jsonc

    # Seed and trigger reindex to populate Vectorize
    uv run python scripts/seed_test_data.py --local --reindex --base-url http://localhost:8787

    # Seed with custom session secret for reindex auth
    uv run python scripts/seed_test_data.py --reindex --base-url http://localhost:8787 \\
        --session-secret my-secret
"""

import argparse
import base64
import hashlib
import hmac
import json
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Module-level connection for efficient SQL quoting
_quote_conn = sqlite3.connect(":memory:")

# Default database name (overridden by --db-name)
DEFAULT_DB_NAME = "test-planet-db"

# Default session secret for test-planet (matches E2E_SESSION_SECRET in tests)
DEFAULT_SESSION_SECRET = "test-session-secret-for-e2e-testing-only"


def sql_quote(value: str) -> str:
    """Safely quote a string for SQLite SQL."""
    cursor = _quote_conn.execute("SELECT quote(?)", (value,))
    return cursor.fetchone()[0]


def run_sql(db_name: str, sql: str, *, local: bool = False, config: str | None = None) -> bool:
    """Execute SQL against D1 via wrangler.

    Returns True on success, False on failure.
    """
    cmd = ["npx", "wrangler", "d1", "execute", db_name, "--command", sql]
    if local:
        cmd.append("--local")
    else:
        cmd.append("--remote")
    if config:
        cmd.extend(["--config", config])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [FAIL] SQL error: {result.stderr.strip()}", file=sys.stderr)
        return False
    return True


def seed_admins(db_name: str, *, local: bool = False, config: str | None = None) -> int:
    """Seed test admin users. Returns count of successfully seeded admins."""
    admins = [
        {"username": "adewale", "display_name": "Adewale Oshineye", "github_id": 0},
        {"username": "testadmin", "display_name": "Test Admin", "github_id": 12345},
    ]

    print(f"Seeding {len(admins)} admin(s)...")
    success = 0
    for admin in admins:
        sql = (
            f"INSERT INTO admins (github_username, github_id, display_name, is_active) "
            f"VALUES ({sql_quote(admin['username'])}, {admin['github_id']}, "
            f"{sql_quote(admin['display_name'])}, 1) "
            f"ON CONFLICT(github_username) DO UPDATE SET "
            f"display_name = excluded.display_name, is_active = 1;"
        )
        if run_sql(db_name, sql, local=local, config=config):
            print(f"  [OK] Admin: {admin['username']}")
            success += 1
        else:
            print(f"  [FAIL] Admin: {admin['username']}", file=sys.stderr)

    return success


def seed_feeds(
    db_name: str, feeds: list[dict], *, local: bool = False, config: str | None = None
) -> int:
    """Seed feeds from fixture data. Returns count of successfully seeded feeds."""
    print(f"Seeding {len(feeds)} feed(s)...")
    success = 0
    for feed in feeds:
        sql = (
            f"INSERT INTO feeds (url, title, site_url, is_active) "
            f"VALUES ({sql_quote(feed['url'])}, {sql_quote(feed['title'])}, "
            f"{sql_quote(feed.get('site_url', ''))}, 1) "
            f"ON CONFLICT(url) DO UPDATE SET "
            f"title = excluded.title, site_url = excluded.site_url, is_active = 1;"
        )
        if run_sql(db_name, sql, local=local, config=config):
            print(f"  [OK] Feed: {feed['title']}")
            success += 1
        else:
            print(f"  [FAIL] Feed: {feed['title']}", file=sys.stderr)

    return success


def seed_entries(
    db_name: str, entries: list[dict], *, local: bool = False, config: str | None = None
) -> int:
    """Seed entries from fixture data. Returns count of successfully seeded entries."""
    print(f"Seeding {len(entries)} entries(s)...")
    success = 0
    for entry in entries:
        published_at = entry.get("published_at", "")
        sql = (
            f"INSERT INTO entries (feed_id, guid, url, title, author, content, summary, "
            f"published_at, first_seen) "
            f"VALUES ({entry['feed_id']}, {sql_quote(entry['guid'])}, "
            f"{sql_quote(entry.get('url', ''))}, {sql_quote(entry.get('title', ''))}, "
            f"{sql_quote(entry.get('author', ''))}, {sql_quote(entry.get('content', ''))}, "
            f"{sql_quote(entry.get('summary', ''))}, "
            f"{sql_quote(published_at)}, {sql_quote(published_at)}) "
            f"ON CONFLICT(feed_id, guid) DO UPDATE SET "
            f"title = excluded.title, content = excluded.content, "
            f"summary = excluded.summary, author = excluded.author, "
            f"published_at = excluded.published_at;"
        )
        if run_sql(db_name, sql, local=local, config=config):
            print(f"  [OK] Entry: {entry.get('title', entry['guid'])}")
            success += 1
        else:
            print(f"  [FAIL] Entry: {entry.get('title', entry['guid'])}", file=sys.stderr)

    return success


def trigger_reindex(base_url: str, session_secret: str) -> bool:
    """Trigger a reindex via the admin API to populate Vectorize.

    Creates a signed session cookie to authenticate as testadmin.
    """
    try:
        import httpx
    except ImportError:
        print(
            "Error: httpx is required for --reindex. Install with: uv pip install httpx",
            file=sys.stderr,
        )
        return False

    # Create signed session cookie (must match the worker's cookie verification)
    payload = {
        "github_username": "testadmin",
        "github_id": 12345,
        "avatar_url": None,
        "exp": int(time.time()) + 3600,
    }
    payload_json = json.dumps(payload)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode()
    signature = hmac.new(session_secret.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    session_value = f"{payload_b64}.{signature}"

    print(f"Triggering reindex at {base_url}/admin/reindex...")
    try:
        client = httpx.Client(base_url=base_url, timeout=120.0)
        response = client.post(
            "/admin/reindex",
            cookies={"session": session_value},
            follow_redirects=True,
        )
        client.close()

        if response.status_code == 200:
            print("  [OK] Reindex triggered successfully")
            return True
        else:
            print(f"  [FAIL] Reindex returned status {response.status_code}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"  [FAIL] Reindex failed: {e}", file=sys.stderr)
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Seed test data into a test-planet D1 database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  uv run python scripts/seed_test_data.py --local
  uv run python scripts/seed_test_data.py --config examples/test-planet/wrangler.jsonc
  uv run python scripts/seed_test_data.py --reindex --base-url http://localhost:8787
""",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Seed to local D1 database",
    )
    parser.add_argument(
        "--db-name",
        default=DEFAULT_DB_NAME,
        help=f"D1 database name (default: {DEFAULT_DB_NAME})",
    )
    parser.add_argument(
        "--config",
        help="Path to wrangler config file (e.g., examples/test-planet/wrangler.jsonc)",
    )
    parser.add_argument(
        "--fixtures",
        default="tests/fixtures/blog_posts.json",
        help="Path to fixtures JSON file (default: tests/fixtures/blog_posts.json)",
    )
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Trigger reindex after seeding to populate Vectorize",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8787",
        help="Base URL of the running worker (for --reindex)",
    )
    parser.add_argument(
        "--session-secret",
        default=DEFAULT_SESSION_SECRET,
        help="Session secret for creating auth cookie (for --reindex)",
    )
    args = parser.parse_args()

    # Load fixtures
    fixtures_path = Path(args.fixtures)
    if not fixtures_path.exists():
        print(f"Error: Fixtures file not found: {fixtures_path}", file=sys.stderr)
        sys.exit(1)

    with open(fixtures_path) as f:
        fixtures = json.load(f)

    feeds = fixtures.get("feeds", [])
    entries = fixtures.get("entries", [])

    # Override published_at with dynamic dates relative to today so entries
    # are always within the 30-day retention window regardless of when the
    # seed script is run. Entry 0 gets yesterday, entry 1 gets 2 days ago, etc.
    now = datetime.now(UTC)
    for i, entry in enumerate(entries):
        dynamic_date = now - timedelta(days=i + 1)
        entry["published_at"] = dynamic_date.strftime("%Y-%m-%dT%H:%M:%S")

    if not feeds and not entries:
        print("No test data found in fixtures file.")
        sys.exit(1)

    target = "local" if args.local else "remote"
    print(f"Seeding test data to {target} database ({args.db_name})...\n")

    failed = False

    # Step 1: Seed admins
    admin_count = seed_admins(args.db_name, local=args.local, config=args.config)
    if admin_count < 2:
        failed = True
    print()

    # Step 2: Seed feeds
    feed_count = seed_feeds(args.db_name, feeds, local=args.local, config=args.config)
    if feed_count < len(feeds):
        failed = True
    print()

    # Step 3: Seed entries
    entry_count = seed_entries(args.db_name, entries, local=args.local, config=args.config)
    if entry_count < len(entries):
        failed = True
    print()

    # Step 4: Optional reindex
    if args.reindex:
        if not trigger_reindex(args.base_url, args.session_secret):
            failed = True
        print()

    # Summary
    print("=" * 50)
    print(f"Admins:  {admin_count}/2")
    print(f"Feeds:   {feed_count}/{len(feeds)}")
    print(f"Entries: {entry_count}/{len(entries)}")
    if args.reindex:
        print("Reindex: triggered")
    print("=" * 50)

    if failed:
        print("\nSome operations failed. Check errors above.", file=sys.stderr)
        sys.exit(1)

    print("\nDone!")


if __name__ == "__main__":
    main()
