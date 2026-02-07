# CLI-First Administration Proposal for Planet CF

## Executive Summary

This document proposes a unified CLI tool (`planet`) for Planet CF administration, inspired by [Rogue Planet](https://github.com/adewale/rogue_planet)'s command-line interface design. The goal is to consolidate the existing scripts (`create_instance.py`, `deploy_instance.sh`, `build_templates.py`, `seed_admins.py`) into a cohesive, discoverable CLI that follows modern Python CLI conventions.

## Background and Motivation

### Current State

Planet CF currently has several standalone scripts in `scripts/`:

| Script | Purpose | Invocation |
|--------|---------|------------|
| `create_instance.py` | Initialize new instance configuration | `python scripts/create_instance.py --id ... --name ...` |
| `deploy_instance.sh` | Deploy instance to Cloudflare | `./scripts/deploy_instance.sh <instance-id>` |
| `build_templates.py` | Compile templates for Workers | `python scripts/build_templates.py --theme ...` |
| `seed_admins.py` | Seed admin users into D1 | `python scripts/seed_admins.py` |

**Problems with current approach:**
1. **Discoverability**: Users must read documentation to find available scripts
2. **Inconsistent interfaces**: Mix of Python and Bash with different argument styles
3. **No unified help**: Cannot run `--help` to see all available operations
4. **Instance context**: Must manually specify config files or instance IDs
5. **Missing operations**: No CLI for common tasks like adding/removing feeds

### Rogue Planet's Approach

Rogue Planet uses a single `rp` binary with hierarchical subcommands:

```
rp init              # Initialize a new planet
rp add-feed <url>    # Add a feed
rp remove-feed <url> # Remove a feed
rp list-feeds        # List all feeds
rp status            # Show status
rp update            # Fetch and regenerate
rp fetch             # Just fetch feeds
rp generate          # Just regenerate site
rp prune --days 30   # Clean old entries
rp import-opml <file># Import from OPML
rp export-opml       # Export to OPML
rp verify            # Validate configuration
rp version           # Show version
```

Key patterns:
- **Global `--config` flag**: Override config file for all commands
- **Consistent flags**: `--dry-run` for preview, `-f` for file input
- **Composable operations**: Separate `fetch` and `generate` that `update` combines
- **INI-based configuration**: Simple, human-readable config format

## Proposed CLI Design

### 1. Unified Entry Point

```bash
planet [OPTIONS] COMMAND [ARGS]...

Options:
  -i, --instance TEXT   Instance ID to operate on (default: auto-detect)
  -c, --config PATH     Path to config file (default: config/instances/<instance>.yaml)
  -v, --verbose         Enable verbose output
  --version             Show version and exit
  --help                Show help and exit
```

### 2. Command Structure

```
planet
├── init <instance-id>          # Initialize new instance
├── deploy <instance-id>        # Deploy instance to Cloudflare
├── status                      # Show instance status
├── validate                    # Validate configuration
├── build                       # Build templates
│
├── feed                        # Feed management
│   ├── add <url>               # Add a feed
│   ├── remove <url>            # Remove a feed
│   ├── list                    # List all feeds
│   ├── enable <id-or-url>      # Enable a feed
│   ├── disable <id-or-url>     # Disable a feed
│   ├── import <file>           # Import from OPML
│   └── export                  # Export to OPML
│
├── admin                       # Admin user management
│   ├── add <username>          # Add admin user
│   ├── remove <username>       # Remove admin user
│   ├── list                    # List admins
│   └── seed                    # Seed admins from config
│
├── db                          # Database operations
│   ├── migrate                 # Run migrations
│   ├── shell                   # Open D1 shell
│   └── prune --days N          # Remove old entries
│
├── search                      # Search index operations
│   └── reindex                 # Rebuild search index
│
└── logs                        # View worker logs
    └── tail                    # Stream logs
```

### 3. Detailed Command Specifications

#### 3.1 Instance Lifecycle Commands

```bash
# Initialize a new instance
planet init my-planet \
  --name "My Planet" \
  --description "Community feed aggregator" \
  --url "https://my-planet.example.com" \
  --owner-name "Planet Admin" \
  --owner-email "admin@example.com" \
  --theme default

# Options:
#   --name TEXT          Display name (default: derived from ID)
#   --description TEXT   Instance description
#   --url TEXT           Public URL
#   --owner-name TEXT    Owner name
#   --owner-email TEXT   Owner email
#   --theme TEXT         Theme to use [default|classic|dark|minimal|custom]
#   --dry-run            Preview without creating files
#   --force              Overwrite existing configuration

# Output:
# Created: config/instances/my-planet.yaml
# Created: wrangler.my-planet.jsonc
#
# Next steps:
#   planet deploy my-planet
```

```bash
# Deploy an instance
planet deploy my-planet

# Options:
#   --skip-secrets       Skip interactive secret prompts
#   --skip-migrations    Skip database migrations
#   --dry-run            Preview deployment steps
#   --force              Force redeploy even if up-to-date

# This replaces: ./scripts/deploy_instance.sh <instance-id>
```

```bash
# Check instance status
planet status

# Options:
#   --json               Output as JSON

# Output:
# Instance: my-planet
# Status: deployed
# URL: https://my-planet.example.com
#
# Resources:
#   Database: my-planet-db (connected)
#   Vectorize: my-planet-entries (768 dimensions)
#   Queue: my-planet-feed-queue (0 pending)
#   DLQ: my-planet-feed-dlq (2 failed)
#
# Feeds: 45 active, 3 disabled
# Entries: 1,234 (last 7 days)
# Admins: 2 configured
```

```bash
# Validate configuration
planet validate

# Options:
#   --strict             Fail on warnings too

# Output:
# Validating configuration for: my-planet
#
# [OK] Instance configuration valid
# [OK] Wrangler configuration valid
# [OK] Database ID configured
# [WARN] GITHUB_CLIENT_ID secret not set (required for OAuth)
#
# 1 warning(s) found
```

```bash
# Build templates with a theme
planet build --theme dark

# Options:
#   --theme TEXT         Theme to use
#   --list-themes        List available themes

# This replaces: python scripts/build_templates.py --theme ...
```

#### 3.2 Feed Management Commands

```bash
# Add a feed (local: writes to config file)
planet feed add https://example.com/feed.xml \
  --title "Example Blog" \
  --tags python,tutorial

# Options:
#   --title TEXT         Feed title (default: fetched from feed)
#   --tags TEXT          Comma-separated tags
#   --no-fetch           Don't fetch feed metadata
```

```bash
# Add a feed (remote: via API/D1)
planet feed add https://example.com/feed.xml --remote

# The --remote flag indicates this should use the admin API
# or direct D1 access instead of modifying config files
```

```bash
# Remove a feed
planet feed remove https://example.com/feed.xml
planet feed remove --id 42

# Options:
#   --id INT             Remove by feed ID
#   --remote             Remove from deployed instance
#   --keep-entries       Don't delete associated entries
```

```bash
# List all feeds
planet feed list

# Options:
#   --active             Only show active feeds
#   --disabled           Only show disabled feeds
#   --failing            Only show failing feeds
#   --format [table|json|csv]  Output format (default: table)
#   --remote             Query deployed instance

# Output:
# ID  Status   Failures  Title                    URL
# 1   active   0         Real Python              https://realpython.com/atom.xml
# 2   active   0         Python Insider           https://feeds.feedburner.com/...
# 3   disabled 5         Abandoned Blog           https://example.com/feed.xml
```

```bash
# Enable/disable feeds
planet feed enable 42
planet feed disable https://example.com/feed.xml

# Options:
#   --remote             Modify deployed instance
```

```bash
# Import feeds from OPML
planet feed import feeds.opml

# Options:
#   --dry-run            Preview without importing
#   --merge              Merge with existing feeds (default)
#   --replace            Replace all existing feeds
#   --remote             Import to deployed instance
```

```bash
# Export feeds to OPML
planet feed export > feeds.opml
planet feed export --output feeds.opml

# Options:
#   --output PATH        Output file (default: stdout)
#   --remote             Export from deployed instance
```

#### 3.3 Admin Management Commands

```bash
# Add an admin
planet admin add octocat --display-name "The Octocat"

# Options:
#   --display-name TEXT  Display name
#   --provider TEXT      OAuth provider (default: from config)
#   --remote             Add to deployed instance
```

```bash
# Remove an admin
planet admin remove octocat

# Options:
#   --remote             Remove from deployed instance
```

```bash
# List admins
planet admin list

# Options:
#   --format [table|json]  Output format
#   --remote               Query deployed instance
```

```bash
# Seed admins from configuration
planet admin seed

# This replaces: python scripts/seed_admins.py
# Reads from config/instances/<instance>.yaml
```

#### 3.4 Database Commands

```bash
# Run database migrations
planet db migrate

# Options:
#   --dry-run            Preview migrations
#   --force              Run even if already applied
```

```bash
# Open D1 shell for the instance
planet db shell

# Opens: npx wrangler d1 execute <db-name> --config <wrangler-config>
```

```bash
# Prune old entries
planet db prune --days 90

# Options:
#   --days INT           Delete entries older than N days (required)
#   --dry-run            Preview deletion count
#   --batch-size INT     Entries to delete per batch (default: 1000)
```

#### 3.5 Search Commands

```bash
# Rebuild search index
planet search reindex

# Options:
#   --batch-size INT     Entries to index per batch (default: 100)
#   --from-date DATE     Only reindex entries after this date

# This triggers the /admin/reindex endpoint or runs locally
```

#### 3.6 Log Commands

```bash
# Tail worker logs
planet logs tail

# Options:
#   --format [json|pretty]  Output format
#   --filter TEXT           Filter by message content

# Wraps: npx wrangler tail --config <wrangler-config>
```

### 4. Instance Context Resolution

The CLI needs to know which instance to operate on. Resolution order:

1. **Explicit flag**: `planet --instance my-planet status`
2. **Environment variable**: `PLANET_INSTANCE=my-planet planet status`
3. **Config file in current directory**: If `planet.yaml` or `instance.yaml` exists
4. **Single instance detection**: If only one instance in `config/instances/`
5. **Default**: Falls back to `planetcf` (the original default)

```python
# Implementation pseudocode
def resolve_instance(explicit: str | None) -> str:
    if explicit:
        return explicit

    if env := os.environ.get("PLANET_INSTANCE"):
        return env

    if Path("planet.yaml").exists():
        return load_yaml("planet.yaml")["planet"]["id"]

    instances = list(Path("config/instances").glob("*.yaml"))
    if len(instances) == 1:
        return instances[0].stem

    return "planetcf"
```

### 5. Local vs Remote Commands

Commands are categorized by where they operate:

| Category | Description | Examples |
|----------|-------------|----------|
| **Local** | Modify config files only | `init`, `validate`, `build`, `feed add` |
| **Remote** | Require deployed instance | `status`, `feed add --remote`, `admin seed` |
| **Hybrid** | Work locally or remotely | `feed list`, `admin list` |

**Remote command requirements:**
- Valid wrangler configuration with credentials
- Deployed worker accessible
- Either admin API access or `wrangler d1 execute` permissions

**Implementation approach:**
- Local commands modify YAML/JSONC files directly
- Remote commands use `wrangler d1 execute` for database operations
- Some operations can call the admin API if the worker is deployed

```python
# Remote command implementation pattern
def remote_command(func):
    """Decorator for commands that operate on deployed instances."""
    @wraps(func)
    def wrapper(ctx, *args, **kwargs):
        instance = ctx.obj["instance"]
        config_path = f"wrangler.{instance}.jsonc"

        if not Path(config_path).exists():
            raise click.ClickException(
                f"Instance {instance} not found. Run 'planet init {instance}' first."
            )

        # Verify deployment (optional)
        if not verify_deployed(instance):
            click.echo(f"Warning: Instance {instance} may not be deployed", err=True)

        ctx.obj["config_path"] = config_path
        return func(ctx, *args, **kwargs)
    return wrapper
```

## Implementation Approach

### 1. Recommended CLI Framework: Click

**Why Click over alternatives:**

| Framework | Pros | Cons |
|-----------|------|------|
| **Click** | Mature, composable, decorator-based, excellent docs | Slightly more verbose |
| Typer | Type hints for args, modern | Less flexible for complex CLIs |
| argparse | stdlib, no dependencies | Verbose, harder subcommand nesting |
| Fire | Auto-generates from functions | Less control over interface |

**Click advantages for Planet CF:**
- Subcommand groups (`planet feed add`, `planet admin list`)
- Context passing between commands
- Automatic help generation
- Plugin architecture (future extensibility)
- Well-suited for complex CLIs

### 2. Proposed File Structure

```
planet_cf/
├── cli/
│   ├── __init__.py          # Package init, exports main
│   ├── main.py              # Entry point, root command group
│   ├── context.py           # Shared context/state management
│   ├── utils.py             # Common utilities (output formatting, etc.)
│   │
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── init.py          # planet init
│   │   ├── deploy.py        # planet deploy
│   │   ├── status.py        # planet status
│   │   ├── validate.py      # planet validate
│   │   ├── build.py         # planet build
│   │   ├── feed.py          # planet feed *
│   │   ├── admin.py         # planet admin *
│   │   ├── db.py            # planet db *
│   │   ├── search.py        # planet search *
│   │   └── logs.py          # planet logs *
│   │
│   └── adapters/
│       ├── __init__.py
│       ├── config.py        # Config file read/write
│       ├── wrangler.py      # Wrangler CLI wrapper
│       └── d1.py            # D1 database operations
│
├── scripts/                  # Legacy scripts (deprecated, calls CLI)
│   ├── create_instance.py   # -> planet init
│   ├── deploy_instance.sh   # -> planet deploy
│   ├── build_templates.py   # -> planet build
│   └── seed_admins.py       # -> planet admin seed
```

### 3. Entry Point Configuration

Add to `pyproject.toml`:

```toml
[project.scripts]
planet = "cli.main:main"

[project.optional-dependencies]
cli = [
    "click>=8.1.0",
    "rich>=13.0.0",      # For beautiful terminal output
    "pyyaml>=6.0.0",     # For config file handling
]
```

### 4. Core Implementation

#### main.py - Entry Point

```python
# cli/main.py
"""Planet CF CLI - Command-line interface for Planet administration."""

import click
from cli.context import PlanetContext
from cli.commands import init, deploy, status, validate, build, feed, admin, db, search, logs


@click.group()
@click.option("-i", "--instance", help="Instance ID to operate on")
@click.option("-c", "--config", "config_path", type=click.Path(), help="Config file path")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output")
@click.version_option(package_name="planetcf")
@click.pass_context
def main(ctx: click.Context, instance: str | None, config_path: str | None, verbose: bool):
    """Planet CF - Feed aggregator administration CLI.

    Manage Planet instances, feeds, admins, and deployments from the command line.

    \b
    Examples:
      planet init my-planet --name "My Planet"
      planet deploy my-planet
      planet feed add https://example.com/feed.xml
      planet status
    """
    ctx.ensure_object(dict)
    ctx.obj = PlanetContext(
        instance=instance,
        config_path=config_path,
        verbose=verbose,
    )


# Register command groups
main.add_command(init.init)
main.add_command(deploy.deploy)
main.add_command(status.status)
main.add_command(validate.validate)
main.add_command(build.build)
main.add_command(feed.feed)
main.add_command(admin.admin)
main.add_command(db.db)
main.add_command(search.search)
main.add_command(logs.logs)


if __name__ == "__main__":
    main()
```

#### context.py - Shared Context

```python
# cli/context.py
"""Shared context and state management for CLI commands."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class PlanetContext:
    """Context object passed between CLI commands."""

    instance: str | None = None
    config_path: str | None = None
    verbose: bool = False

    _resolved_instance: str | None = field(default=None, repr=False)
    _config: dict[str, Any] | None = field(default=None, repr=False)

    @property
    def project_root(self) -> Path:
        """Find project root (directory containing pyproject.toml)."""
        current = Path.cwd()
        while current != current.parent:
            if (current / "pyproject.toml").exists():
                return current
            current = current.parent
        return Path.cwd()

    def resolve_instance(self) -> str:
        """Resolve which instance to operate on."""
        if self._resolved_instance:
            return self._resolved_instance

        # 1. Explicit argument
        if self.instance:
            self._resolved_instance = self.instance
            return self.instance

        # 2. Environment variable
        if env_instance := os.environ.get("PLANET_INSTANCE"):
            self._resolved_instance = env_instance
            return env_instance

        # 3. Local config file
        for config_name in ["planet.yaml", "instance.yaml"]:
            if (Path.cwd() / config_name).exists():
                config = yaml.safe_load((Path.cwd() / config_name).read_text())
                self._resolved_instance = config.get("planet", {}).get("id", "planetcf")
                return self._resolved_instance

        # 4. Single instance in config/instances/
        instances_dir = self.project_root / "config" / "instances"
        if instances_dir.exists():
            instances = list(instances_dir.glob("*.yaml"))
            if len(instances) == 1:
                self._resolved_instance = instances[0].stem
                return self._resolved_instance

        # 5. Default
        self._resolved_instance = "planetcf"
        return self._resolved_instance

    def get_config_path(self) -> Path:
        """Get path to instance configuration file."""
        if self.config_path:
            return Path(self.config_path)

        instance = self.resolve_instance()
        return self.project_root / "config" / "instances" / f"{instance}.yaml"

    def get_wrangler_config_path(self) -> Path:
        """Get path to wrangler configuration file."""
        instance = self.resolve_instance()
        # Default instance uses wrangler.jsonc, others use wrangler.<id>.jsonc
        if instance == "planetcf":
            return self.project_root / "wrangler.jsonc"
        return self.project_root / f"wrangler.{instance}.jsonc"

    def load_config(self) -> dict[str, Any]:
        """Load and cache instance configuration."""
        if self._config is not None:
            return self._config

        config_path = self.get_config_path()
        if not config_path.exists():
            self._config = {}
            return self._config

        self._config = yaml.safe_load(config_path.read_text())
        return self._config

    def echo(self, message: str, **kwargs):
        """Output message (respects verbose flag)."""
        click.echo(message, **kwargs)

    def echo_verbose(self, message: str, **kwargs):
        """Output message only if verbose mode is enabled."""
        if self.verbose:
            click.echo(message, **kwargs)
```

#### Example Command Implementation: feed.py

```python
# cli/commands/feed.py
"""Feed management commands."""

import click
from cli.context import PlanetContext
from cli.adapters.config import update_feeds_config
from cli.adapters.d1 import D1Client
from cli.utils import format_table, format_json


@click.group()
@click.pass_obj
def feed(ctx: PlanetContext):
    """Manage feeds for a Planet instance.

    \b
    Examples:
      planet feed list
      planet feed add https://example.com/feed.xml
      planet feed remove --id 42
      planet feed import feeds.opml
    """
    pass


@feed.command()
@click.argument("url")
@click.option("--title", help="Feed title (fetched from feed if not provided)")
@click.option("--tags", help="Comma-separated tags")
@click.option("--remote", is_flag=True, help="Add to deployed instance via D1")
@click.option("--no-fetch", is_flag=True, help="Don't fetch feed metadata")
@click.pass_obj
def add(ctx: PlanetContext, url: str, title: str | None, tags: str | None,
        remote: bool, no_fetch: bool):
    """Add a feed to the instance.

    By default, adds to the local configuration file. Use --remote to add
    directly to the deployed D1 database.

    \b
    Examples:
      planet feed add https://realpython.com/atom.xml
      planet feed add https://example.com/feed.xml --title "My Blog" --tags python,web
      planet feed add https://example.com/feed.xml --remote
    """
    instance = ctx.resolve_instance()
    ctx.echo(f"Adding feed to {instance}...")

    # Fetch metadata if needed
    if not no_fetch and not title:
        ctx.echo_verbose(f"Fetching feed metadata from {url}")
        title = fetch_feed_title(url)

    if remote:
        # Add via D1
        d1 = D1Client(ctx)
        feed_id = d1.insert_feed(url=url, title=title or url)
        ctx.echo(f"Added feed with ID {feed_id}")
    else:
        # Add to local config
        update_feeds_config(ctx, "add", url=url, title=title, tags=tags)
        ctx.echo(f"Added feed to configuration. Run 'planet deploy {instance}' to update.")


@feed.command()
@click.option("--id", "feed_id", type=int, help="Remove by feed ID")
@click.argument("url", required=False)
@click.option("--remote", is_flag=True, help="Remove from deployed instance")
@click.option("--keep-entries", is_flag=True, help="Don't delete associated entries")
@click.pass_obj
def remove(ctx: PlanetContext, feed_id: int | None, url: str | None,
           remote: bool, keep_entries: bool):
    """Remove a feed from the instance.

    Specify either a URL or --id to identify the feed.

    \b
    Examples:
      planet feed remove https://example.com/feed.xml
      planet feed remove --id 42
      planet feed remove --id 42 --keep-entries
    """
    if not feed_id and not url:
        raise click.UsageError("Must specify either URL or --id")

    instance = ctx.resolve_instance()

    if remote:
        d1 = D1Client(ctx)
        d1.delete_feed(feed_id=feed_id, url=url, keep_entries=keep_entries)
        ctx.echo(f"Removed feed from {instance}")
    else:
        update_feeds_config(ctx, "remove", feed_id=feed_id, url=url)
        ctx.echo(f"Removed feed from configuration.")


@feed.command("list")
@click.option("--active", is_flag=True, help="Only show active feeds")
@click.option("--disabled", is_flag=True, help="Only show disabled feeds")
@click.option("--failing", is_flag=True, help="Only show failing feeds")
@click.option("--format", "output_format", type=click.Choice(["table", "json", "csv"]),
              default="table", help="Output format")
@click.option("--remote", is_flag=True, help="Query deployed instance")
@click.pass_obj
def list_feeds(ctx: PlanetContext, active: bool, disabled: bool, failing: bool,
               output_format: str, remote: bool):
    """List all feeds in the instance.

    \b
    Examples:
      planet feed list
      planet feed list --failing
      planet feed list --format json
      planet feed list --remote
    """
    if remote:
        d1 = D1Client(ctx)
        feeds = d1.list_feeds(
            active_only=active,
            disabled_only=disabled,
            failing_only=failing,
        )
    else:
        config = ctx.load_config()
        feeds = config.get("initial_feeds", [])
        # Convert config format to common format
        feeds = [{"url": f["url"], "title": f.get("title", "")} for f in feeds]

    if output_format == "json":
        ctx.echo(format_json(feeds))
    elif output_format == "csv":
        ctx.echo(format_csv(feeds))
    else:
        ctx.echo(format_table(feeds, columns=["id", "status", "failures", "title", "url"]))


@feed.command("enable")
@click.argument("identifier")  # URL or ID
@click.option("--remote", is_flag=True, help="Modify deployed instance")
@click.pass_obj
def enable(ctx: PlanetContext, identifier: str, remote: bool):
    """Enable a disabled feed."""
    _toggle_feed(ctx, identifier, is_active=True, remote=remote)


@feed.command("disable")
@click.argument("identifier")
@click.option("--remote", is_flag=True, help="Modify deployed instance")
@click.pass_obj
def disable(ctx: PlanetContext, identifier: str, remote: bool):
    """Disable a feed (stops fetching)."""
    _toggle_feed(ctx, identifier, is_active=False, remote=remote)


def _toggle_feed(ctx: PlanetContext, identifier: str, is_active: bool, remote: bool):
    """Internal helper to enable/disable feeds."""
    action = "Enabled" if is_active else "Disabled"

    if remote:
        d1 = D1Client(ctx)
        d1.toggle_feed(identifier, is_active=is_active)
        ctx.echo(f"{action} feed: {identifier}")
    else:
        raise click.UsageError("Feed enable/disable requires --remote flag")


@feed.command("import")
@click.argument("file", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Preview without importing")
@click.option("--merge", is_flag=True, default=True, help="Merge with existing feeds")
@click.option("--replace", is_flag=True, help="Replace all existing feeds")
@click.option("--remote", is_flag=True, help="Import to deployed instance")
@click.pass_obj
def import_feeds(ctx: PlanetContext, file: str, dry_run: bool, merge: bool,
                 replace: bool, remote: bool):
    """Import feeds from an OPML file.

    \b
    Examples:
      planet feed import feeds.opml
      planet feed import feeds.opml --dry-run
      planet feed import feeds.opml --remote
    """
    from cli.adapters.opml import parse_opml

    feeds = parse_opml(file)
    ctx.echo(f"Found {len(feeds)} feeds in {file}")

    if dry_run:
        for feed in feeds:
            ctx.echo(f"  Would import: {feed['title']} ({feed['url']})")
        return

    if remote:
        d1 = D1Client(ctx)
        if replace:
            d1.clear_feeds()
        imported = d1.bulk_insert_feeds(feeds)
        ctx.echo(f"Imported {imported} feeds")
    else:
        update_feeds_config(ctx, "import", feeds=feeds, replace=replace)
        ctx.echo(f"Imported {len(feeds)} feeds to configuration")


@feed.command("export")
@click.option("--output", "-o", type=click.Path(), help="Output file (default: stdout)")
@click.option("--remote", is_flag=True, help="Export from deployed instance")
@click.pass_obj
def export_feeds(ctx: PlanetContext, output: str | None, remote: bool):
    """Export feeds to OPML format.

    \b
    Examples:
      planet feed export > feeds.opml
      planet feed export --output feeds.opml
      planet feed export --remote
    """
    from cli.adapters.opml import generate_opml

    if remote:
        d1 = D1Client(ctx)
        feeds = d1.list_feeds()
    else:
        config = ctx.load_config()
        feeds = config.get("initial_feeds", [])

    opml = generate_opml(feeds, ctx.load_config())

    if output:
        Path(output).write_text(opml)
        ctx.echo(f"Exported {len(feeds)} feeds to {output}")
    else:
        click.echo(opml)
```

#### D1 Adapter Implementation

```python
# cli/adapters/d1.py
"""D1 database operations via wrangler CLI."""

import json
import subprocess
from typing import Any

from cli.context import PlanetContext


class D1Client:
    """Client for D1 database operations using wrangler CLI."""

    def __init__(self, ctx: PlanetContext):
        self.ctx = ctx
        self.config_path = ctx.get_wrangler_config_path()
        self._db_name = None

    @property
    def db_name(self) -> str:
        """Get D1 database name from wrangler config."""
        if self._db_name:
            return self._db_name

        # Parse wrangler config to get database name
        config = json.loads(self.config_path.read_text())
        for db in config.get("d1_databases", []):
            if db.get("binding") == "DB":
                self._db_name = db["database_name"]
                return self._db_name

        # Fallback to instance-based naming
        instance = self.ctx.resolve_instance()
        self._db_name = f"{instance}-db"
        return self._db_name

    def execute(self, sql: str, params: list[Any] | None = None) -> dict:
        """Execute SQL query on D1 database."""
        cmd = [
            "npx", "wrangler", "d1", "execute", self.db_name,
            "--config", str(self.config_path),
            "--command", sql,
            "--json",
        ]

        self.ctx.echo_verbose(f"Executing: {' '.join(cmd)}")

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"D1 query failed: {result.stderr}")

        return json.loads(result.stdout)

    def list_feeds(self, active_only: bool = False, disabled_only: bool = False,
                   failing_only: bool = False) -> list[dict]:
        """List feeds from D1 database."""
        conditions = []
        if active_only:
            conditions.append("is_active = 1")
        if disabled_only:
            conditions.append("is_active = 0")
        if failing_only:
            conditions.append("consecutive_failures >= 3")

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        result = self.execute(
            f"SELECT id, url, title, is_active, consecutive_failures FROM feeds {where}"
        )

        return result.get("results", [])

    def insert_feed(self, url: str, title: str | None = None) -> int:
        """Insert a new feed."""
        result = self.execute(
            f"INSERT INTO feeds (url, title, is_active) VALUES ('{url}', '{title or url}', 1) RETURNING id"
        )
        return result["results"][0]["id"]

    def delete_feed(self, feed_id: int | None = None, url: str | None = None,
                    keep_entries: bool = False):
        """Delete a feed and optionally its entries."""
        if feed_id:
            condition = f"id = {feed_id}"
        elif url:
            condition = f"url = '{url}'"
        else:
            raise ValueError("Must specify feed_id or url")

        if not keep_entries:
            self.execute(f"DELETE FROM entries WHERE feed_id IN (SELECT id FROM feeds WHERE {condition})")

        self.execute(f"DELETE FROM feeds WHERE {condition}")

    def toggle_feed(self, identifier: str, is_active: bool):
        """Enable or disable a feed."""
        # Determine if identifier is ID (numeric) or URL
        try:
            feed_id = int(identifier)
            condition = f"id = {feed_id}"
        except ValueError:
            condition = f"url = '{identifier}'"

        self.execute(f"UPDATE feeds SET is_active = {1 if is_active else 0} WHERE {condition}")

    def bulk_insert_feeds(self, feeds: list[dict]) -> int:
        """Bulk insert feeds."""
        count = 0
        for feed in feeds:
            try:
                self.insert_feed(url=feed["url"], title=feed.get("title"))
                count += 1
            except Exception as e:
                self.ctx.echo_verbose(f"Failed to insert {feed['url']}: {e}")
        return count

    def clear_feeds(self):
        """Delete all feeds (for --replace import)."""
        self.execute("DELETE FROM entries")
        self.execute("DELETE FROM feeds")
```

## Example Usage Flows

### Flow 1: Creating and Deploying a New Instance

```bash
# 1. Initialize a new instance
$ planet init planet-python \
    --name "Planet Python" \
    --url "https://planetpython.org" \
    --theme planet-python

Creating instance: planet-python
  Created: config/instances/planet-python.yaml
  Created: wrangler.planet-python.jsonc

Next steps:
  1. Review configuration: config/instances/planet-python.yaml
  2. Deploy: planet deploy planet-python

# 2. Validate configuration
$ planet validate --instance planet-python

Validating: planet-python
  [OK] Instance configuration valid
  [OK] Wrangler configuration valid
  [WARN] database_id is placeholder (will be created during deploy)

# 3. Deploy the instance
$ planet deploy planet-python

Deploying planet-python...
  [1/6] Creating D1 database: planet-python-db
        Database ID: abc123-def456
        Updated wrangler configuration
  [2/6] Creating Vectorize index: planet-python-entries
  [3/6] Creating queues
        planet-python-feed-queue
        planet-python-feed-dlq
  [4/6] Configuring secrets
        Enter GITHUB_CLIENT_ID: ********
        Enter GITHUB_CLIENT_SECRET: ********
        Generated SESSION_SECRET
  [5/6] Running migrations
        001_initial.sql applied
  [6/6] Deploying worker

Deployment complete!
  URL: https://planet-python.workers.dev

# 4. Import initial feeds
$ planet feed import planet-python-feeds.opml --remote --instance planet-python

Found 561 feeds in planet-python-feeds.opml
Imported 561 feeds

# 5. Check status
$ planet status --instance planet-python

Instance: planet-python
Status: deployed
URL: https://planet-python.workers.dev

Resources:
  Database: planet-python-db (connected)
  Vectorize: planet-python-entries (ready)
  Queue: planet-python-feed-queue (0 pending)

Feeds: 561 active, 0 disabled
Entries: 0 (fetching on next cron)
Admins: 1 configured
```

### Flow 2: Managing Feeds

```bash
# List current feeds
$ planet feed list --remote

ID  Status   Failures  Title                    URL
1   active   0         Real Python              https://realpython.com/atom.xml
2   active   0         Python Insider           https://feeds.feedburner.com/...
3   disabled 5         Old Blog                 https://example.com/feed.xml
...

# Add a new feed
$ planet feed add https://nedbatchelder.com/blog/rss.xml --remote

Fetching feed metadata...
Added feed: "Ned Batchelder" (ID: 562)

# Disable a problematic feed
$ planet feed disable 3 --remote

Disabled feed: Old Blog

# Export feeds for backup
$ planet feed export --remote --output backup.opml

Exported 562 feeds to backup.opml

# Check failing feeds
$ planet feed list --failing --remote

ID  Status   Failures  Title           URL
47  active   5         Defunct Blog    https://defunct.example.com/feed
```

### Flow 3: Admin Management

```bash
# List current admins
$ planet admin list --remote

Username      Display Name         Provider  Active
octocat       The Octocat          github    yes
guido         Guido van Rossum     github    yes

# Add a new admin
$ planet admin add bdfl --display-name "Benevolent Dictator" --remote

Added admin: bdfl

# Seed admins from config (for new deployment)
$ planet admin seed

Seeding admins from config/instances/planet-python.yaml...
  [OK] Seeded: python (Python Software Foundation)

# Remove an admin
$ planet admin remove bdfl --remote

Removed admin: bdfl
```

### Flow 4: Database Operations

```bash
# Run migrations after schema update
$ planet db migrate

Running migrations on planet-python-db...
  001_initial.sql: already applied
  002_add_tags.sql: applying... done

# Prune old entries
$ planet db prune --days 90 --dry-run

Would delete 1,234 entries older than 90 days

$ planet db prune --days 90

Deleted 1,234 entries

# Open D1 shell for debugging
$ planet db shell

Opening D1 shell for planet-python-db...
> SELECT COUNT(*) FROM entries;
```

### Flow 5: Theme and Template Management

```bash
# List available themes
$ planet build --list-themes

Available themes:
  default     - Modern, clean design with accent colors
  classic     - Planet Venus-style with right sidebar
  dark        - Dark mode with vibrant accents
  minimal     - Typography-focused single column
  planet-python - Planet Python custom theme

# Build with a specific theme
$ planet build --theme dark

Building templates with theme: dark
  Generated src/templates.py
    - 9 templates

# Rebuild after editing templates
$ planet build

Building templates with theme: default
  Generated src/templates.py
```

## Migration Path

### Phase 1: CLI Foundation (Week 1-2)
1. Set up `cli/` package structure
2. Implement core context and utilities
3. Implement `planet init` (wraps `create_instance.py`)
4. Implement `planet deploy` (wraps `deploy_instance.sh`)
5. Implement `planet build` (wraps `build_templates.py`)

### Phase 2: Feed & Admin Commands (Week 3-4)
1. Implement D1 adapter
2. Implement `planet feed list/add/remove`
3. Implement `planet admin list/add/remove/seed`
4. Implement `planet status`

### Phase 3: Advanced Commands (Week 5-6)
1. Implement `planet feed import/export`
2. Implement `planet db migrate/prune`
3. Implement `planet search reindex`
4. Implement `planet logs tail`
5. Implement `planet validate`

### Phase 4: Polish & Deprecation (Week 7-8)
1. Add comprehensive help text
2. Add shell completion support
3. Update documentation
4. Add deprecation warnings to old scripts
5. Write migration guide

### Backwards Compatibility

During transition, existing scripts will continue to work but emit deprecation warnings:

```python
# scripts/create_instance.py
import warnings
import sys

warnings.warn(
    "create_instance.py is deprecated. Use 'planet init' instead.",
    DeprecationWarning,
    stacklevel=2
)

# Call CLI implementation
from cli.commands.init import init_command
sys.exit(init_command())
```

## Future Enhancements

### Plugin System
Allow third-party commands via entry points:

```toml
# In a plugin's pyproject.toml
[project.entry-points."planet.commands"]
my-command = "planet_myplugin.commands:my_command"
```

### Interactive Mode
Add an interactive REPL for exploring data:

```bash
$ planet shell

planet> feeds.list()
[561 feeds]

planet> feeds.search("python bytes")
[5 feeds matching]

planet> status()
Instance: planet-python
Feeds: 561 active
...
```

### Watch Mode
Auto-rebuild and deploy on file changes:

```bash
$ planet watch

Watching for changes...
  templates/index.html changed
  Rebuilding templates...
  Deploying...
  Done!
```

### Remote API Support
Instead of `wrangler d1 execute`, use authenticated admin API:

```bash
$ planet config set api-key <key>

$ planet feed list --remote  # Now uses /admin/api/feeds
```

## Appendix A: Click Patterns Reference

### Subcommand Groups
```python
@click.group()
def feed():
    """Feed management commands."""
    pass

@feed.command()
def add():
    pass
```

### Context Passing
```python
@click.pass_obj
def command(ctx: PlanetContext):
    instance = ctx.resolve_instance()
```

### Options and Arguments
```python
@click.option("--name", "-n", required=True, help="Instance name")
@click.option("--dry-run", is_flag=True, help="Preview changes")
@click.argument("instance_id")
def init(name: str, dry_run: bool, instance_id: str):
    pass
```

### Error Handling
```python
if not config_path.exists():
    raise click.ClickException(f"Config not found: {config_path}")

# Or with specific exit code
raise SystemExit(1)
```

### Progress Display
```python
with click.progressbar(feeds, label="Importing feeds") as bar:
    for feed in bar:
        import_feed(feed)
```

## Appendix B: Comparison with Other CLI Tools

| Feature | Planet CF (proposed) | Rogue Planet | Hugo | Jekyll |
|---------|---------------------|--------------|------|--------|
| Entry point | `planet` | `rp` | `hugo` | `jekyll` |
| Init command | `planet init` | `rp init` | `hugo new site` | `jekyll new` |
| Build command | `planet build` | `rp generate` | `hugo` | `jekyll build` |
| Deploy command | `planet deploy` | N/A | N/A | N/A |
| Config format | YAML | INI | TOML | YAML |
| Feed management | Yes | Yes | N/A | N/A |
| User management | Yes | No | N/A | N/A |
| Remote operations | Yes | No | No | No |

## Conclusion

This proposal outlines a comprehensive CLI-first approach for Planet CF administration that:

1. **Consolidates** existing scripts into a unified `planet` command
2. **Follows** established CLI patterns from Rogue Planet and modern Python tools
3. **Supports** both local configuration and remote instance management
4. **Enables** gradual migration while maintaining backwards compatibility
5. **Provides** extensibility for future enhancements

The implementation uses Click for its maturity and flexibility, with a modular command structure that maps naturally to Planet CF's domain model (instances, feeds, admins, etc.).

Estimated development time: 6-8 weeks for full implementation with testing and documentation.
