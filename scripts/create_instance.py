#!/usr/bin/env python3
"""
Create a new Planet instance.

This script provisions all Cloudflare resources needed for a new planet instance,
similar to Rogue Planet's `rp init` command.

Usage:
    python scripts/create_instance.py --id planet-python --name "Planet Python"
    python scripts/create_instance.py --id my-planet --from-example planet-cloudflare

This will:
1. Create examples/{id}/ directory with config.yaml, wrangler.jsonc, assets/
2. Print instructions for creating Cloudflare resources

For full automated provisioning, you'll need wrangler CLI installed.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Paths relative to script
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
EXAMPLES_DIR = PROJECT_ROOT / "examples"
CONFIG_DIR = PROJECT_ROOT / "config"
TEMPLATE_FILE = CONFIG_DIR / "instance.example.yaml"


def get_available_themes() -> list[str]:
    """Get list of available themes from templates.py."""
    try:
        # Import from src directory
        sys.path.insert(0, str(PROJECT_ROOT / "src"))
        from templates import _EMBEDDED_TEMPLATES

        # Return themes excluding _shared (internal)
        return [t for t in _EMBEDDED_TEMPLATES if not t.startswith("_")]
    except ImportError:
        # Fallback if templates.py doesn't exist yet
        return ["default"]


def validate_theme(theme: str) -> tuple[bool, str]:
    """Validate that a theme exists in templates.py.

    Returns:
        (is_valid, message)
    """
    available = get_available_themes()
    if theme in available:
        return True, f"Theme '{theme}' is available"
    else:
        return False, (
            f"Warning: Theme '{theme}' not found in templates.py.\n"
            f"Available themes: {', '.join(sorted(available))}\n"
            f"The default theme will be used at runtime."
        )


def create_python_modules_symlink(instance_dir: Path) -> bool:
    """Create python_modules symlink in instance directory.

    Args:
        instance_dir: Path to the instance directory (examples/{instance_id}/)

    Returns:
        True if symlink was created or already exists, False on error
    """
    symlink_path = instance_dir / "python_modules"
    target = "../../python_modules"

    # Check if root python_modules exists
    root_python_modules = PROJECT_ROOT / "python_modules"
    if not root_python_modules.exists():
        print("    ⚠️  Root python_modules/ not found. Run 'make python-modules' before deploying.")
        return False

    if symlink_path.is_symlink():
        # Already a symlink - check if it points to the right place
        current_target = os.readlink(symlink_path)
        if current_target == target:
            print("    ✓ python_modules symlink already exists")
            return True
        else:
            # Points to wrong place - remove and recreate
            symlink_path.unlink()
    elif symlink_path.exists():
        # Exists but not a symlink (could be a directory from copying)
        print("    ✓ python_modules directory exists (not a symlink)")
        return True

    try:
        symlink_path.symlink_to(target)
        print(f"    ✓ Created python_modules symlink -> {target}")
        return True
    except OSError as e:
        print(f"    ⚠️  Could not create symlink: {e}")
        return False


def slugify(text: str) -> str:
    """Convert text to a valid slug for resource names."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text


def create_instance_config(
    instance_id: str,
    name: str,
    description: str,
    url: str,
    owner_name: str,
    owner_email: str,
    theme: str = "default",
    mode: str = "full",
) -> Path:
    """Create instance configuration file from template."""
    instance_dir = EXAMPLES_DIR / instance_id
    instance_dir.mkdir(parents=True, exist_ok=True)
    # Create assets directory for Workers Static Assets binding
    (instance_dir / "assets").mkdir(exist_ok=True)
    # Create assets/static/ subdirectory and copy default static files
    (instance_dir / "assets" / "static").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        PROJECT_ROOT / "templates" / "style.css", instance_dir / "assets" / "static" / "style.css"
    )
    # Only copy keyboard-nav.js for default theme instances.
    # Replica themes (planet-python, planet-mozilla) don't load it — the originals
    # have no keyboard navigation, so replicas shouldn't either.
    if theme == "default":
        shutil.copy2(
            PROJECT_ROOT / "templates" / "keyboard-nav.js",
            instance_dir / "assets" / "static" / "keyboard-nav.js",
        )
    if mode != "lite":
        shutil.copy2(
            PROJECT_ROOT / "static" / "admin.js", instance_dir / "assets" / "static" / "admin.js"
        )

    # In lite/admin mode, create a starter feeds.opml file
    if mode in ("lite", "admin"):
        feeds_opml = instance_dir / "assets" / "feeds.opml"
        if not feeds_opml.exists():
            feeds_opml.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head>
    <title>{name} Feeds</title>
    <ownerName>{owner_name}</ownerName>
    <ownerEmail>{owner_email}</ownerEmail>
  </head>
  <body>
    <!-- Add your feeds here -->
    <!-- Example: <outline type="rss" text="Blog Name" xmlUrl="https://example.com/feed.xml"/> -->
  </body>
