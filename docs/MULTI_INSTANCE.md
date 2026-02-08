# Multi-Instance Deployment Guide

This guide explains how to deploy multiple Planet instances (like Planet Python, Planet PHP, Planet Ruby) using the examples-based architecture inspired by [Rogue Planet](https://github.com/adewale/rogue_planet).

## Overview

Planet CF supports configurable multi-instance deployment through the `examples/` directory:

- **Examples-Based Structure**: Each instance has its own directory in `examples/`
- **Ready-to-Deploy Instances**: Planet Python and Planet Mozilla included
- **Multiple Themes**: Per-instance templates in `examples/<id>/templates/`
- **OAuth Abstraction**: Support for GitHub OAuth (Google and custom OIDC not yet implemented)
- **CLI Tooling**: Scripts to provision and deploy new instances
- **One-Command Deployment**: Single script handles all Cloudflare resources

## Available Examples

| Example | Mode | Description |
|---------|------|-------------|
| `examples/default/` | lite | Minimal starting point, no search/auth |
| `examples/planet-cloudflare/` | full | Full-featured with search and admin |
| `examples/planet-python/` | lite | 500+ Python community feeds, no search/auth |
| `examples/planet-mozilla/` | lite | 190 Mozilla community feeds, no search/auth |
| `examples/test-planet/` | full | Test instance for CI/E2E testing |

## Quick Start

### Option A: Deploy an Existing Example

The fastest way to get started is to deploy one of the included examples:

```bash
# Deploy Planet Python (500+ feeds)
./scripts/deploy_instance.sh planet-python

# Deploy Planet Mozilla (190 feeds)
./scripts/deploy_instance.sh planet-mozilla

# Skip interactive secret prompts (set later)
./scripts/deploy_instance.sh planet-python --skip-secrets
```

### Option B: Copy from an Example

Create a new instance by copying from an existing example:

```bash
# Copy from planet-cloudflare (full-featured)
python scripts/create_instance.py \
  --id my-planet \
  --from-example planet-cloudflare

# Copy from default (minimal lite-mode)
python scripts/create_instance.py \
  --id my-planet \
  --from-example default

# Then deploy
./scripts/deploy_instance.sh my-planet
```

### Option C: Create from Scratch

Create a completely new instance:

```bash
# Create config and deploy everything
python scripts/create_instance.py \
  --id my-planet \
  --name "My Planet" \
  --deploy

# Or create a lite-mode instance (no search, no auth)
python scripts/create_instance.py \
  --id my-planet \
  --name "My Planet" \
  --lite \
  --deploy
```

This will:
1. Create `examples/my-planet/` directory with config and wrangler files
2. Create all Cloudflare resources (D1, Vectorize, Queues)
3. Auto-update database_id in wrangler config
4. Prompt for GitHub OAuth secrets (unless --lite)
5. Run database migrations
6. Deploy the worker

### Deploy Script Options

```
./scripts/deploy_instance.sh <instance-id> [options]

Options:
  --skip-secrets  Skip secret prompts (set later manually)
  --help, -h      Show help message
```

The script is idempotent - it safely skips resources that already exist, so you can re-run it if needed.

## Manual Deployment (Alternative)

If you prefer manual control:

### Create Instance Configuration

```bash
python scripts/create_instance.py \
  --id planet-python \
  --name "Planet Python" \
  --description "Python community feed aggregator" \
  --url "https://planetpython.org" \
  --owner-name "Python Software Foundation" \
  --owner-email "planet@python.org" \
  --theme default
```

This creates:
- `examples/planet-python/config.yaml` - Instance configuration
- `examples/planet-python/wrangler.jsonc` - Cloudflare Workers config
- `examples/planet-python/assets/` - Static assets directory (CSS, JS served at edge)

### Provision Cloudflare Resources Manually

```bash
# Create D1 database
npx wrangler d1 create planet-python-db
# Copy the database_id from output and update examples/planet-python/wrangler.jsonc

# Create Vectorize index
npx wrangler vectorize create planet-python-entries --dimensions 768 --metric cosine

# Create queues
npx wrangler queues create planet-python-feed-queue
npx wrangler queues create planet-python-feed-dlq

# Set secrets
npx wrangler secret put GITHUB_CLIENT_ID --config examples/planet-python/wrangler.jsonc
npx wrangler secret put GITHUB_CLIENT_SECRET --config examples/planet-python/wrangler.jsonc
npx wrangler secret put SESSION_SECRET --config examples/planet-python/wrangler.jsonc

# Run migrations
npx wrangler d1 execute planet-python-db \
  --remote \
  --file migrations/001_initial.sql \
  --config examples/planet-python/wrangler.jsonc

# Deploy
npx wrangler deploy --config examples/planet-python/wrangler.jsonc
```

## Before vs After Comparison

| Task | Before (Manual) | After (Automated) |
|------|-----------------|-------------------|
| Create D1 database | Run command, copy ID | Automatic |
| Update database_id | Manual edit | Automatic |
| Create Vectorize | Run command | Automatic |
| Create queues (2) | Run 2 commands | Automatic |
| Set secrets (3) | Run 3 commands | Interactive prompts |
| Run migrations | Run command | Automatic |
| Deploy | Run command | Automatic |
| **Total commands** | **8+ commands** | **1 command** |

## Configuration Reference

### Instance Configuration (YAML)

```yaml
# examples/planet-python/config.yaml

planet:
  id: planet-python
  name: Planet Python
  description: Python community feed aggregator
  url: https://planetpython.org
  owner:
    name: Python Software Foundation
    email: planet@python.org

branding:
  theme: default  # default, planet-python, planet-mozilla
  user_agent: "{name}/1.0 (+{url}; {email})"
  footer_text: "Powered by {name}"
  show_admin_link: true

content:
  days: 7
  group_by_date: true
  max_entries_per_feed: 100
  retention_days: 90

search:
  enabled: true
  embedding_max_chars: 2000
  score_threshold: 0.3
  top_k: 50

feeds:
  http_timeout_seconds: 30
  feed_timeout_seconds: 60
  auto_deactivate_threshold: 10

auth:
  provider: github
  scopes:
    - user:email
  session_ttl_seconds: 604800

admins:
  - username: guido
    display_name: Guido van Rossum
```

### Environment Variables

All configuration can be overridden via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `PLANET_NAME` | Display name | `Planet CF` |
| `PLANET_DESCRIPTION` | Tagline | `Aggregated posts from Cloudflare employees and community` |
| `PLANET_URL` | Public URL | - |
| `PLANET_OWNER_NAME` | Owner name | - |
| `THEME` | Theme name or path | `default` |
| `FOOTER_TEXT` | Footer message displayed at bottom of page | `Powered by Planet CF` |
| `SHOW_ADMIN_LINK` | Show admin link in footer (`true`/`false`) | Based on instance mode |
| `ENABLE_RSS10` | Enable RSS 1.0 feed format (`true`/`false`) | Theme-dependent |
| `ENABLE_FOAF` | Enable FOAF feed (`true`/`false`) | Theme-dependent |
| `HIDE_SIDEBAR_LINKS` | Hide sidebar RSS/titles links (`true`/`false`) | Theme-dependent |
| `RETENTION_DAYS` | Database retention | `90` |
| `GITHUB_CLIENT_ID` | GitHub OAuth app ID | (secret) |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth app secret | (secret) |
| `SESSION_SECRET` | Cookie signing key | (secret) |

## Themes

### Built-in Themes

| Theme | Description |
|-------|-------------|
| `default` | Modern, clean design with accent colors |
| `planet-python` | Planet Python theme with Python branding |
| `planet-mozilla` | Planet Mozilla theme with Mozilla branding |

### Using a Theme

Set in `wrangler.jsonc`:
```json
"vars": {
  "THEME": "planet-mozilla"
}
```

Or in instance config:
```yaml
branding:
  theme: planet-mozilla
```

### Creating Custom Themes

1. Create an instance with its assets directory:
```bash
python scripts/create_instance.py --id my-planet --name "My Planet" ...
```

2. Customize the CSS in `assets/static/style.css`:
```css
/* examples/my-planet/assets/static/style.css */
:root {
  --accent: #your-color;
  /* ... */
}
```

3. For custom HTML templates, add files to `examples/my-planet/templates/` and rebuild:
```bash
python scripts/build_templates.py --example my-planet
```

## OAuth Provider Configuration

### GitHub (Default)

```yaml
auth:
  provider: github
  scopes:
    - user:email
```

Required secrets:
- `GITHUB_CLIENT_ID`
- `GITHUB_CLIENT_SECRET`

### Google (NOT YET IMPLEMENTED)

> Google OAuth is not yet supported. Only GitHub OAuth is currently implemented.

### Custom OIDC (NOT YET IMPLEMENTED)

> Custom OIDC providers are not yet supported. Only GitHub OAuth is currently implemented.

## Comparison with Rogue Planet

| Feature | Rogue Planet | Planet CF |
|---------|--------------|-----------|
| Architecture | Static site generator | Dynamic Workers app |
| Config format | INI | YAML + env vars |
| Themes | 5 built-in | 3 built-in (default, planet-python, planet-mozilla) |
| Search | N/A | Semantic (Vectorize) |
| Auth | None | OAuth (GitHub) |
| Database | SQLite file | D1 (managed SQLite) |
| Deployment | Any web server | Cloudflare Workers |
| CLI | `rp` commands | Python scripts |

## Directory Structure

```
planet_cf/
├── examples/                    # Instance configurations
│   ├── default/                 # Minimal lite-mode template
│   │   ├── config.yaml
│   │   ├── wrangler.jsonc
│   │   ├── assets/
│   │   ├── templates/
│   │   └── README.md
│   ├── planet-cloudflare/       # Full-featured template
│   │   ├── config.yaml
│   │   ├── wrangler.jsonc
│   │   ├── assets/
│   │   └── README.md
│   ├── planet-python/           # Planet Python clone
│   │   ├── config.yaml          # 500+ feeds
│   │   ├── wrangler.jsonc
│   │   ├── assets/
│   │   ├── templates/
│   │   └── README.md
│   ├── planet-mozilla/          # Planet Mozilla clone
│   │   ├── config.yaml          # 190 feeds
│   │   ├── wrangler.jsonc
│   │   ├── assets/
│   │   ├── templates/
│   │   └── README.md
│   └── test-planet/             # Test instance for CI
│       ├── config.yaml
│       ├── wrangler.jsonc
│       └── assets/
├── scripts/
│   ├── create_instance.py       # Instance configuration generator
│   ├── deploy_instance.sh       # One-command deployment script
│   ├── build_templates.py       # Template compiler (--example flag)
│   └── seed_admins.py           # Admin seeding
├── src/
│   ├── instance_config.py       # Config loader
│   └── ...
├── wrangler.jsonc               # Root config for local dev
└── ...
```

## Migration from Single Instance

If you have an existing Planet CF deployment:

1. Your current config in `wrangler.jsonc` continues to work
2. The new system is backwards compatible
3. To add more instances, use `create_instance.py`

## Best Practices

1. **One instance per Cloudflare account** - Each instance needs its own D1, Vectorize, and Queues
2. **Use separate GitHub OAuth apps** - Each instance should have its own OAuth credentials
3. **Version control instance configs** - Keep `examples/<instance>/config.yaml` in git
4. **Don't commit secrets** - Use `wrangler secret put` for credentials
5. **Test themes locally** - Use `wrangler dev` before deploying

## Troubleshooting

### "Database not found"
Ensure you've created the D1 database and updated `database_id` in wrangler config.

### "OAuth redirect mismatch"
Set `OAUTH_REDIRECT_URI` to match your OAuth app's callback URL.

### Theme not loading
Run `python scripts/build_templates.py` to regenerate embedded templates.
