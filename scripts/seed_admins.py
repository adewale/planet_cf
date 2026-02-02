#!/usr/bin/env python3
"""Seed admin users from config/admins.json into D1.

Usage:
    uv run python scripts/seed_admins.py           # Seed to remote (production)
    uv run python scripts/seed_admins.py --local   # Seed to local dev database

This script reads the admin configuration from config/admins.json
and inserts/updates the admins in the D1 database using wrangler.

Admins marked with "test_only": true are only seeded in local mode.
"""

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

# Module-level connection for efficient SQL quoting
_quote_conn = sqlite3.connect(":memory:")


def sql_quote(value: str) -> str:
    """Safely quote a string for SQLite SQL."""
    cursor = _quote_conn.execute("SELECT quote(?)", (value,))
    return cursor.fetchone()[0]


def seed_admins(local: bool = False):
    """Seed admin users from configuration file.

    Args:
        local: If True, seed to local D1 database and include test_only admins.
    """
    config_path = Path("config/admins.json")

    if not config_path.exists():
        print(f"Error: Configuration file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    admins = config.get("admins", [])

    # Filter test_only admins for production
    if not local:
        admins = [a for a in admins if not a.get("test_only", False)]

    if not admins:
        print("No admins found in configuration file.")
        return

    target = "local" if local else "remote"
    print(f"Seeding {len(admins)} admin(s) to {target} database...")

    failed_admins = []

    for admin in admins:
        username = admin["github_username"]
        display_name = admin.get("display_name", username)
        github_id = admin.get("github_id", 0)

        # Use proper SQL escaping for both fields
        username_quoted = sql_quote(username)
        display_name_quoted = sql_quote(display_name)

        sql = f"""
            INSERT INTO admins (github_username, github_id, display_name, is_active)
            VALUES ({username_quoted}, {github_id}, {display_name_quoted}, 1)
            ON CONFLICT(github_username) DO UPDATE SET
                display_name = excluded.display_name,
                is_active = 1;
        """

        cmd = ["npx", "wrangler", "d1", "execute", "planetcf", "--command", sql]
        if local:
            cmd.append("--local")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            print(f"  [OK] Seeded admin: {username}")
        else:
            print(f"  [FAIL] Failed to seed {username}: {result.stderr}", file=sys.stderr)
            failed_admins.append(username)

    if failed_admins:
        print(f"\n{len(failed_admins)} admin(s) failed to seed", file=sys.stderr)
        sys.exit(1)

    print("Done!")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Seed admin users into D1 database")
    parser.add_argument(
        "--local",
        action="store_true",
        help="Seed to local D1 database (includes test_only admins)",
    )
    args = parser.parse_args()

    try:
        seed_admins(local=args.local)
    except FileNotFoundError:
        print("Error: wrangler command not found. Please install wrangler:", file=sys.stderr)
        print("  npm install -g wrangler", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)


if __name__ == "__main__":
    main()