</opml>
""")

    search_enabled = "true" if mode == "full" else "false"
    show_admin_link = "false" if mode == "lite" else "true"

    # Build config sections
    mode_section = f"""# =============================================================================
# Instance Mode
# =============================================================================
# Mode: full (all features) or lite (simplified, no search/auth)
mode: {mode}
"""

    auth_section = ""
    if mode != "lite":
        auth_section = """
# =============================================================================
# Authentication
# =============================================================================
auth:
  provider: github
  scopes:
    - user:email
  session_ttl_seconds: 604800
"""

    cloudflare_section = f"""# =============================================================================
# Cloudflare Resources (auto-generated names)
# =============================================================================
cloudflare:
  database_name: {instance_id}-db"""

    if mode == "full":
        cloudflare_section += f"""
  vectorize_index: {instance_id}-entries"""

    cloudflare_section += f"""
  feed_queue: {instance_id}-feed-queue
  dead_letter_queue: {instance_id}-feed-dlq
"""

    admin_section = ""
    if mode != "lite":
        admin_section = """
# =============================================================================
# Admin Users
# =============================================================================
admins:
  - username: your-github-username
    display_name: Your Name
"""

    config_content = f"""# Planet Instance Configuration: {name}
# Generated by create_instance.py

{mode_section}
# =============================================================================
# Core Identity
# =============================================================================
planet:
  id: {instance_id}
  name: {name}
  description: {description}
  url: {url}
  owner:
    name: {owner_name}
    email: {owner_email}

# =============================================================================
# Branding & Theme
# =============================================================================
branding:
  # Available themes: default, planet-python, planet-mozilla
  theme: {theme}

  # User-Agent string for feed fetching
  user_agent: "{{name}}/1.0 (+{{url}}; {{email}})"

  # Footer text
  footer_text: "Powered by {{name}}"

  show_admin_link: {show_admin_link}

# =============================================================================
# Content Settings
# =============================================================================
content:
  days: 7
  group_by_date: true
  max_entries_per_feed: 100
  retention_days: 90
  summary_max_length: 500

# =============================================================================
# Search Configuration
# =============================================================================
search:
  enabled: {search_enabled}
  embedding_max_chars: 2000
  score_threshold: 0.3
  top_k: 50

