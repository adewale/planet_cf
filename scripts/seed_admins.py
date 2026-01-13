#!/usr/bin/env python3
"""Seed admin users from config/admins.json into D1.

Usage:
    uv run python scripts/seed_admins.py

This script reads the admin configuration from config/admins.json
and inserts/updates the admins in the D1 database using wrangler.
"""

import json
import subprocess
import sys
from pathlib import Path


def seed_admins():
    """Seed admin users from configuration file."""
    config_path = Path("config/admins.json")

    if not config_path.exists():
        print(f"Error: Configuration file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    admins = config.get("admins", [])

    if not admins:
        print("No admins found in configuration file.")
        return

    print(f"Seeding {len(admins)} admin(s)...")

    for admin in admins:
        username = admin["github_username"]
        display_name = admin.get("display_name", username)

        # Escape single quotes in display name
        display_name_escaped = display_name.replace("'", "''")

        sql = f"""
            INSERT INTO admins (github_username, display_name, is_active)
            VALUES ('{username}', '{display_name_escaped}', 1)
            ON CONFLICT(github_username) DO UPDATE SET
                display_name = excluded.display_name,
                is_active = 1;
        """

        result = subprocess.run(
            ["wrangler", "d1", "execute", "planetcf", "--command", sql],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            print(f"  [OK] Seeded admin: {username}")
        else:
            print(f"  [FAIL] Failed to seed {username}: {result.stderr}", file=sys.stderr)
            sys.exit(1)

    print("Done!")


def main():
    """Main entry point."""
    try:
        seed_admins()
    except FileNotFoundError:
        print("Error: wrangler command not found. Please install wrangler:", file=sys.stderr)
        print("  npm install -g wrangler", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)


if __name__ == "__main__":
    main()