# =============================================================================
# Feed Processing
# =============================================================================
feeds:
  http_timeout_seconds: 30
  feed_timeout_seconds: 60
  auto_deactivate_threshold: 10
  failure_threshold: 3
{auth_section}
{cloudflare_section}{admin_section}"""

    config_path = instance_dir / "config.yaml"
    config_path.write_text(config_content)
    return config_path


def generate_wrangler_config(
    instance_id: str,
    name: str,
    description: str,
    url: str,
    owner_name: str,
    owner_email: str,
    theme: str = "default",
    database_id: str = "YOUR_DATABASE_ID",
    mode: str = "full",
) -> Path:
    """Generate wrangler configuration file for the instance.

    Args:
        instance_id: Unique identifier for the instance
        name: Display name
        description: Planet description
        url: Public URL
        owner_name: Owner name
        owner_email: Owner email
        theme: Theme name
        database_id: D1 database ID (or placeholder)
        mode: Instance mode - "lite", "admin", or "full"
    """

    # Base vars
    vars_config = {
        "PLANET_NAME": name,
        "PLANET_DESCRIPTION": description,
        "PLANET_URL": url,
        "PLANET_OWNER_NAME": owner_name,
        "THEME": theme,
        "INSTANCE_MODE": mode,
        "RETENTION_DAYS": "90",
        "RETENTION_MAX_ENTRIES_PER_FEED": "100",
        "FEED_TIMEOUT_SECONDS": "60",
        "HTTP_TIMEOUT_SECONDS": "30",
    }

    config = {
        "$schema": "node_modules/wrangler/config-schema.json",
        "name": instance_id,
        "main": "../../src/main.py",
        "compatibility_date": "2026-01-01",
        "compatibility_flags": ["python_workers", "python_dedicated_snapshot"],
        "limits": {"cpu_ms": 60000},
        "vars": vars_config,
        "observability": {"enabled": True, "head_sampling_rate": 1.0},
        "d1_databases": [
            {
                "binding": "DB",
                "database_name": f"{instance_id}-db",
                "database_id": database_id,
            }
        ],
        "queues": {
            "producers": [
                {"binding": "FEED_QUEUE", "queue": f"{instance_id}-feed-queue"},
                {"binding": "DEAD_LETTER_QUEUE", "queue": f"{instance_id}-feed-dlq"},
            ],
            "consumers": [
                {
                    "queue": f"{instance_id}-feed-queue",
                    "max_batch_size": 5,
                    "max_batch_timeout": 30,
                    "max_retries": 3,
                    "dead_letter_queue": f"{instance_id}-feed-dlq",
                    "retry_delay": 300,
                }
            ],
        },
        "triggers": {"crons": ["0 * * * *"]},
        # Assets binding for serving static files
        "assets": {"directory": "./assets/", "binding": "ASSETS"},
    }

    # Add Vectorize and AI bindings only in full mode
    if mode == "full":
        config["vectorize"] = [{"binding": "SEARCH_INDEX", "index_name": f"{instance_id}-entries"}]
        config["ai"] = {"binding": "AI"}

    # Write as JSONC with comments
    instance_dir = EXAMPLES_DIR / instance_id
    instance_dir.mkdir(parents=True, exist_ok=True)
    wrangler_path = instance_dir / "wrangler.jsonc"

    # Build manual deploy instructions based on mode
    if mode == "lite":
        manual_deploy_steps = f"""// =============================================================================
// MANUAL DEPLOY (Alternative) - LITE MODE
// =============================================================================
// Lite mode: No Vectorize index or OAuth secrets required
//
// 1. Create D1 database: npx wrangler d1 create {instance_id}-db
// 2. Update database_id below with the ID from step 1
// 3. Create queues:
//    npx wrangler queues create {instance_id}-feed-queue
//    npx wrangler queues create {instance_id}-feed-dlq
// 4. Run migrations:
//    npx wrangler d1 execute {instance_id}-db --remote --file migrations/001_initial.sql
// 5. Deploy: npx wrangler deploy --config examples/{instance_id}/wrangler.jsonc
// ============================================================================="""
    elif mode == "admin":
        manual_deploy_steps = f"""// =============================================================================
// MANUAL DEPLOY (Alternative) - ADMIN MODE
// =============================================================================
// Admin mode: OAuth + admin dashboard, no Vectorize/AI needed
//
// 1. Create D1 database: npx wrangler d1 create {instance_id}-db
// 2. Update database_id below with the ID from step 1
// 3. Create queues:
//    npx wrangler queues create {instance_id}-feed-queue
//    npx wrangler queues create {instance_id}-feed-dlq
// 4. Set secrets:
//    npx wrangler secret put GITHUB_CLIENT_ID --config examples/{instance_id}/wrangler.jsonc
//    npx wrangler secret put GITHUB_CLIENT_SECRET --config examples/{instance_id}/wrangler.jsonc
//    npx wrangler secret put SESSION_SECRET --config examples/{instance_id}/wrangler.jsonc
// 5. Run migrations:
//    npx wrangler d1 execute {instance_id}-db --remote --file migrations/001_initial.sql
// 6. Deploy: npx wrangler deploy --config examples/{instance_id}/wrangler.jsonc
// ============================================================================="""
    else:
        manual_deploy_steps = f"""// =============================================================================
// MANUAL DEPLOY (Alternative)
// =============================================================================
// 1. Create D1 database: npx wrangler d1 create {instance_id}-db
// 2. Update database_id below with the ID from step 1
// 3. Create Vectorize index: npx wrangler vectorize create {instance_id}-entries --dimensions 768 --metric cosine
// 4. Create queues:
//    npx wrangler queues create {instance_id}-feed-queue
//    npx wrangler queues create {instance_id}-feed-dlq
// 5. Set secrets:
//    npx wrangler secret put GITHUB_CLIENT_ID --config examples/{instance_id}/wrangler.jsonc
//    npx wrangler secret put GITHUB_CLIENT_SECRET --config examples/{instance_id}/wrangler.jsonc
//    npx wrangler secret put SESSION_SECRET --config examples/{instance_id}/wrangler.jsonc
// 6. Run migrations:
//    npx wrangler d1 execute {instance_id}-db --remote --file migrations/001_initial.sql
// 7. Deploy: npx wrangler deploy --config examples/{instance_id}/wrangler.jsonc
// ============================================================================="""

    mode_label = f"{mode.upper()} MODE"

    # Build quick deploy section based on mode
    if mode == "lite":
        quick_deploy_options = ""
    else:
        quick_deploy_options = """
//
// Options:
//   --skip-secrets   Skip interactive secret prompts (set later)"""

    # Manual JSONC formatting for readability
    jsonc_content = f"""// examples/{instance_id}/wrangler.jsonc
// Planet instance: {name}
// Mode: {mode_label}
// Generated by create_instance.py
//
// =============================================================================
// QUICK DEPLOY (Recommended)
// =============================================================================
// Deploy everything with a single command:
//
//   ./scripts/deploy_instance.sh {instance_id}{quick_deploy_options}
//
// The script is idempotent - safe to re-run if needed.
//
{manual_deploy_steps}

{json.dumps(config, indent=2)}
"""

    wrangler_path.write_text(jsonc_content)
    return wrangler_path


def run_wrangler_command(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a wrangler command."""
    full_cmd = ["npx", "wrangler"] + cmd
    print(f"  Running: {' '.join(full_cmd)}")
    return subprocess.run(full_cmd, capture_output=True, text=True, check=check)


def update_wrangler_config_database_id(instance_id: str, database_id: str) -> bool:
    """Update the database_id in a wrangler config file.

    Args:
        instance_id: The instance identifier
        database_id: The actual D1 database UUID

    Returns:
        True if successfully updated, False otherwise
    """
    wrangler_path = EXAMPLES_DIR / instance_id / "wrangler.jsonc"
    if not wrangler_path.exists():
        print(f"    Warning: Config file not found: {wrangler_path}")
        return False

    content = wrangler_path.read_text()

    # Replace the placeholder with actual database_id
    # This handles both "YOUR_DATABASE_ID" placeholder and any existing UUID
    updated_content = re.sub(
        r'"database_id":\s*"[^"]*"',
        f'"database_id": "{database_id}"',
        content,
    )

    if updated_content != content:
        wrangler_path.write_text(updated_content)
        print(f"    Updated database_id in {wrangler_path.name}")
        return True

    return False


def validate_wrangler_config(instance_id: str) -> dict:
    """Validate a wrangler configuration file before deployment.

    Args:
        instance_id: The instance identifier

    Returns:
        Dict with 'valid' bool and 'issues' list of problems found
    """
    issues = []
    warnings = []

    wrangler_path = EXAMPLES_DIR / instance_id / "wrangler.jsonc"

    # Check config exists
    if not wrangler_path.exists():
        issues.append(f"Configuration file not found: {wrangler_path.name}")
        return {"valid": False, "issues": issues, "warnings": warnings}

    content = wrangler_path.read_text()

    # Detect instance mode from config
    if '"INSTANCE_MODE": "lite"' in content:
        detected_mode = "lite"
    elif '"INSTANCE_MODE": "admin"' in content:
        detected_mode = "admin"
    else:
        detected_mode = "full"

    # Check database_id is not placeholder
    if "YOUR_DATABASE_ID" in content:
        issues.append(
            "database_id is still set to placeholder 'YOUR_DATABASE_ID'. "
            "Create the D1 database first and update the config."
        )

    # Check for empty database_id
    if '"database_id": ""' in content:
        issues.append("database_id is empty. Create the D1 database and update the config.")

    # Check that required vars exist
    required_vars = ["PLANET_NAME", "PLANET_URL"]
    for var in required_vars:
        if f'"{var}"' not in content:
            issues.append(f"Missing required environment variable: {var}")

    # Warnings for secrets (only for non-lite modes - lite mode doesn't need auth secrets)
    if detected_mode != "lite":
        warnings.append(
            "Remember to set secrets before deploying:\n"
            f"    npx wrangler secret put GITHUB_CLIENT_ID --config {wrangler_path.name}\n"
            f"    npx wrangler secret put GITHUB_CLIENT_SECRET --config {wrangler_path.name}\n"
            f"    npx wrangler secret put SESSION_SECRET --config {wrangler_path.name}"
        )
    else:
        warnings.append(
            "Lite mode: No OAuth secrets required. Admin and search features are disabled."
        )

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
    }


def provision_cloudflare_resources(
    instance_id: str,
    auto_provision: bool = False,
    update_config: bool = True,
    mode: str = "full",
) -> dict:
    """Provision Cloudflare resources for the instance.

    Args:
        instance_id: The instance identifier
        auto_provision: If True, actually create resources via wrangler CLI
        update_config: If True and auto_provision is True, update wrangler config
                      with extracted database_id
        mode: Instance mode - "lite", "admin", or "full"

    Returns:
        Dict with resource IDs if auto_provision is True.
    """
    resources = {}

    if not auto_provision:
        print("\n📋 Manual provisioning steps:")
        print("\n  # 1. Create D1 database")
        print(f"  npx wrangler d1 create {instance_id}-db")
        if mode == "full":
            print("\n  # 2. Create Vectorize index")
            print(
                f"  npx wrangler vectorize create {instance_id}-entries --dimensions 768 --metric cosine"
            )
            step_num = 3
        else:
            print(f"\n  # (Skipping Vectorize index - {mode} mode)")
            step_num = 2
        print(f"\n  # {step_num}. Create queues")
        print(f"  npx wrangler queues create {instance_id}-feed-queue")
        print(f"  npx wrangler queues create {instance_id}-feed-dlq")
        step_num += 1
        if mode != "lite":
            print(f"\n  # {step_num}. Set secrets")
            print(
                f"  npx wrangler secret put GITHUB_CLIENT_ID --config examples/{instance_id}/wrangler.jsonc"
            )
            print(
                f"  npx wrangler secret put GITHUB_CLIENT_SECRET --config examples/{instance_id}/wrangler.jsonc"
            )
            print(
                f"  npx wrangler secret put SESSION_SECRET --config examples/{instance_id}/wrangler.jsonc"
            )
            step_num += 1
        else:
            print("\n  # (Skipping secrets - lite mode, no auth required)")
        print(f"\n  # {step_num}. Run migrations")
        print(
            f"  npx wrangler d1 execute {instance_id}-db --file migrations/001_initial.sql --config examples/{instance_id}/wrangler.jsonc"
        )
        step_num += 1
        print(f"\n  # {step_num}. Deploy")
        print(f"  npx wrangler deploy --config examples/{instance_id}/wrangler.jsonc")
        return resources

    mode_label = mode
    print(f"\n🚀 Auto-provisioning Cloudflare resources ({mode_label} mode)...")

    # Create D1 database
    print("\n  Creating D1 database...")
    result = run_wrangler_command(["d1", "create", f"{instance_id}-db"], check=False)
    if result.returncode == 0:
        # Parse database ID from output - check both stdout and full output
        output_text = result.stdout + result.stderr
        # Look for UUID pattern anywhere in output (wrangler output format may vary)
        match = re.search(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            output_text,
            re.IGNORECASE,
        )
        if match:
            resources["database_id"] = match.group(0)
            print(f"    Database ID: {resources['database_id']}")

            # Auto-update wrangler config with the extracted database_id
            if update_config:
                update_wrangler_config_database_id(instance_id, resources["database_id"])

            print("    ✓ Database created successfully")
        else:
            print("    ✓ Database created (could not extract ID from output)")
            print(f"    Output: {output_text[:200]}...")
    else:
        print(f"    ✗ Failed to create database: {result.stderr}")

    # Create Vectorize index (only in full mode)
    if mode == "full":
        print("\n  Creating Vectorize index...")
        result = run_wrangler_command(
            [
                "vectorize",
                "create",
                f"{instance_id}-entries",
                "--dimensions",
                "768",
                "--metric",
                "cosine",
            ],
            check=False,
        )
        if result.returncode == 0:
            resources["vectorize_index"] = f"{instance_id}-entries"
            print("    ✓ Vectorize index created")
        else:
            print(f"    ✗ Failed to create Vectorize index: {result.stderr}")
    else:
        print(f"\n  Skipping Vectorize index ({mode} mode)")

    # Create queues
    print("\n  Creating queues...")
    for queue in [f"{instance_id}-feed-queue", f"{instance_id}-feed-dlq"]:
        result = run_wrangler_command(["queues", "create", queue], check=False)
        if result.returncode == 0:
            print(f"    ✓ Queue created: {queue}")
        else:
            print(f"    ✗ Failed to create queue {queue}: {result.stderr}")

    return resources


def main():
    parser = argparse.ArgumentParser(
        description="Create a new Planet instance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode (prompts for all values)
  python scripts/create_instance.py

  # Quick setup with defaults
  python scripts/create_instance.py --id planet-python --name "Planet Python"

  # Copy from an existing example
  python scripts/create_instance.py --id my-planet --from-example planet-cloudflare

  # Create a lite mode instance (no search, no auth, simpler deployment)
  python scripts/create_instance.py --id planet-python --name "Planet Python" --lite

  # Create config AND deploy in one command (recommended)
  python scripts/create_instance.py --id planet-python --name "Planet Python" --deploy

  # Create config, deploy but skip secret prompts
  python scripts/create_instance.py --id planet-python --name "Planet Python" --deploy --skip-secrets

  # Full specification
  python scripts/create_instance.py \\
    --id planet-python \\
    --name "Planet Python" \\
    --description "Python community feed aggregator" \\
    --url "https://planetpython.org" \\
    --owner-name "Python Software Foundation" \\
    --owner-email "planet@python.org" \\
    --theme default

  # Dry run to preview what would be created
  python scripts/create_instance.py --id planet-python --name "Planet Python" --dry-run

  # Validate an existing configuration
  python scripts/create_instance.py --validate planet-python

Modes:
  --lite    Creates a simplified instance without:
            - Semantic search (no Vectorize index)
            - OAuth authentication (no secrets required)
            - Admin dashboard
            Ideal for simple public feed aggregators.

  --from-example  Copy from an existing example directory.
            Available examples: default, planet-cloudflare, planet-python, planet-mozilla
""",
    )

    parser.add_argument("--id", help="Instance ID (e.g., planet-python)")
    parser.add_argument("--name", help="Display name (e.g., Planet Python)")
    parser.add_argument("--description", help="Description/tagline")
    parser.add_argument("--url", help="Public URL")
    parser.add_argument("--owner-name", help="Owner/organization name")
    parser.add_argument("--owner-email", help="Contact email")
    parser.add_argument(
        "--theme",
        default="default",
        help="Theme to use (default: default). Built-in: default, planet-python, planet-mozilla.",
    )
    parser.add_argument(
        "--auto-provision",
        action="store_true",
        help="Automatically create Cloudflare resources (requires wrangler)",
    )
    parser.add_argument(
        "--deploy",
        action="store_true",
        help="Create config and run full deployment (calls deploy_instance.sh)",
    )
    parser.add_argument(
        "--skip-secrets",
        action="store_true",
        help="With --deploy: skip interactive secret prompts",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without actually creating files",
    )
    parser.add_argument(
        "--validate",
        metavar="INSTANCE_ID",
        help="Validate an existing instance configuration and exit",
    )
    parser.add_argument(
        "--lite",
        action="store_true",
        help="Create a lite mode instance (no search, no auth, simplified UI)",
    )
    parser.add_argument(
        "--mode",
        choices=["lite", "admin", "full"],
        default=None,
        help="Instance mode: lite (no search/auth), admin (auth but no search), full (all features)",
    )
    parser.add_argument(
        "--from-example",
        metavar="EXAMPLE",
        help="Copy from an existing example (default, planet-cloudflare, planet-python, planet-mozilla)",
    )

    args = parser.parse_args()

    # Handle --validate flag
    if args.validate:
        print(f"🔍 Validating configuration for: {args.validate}")
        result = validate_wrangler_config(args.validate)

        if result["issues"]:
            print("\n❌ Validation failed:")
            for issue in result["issues"]:
                print(f"  - {issue}")

        if result["warnings"]:
            print("\n⚠️  Warnings:")
            for warning in result["warnings"]:
                print(f"  {warning}")

        if result["valid"]:
            print("\n✅ Configuration is valid!")
            sys.exit(0)
        else:
            sys.exit(1)

    # Handle --from-example flag
    if args.from_example:
        if not args.id:
            print("Error: --id is required when using --from-example")
            sys.exit(1)

        source_dir = EXAMPLES_DIR / args.from_example
        if not source_dir.exists():
            available = [d.name for d in EXAMPLES_DIR.iterdir() if d.is_dir()]
            print(f"Error: Example '{args.from_example}' not found.")
            print(f"Available examples: {', '.join(sorted(available))}")
            sys.exit(1)

        target_dir = EXAMPLES_DIR / args.id
        if target_dir.exists():
            print(f"Error: Directory examples/{args.id} already exists.")
            sys.exit(1)

        import shutil

        print(f"📋 Copying from examples/{args.from_example}/ to examples/{args.id}/...")
        shutil.copytree(source_dir, target_dir)

        # Update the wrangler.jsonc with new instance ID
        wrangler_path = target_dir / "wrangler.jsonc"
        if wrangler_path.exists():
            content = wrangler_path.read_text()
            # Replace the example name with new instance ID
            content = content.replace(args.from_example, args.id)
            wrangler_path.write_text(content)
            print(f"  Updated wrangler.jsonc with instance ID: {args.id}")

        # Update the config.yaml with new instance ID
        config_path = target_dir / "config.yaml"
        if config_path.exists():
            content = config_path.read_text()
            content = content.replace(args.from_example, args.id)
            config_path.write_text(content)
            print(f"  Updated config.yaml with instance ID: {args.id}")

        # Create python_modules symlink (remove copied one first if it exists)
        symlink_path = target_dir / "python_modules"
        if symlink_path.exists() and not symlink_path.is_symlink():
            import shutil

            shutil.rmtree(symlink_path)
        create_python_modules_symlink(target_dir)

        print(f"\n✅ Created examples/{args.id}/ from {args.from_example}")
        print("\nNext steps:")
        print(f"  1. Edit examples/{args.id}/config.yaml to customize your instance")
        print(f"  2. Edit examples/{args.id}/wrangler.jsonc to update environment variables")
        print(f"  3. Deploy: ./scripts/deploy_instance.sh {args.id}")
        sys.exit(0)

    print("🌍 Planet Instance Creator")
    print("=" * 40)

    # Interactive mode if no ID provided
    if not args.id:
        print("\nEnter instance details (press Enter for defaults):\n")
        args.id = input("Instance ID [planet]: ").strip() or "planet"
        args.name = input(f"Display name [{args.id.replace('-', ' ').title()}]: ").strip()
        if not args.name:
            args.name = args.id.replace("-", " ").title()

    # Derive defaults from name if not provided
    slug = slugify(args.name) if args.name else args.id
    if not args.description:
        args.description = f"Feed aggregator for {args.name}"
    if not args.url:
        args.url = f"https://{slug}.example.com"
    if not args.owner_name:
        args.owner_name = args.name
    if not args.owner_email:
        args.owner_email = f"planet@{slug}.example.com"

    # Resolve mode: --mode takes precedence, --lite is shorthand for --mode lite
    if args.mode:
        resolved_mode = args.mode
    elif args.lite:
        resolved_mode = "lite"
    else:
        resolved_mode = "full"

    mode_label = resolved_mode.upper()
    print(f"\n📝 {'[DRY RUN] Would create' if args.dry_run else 'Creating'} instance: {args.name}")
    print(f"   ID: {args.id}")
    print(f"   URL: {args.url}")
    print(f"   Theme: {args.theme}")
    print(f"   Mode: {mode_label}")

    # Validate theme
    theme_valid, theme_msg = validate_theme(args.theme)
    if not theme_valid:
        print(f"\n⚠️  {theme_msg}")

    if args.dry_run:
        # Show what would be created without actually creating
        print("\n📁 Files that would be created:")
        print(f"   - examples/{args.id}/config.yaml")
        print(f"   - examples/{args.id}/wrangler.jsonc")
        print(f"   - examples/{args.id}/assets/static/")
        print(f"   - examples/{args.id}/python_modules -> ../../python_modules (symlink)")
        print("\n☁️  Cloudflare resources that would be needed:")
        print(f"   - D1 database: {args.id}-db")
        if resolved_mode == "full":
            print(f"   - Vectorize index: {args.id}-entries")
        print(f"   - Queue: {args.id}-feed-queue")
        print(f"   - Queue: {args.id}-feed-dlq")
        if resolved_mode != "lite":
            print("\n🔐 Secrets that would need to be configured:")
            print("   - GITHUB_CLIENT_ID")
            print("   - GITHUB_CLIENT_SECRET")
            print("   - SESSION_SECRET")
        else:
            print(f"\n🔐 No secrets required ({resolved_mode} mode)")
        print("\n✅ Dry run complete. No files were created.")
        return

    # Create instance config
    config_path = create_instance_config(
        instance_id=args.id,
        name=args.name,
        description=args.description,
        url=args.url,
        owner_name=args.owner_name,
        owner_email=args.owner_email,
        theme=args.theme,
        mode=resolved_mode,
    )
    print(f"\n✓ Created instance config: {config_path.relative_to(PROJECT_ROOT)}")

    # Generate wrangler config first (before provisioning, so we can update it)
    wrangler_path = generate_wrangler_config(
        instance_id=args.id,
        name=args.name,
        description=args.description,
        url=args.url,
        owner_name=args.owner_name,
        owner_email=args.owner_email,
        theme=args.theme,
        database_id="YOUR_DATABASE_ID",  # Will be updated by auto-provision
        mode=resolved_mode,
    )
    print(f"\n✓ Created wrangler config: {wrangler_path.relative_to(PROJECT_ROOT)}")

    # Create python_modules symlink
    print("\n📦 Setting up python_modules...")
    instance_dir = EXAMPLES_DIR / args.id
    create_python_modules_symlink(instance_dir)

    # Provision or print instructions (this may update wrangler config with database_id)
    resources = provision_cloudflare_resources(args.id, args.auto_provision, mode=resolved_mode)

    database_id = resources.get("database_id")
    if not database_id:
        print(f"\n⚠️  Update database_id in {wrangler_path.name} after creating the D1 database")

    print("\n✅ Instance created successfully!")

    # If --deploy flag is set, run the deploy script
    if args.deploy:
        print("\n🚀 Starting deployment...")
        deploy_script = SCRIPT_DIR / "deploy_instance.sh"
        if not deploy_script.exists():
            print(f"   ❌ Deploy script not found: {deploy_script}")
            sys.exit(1)

        deploy_cmd = [str(deploy_script), args.id]
        if args.skip_secrets:
            deploy_cmd.append("--skip-secrets")

        print(f"   Running: {' '.join(deploy_cmd)}")
        result = subprocess.run(deploy_cmd)
        sys.exit(result.returncode)

    # Print next steps for manual deployment
    print("\nNext steps:")
    print(f"  1. Edit {config_path.relative_to(PROJECT_ROOT)} to configure admins")
    if not args.auto_provision:
        print("\n  Option A: One-command deployment (recommended)")
        print(f"    ./scripts/deploy_instance.sh {args.id}")
        print("\n  Option B: Manual steps (see wrangler config file for details)")
        print(f"    npx wrangler deploy --config {wrangler_path.name}")
    else:
        print("  2. Set secrets (see provisioning steps above)")
        print(
            f"  3. Run migrations: npx wrangler d1 execute {args.id}-db "
            f"--remote --file migrations/001_initial.sql --config {wrangler_path.name}"
        )
        print(f"  4. Deploy: npx wrangler deploy --config {wrangler_path.name}")

    # Run validation at end
    print("\n📋 Configuration validation:")
    validation_result = validate_wrangler_config(args.id)
    if validation_result["valid"]:
        print("   ✓ Configuration is valid")
    else:
        for issue in validation_result["issues"]:
            print(f"   ✗ {issue}")


if __name__ == "__main__":
    main()
