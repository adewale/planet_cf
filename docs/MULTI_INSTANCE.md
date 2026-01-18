# Multi-Instance Deployment Guide

This guide explains how to deploy multiple Planet instances (like Planet Python, Planet PHP, Planet Ruby) using the configurable architecture inspired by [Rogue Planet](https://github.com/adewale/rogue_planet).

## Overview

Planet CF now supports configurable multi-instance deployment:

- **Instance Configuration**: YAML-based configuration per instance
- **Multiple Themes**: 4 built-in themes (default, classic, dark, minimal)
- **OAuth Abstraction**: Support for GitHub, Google, and custom OIDC providers
- **CLI Tooling**: Scripts to provision new instances

## Quick Start

### Create a New Instance

```bash
# Interactive mode
python scripts/create_instance.py

# Or with arguments
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
- `config/instances/planet-python.yaml` - Instance configuration
- `wrangler.planet-python.jsonc` - Cloudflare Workers config

### Provision Cloudflare Resources

```bash
# Create D1 database
npx wrangler d1 create planet-python-db

# Create Vectorize index
npx wrangler vectorize create planet-python-entries --dimensions 768 --metric cosine

# Create queues
npx wrangler queues create planet-python-feed-queue
npx wrangler queues create planet-python-feed-dlq

# Set secrets
npx wrangler secret put GITHUB_CLIENT_ID --config wrangler.planet-python.jsonc
npx wrangler secret put GITHUB_CLIENT_SECRET --config wrangler.planet-python.jsonc
npx wrangler secret put SESSION_SECRET --config wrangler.planet-python.jsonc

# Run migrations
npx wrangler d1 execute planet-python-db \
  --file migrations/001_initial.sql \
  --config wrangler.planet-python.jsonc

# Deploy
npx wrangler deploy --config wrangler.planet-python.jsonc
```

## Configuration Reference

### Instance Configuration (YAML)

```yaml
# config/instances/planet-python.yaml

planet:
  id: planet-python
  name: Planet Python
  description: Python community feed aggregator
  url: https://planetpython.org
  owner:
    name: Python Software Foundation
    email: planet@python.org

branding:
  theme: default  # default, classic, dark, minimal
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
  provider: github  # or google, oidc
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
| `PLANET_ID` | Instance identifier | `planet` |
| `PLANET_NAME` | Display name | `Planet` |
| `PLANET_DESCRIPTION` | Tagline | `A feed aggregator` |
| `PLANET_URL` | Public URL | - |
| `PLANET_OWNER_NAME` | Owner name | - |
| `PLANET_OWNER_EMAIL` | Contact email | - |
| `THEME` | Theme name or path | `default` |
| `USER_AGENT_TEMPLATE` | Feed fetcher UA | `{name}/1.0 (+{url}; {email})` |
| `FOOTER_TEXT` | Footer message | `Powered by {name}` |
| `CONTENT_DAYS` | Days of entries to show | `7` |
| `RETENTION_DAYS` | Database retention | `90` |
| `OAUTH_PROVIDER` | Auth provider | `github` |
| `OAUTH_CLIENT_ID` | OAuth app ID | (secret) |
| `OAUTH_CLIENT_SECRET` | OAuth app secret | (secret) |
| `SESSION_SECRET` | Cookie signing key | (secret) |

## Themes

### Built-in Themes

| Theme | Description |
|-------|-------------|
| `default` | Modern, clean design with accent colors |
| `classic` | Planet Venus-style with right sidebar |
| `dark` | Dark mode with vibrant accents |
| `minimal` | Typography-focused single column |

### Using a Theme

Set in `wrangler.jsonc`:
```json
"vars": {
  "THEME": "dark"
}
```

Or in instance config:
```yaml
branding:
  theme: dark
```

### Creating Custom Themes

1. Create a theme directory:
```bash
mkdir -p themes/my-theme
```

2. Add your CSS:
```bash
# themes/my-theme/style.css
:root {
  --accent: #your-color;
  /* ... */
}
```

3. Reference in config:
```yaml
branding:
  theme: my-theme
```

4. Rebuild templates:
```bash
python scripts/build_templates.py --theme my-theme
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

### Google

```yaml
auth:
  provider: google
  scopes:
    - email
    - profile
```

Required secrets:
- `OAUTH_CLIENT_ID`
- `OAUTH_CLIENT_SECRET`

### Custom OIDC

```yaml
auth:
  provider: oidc
  authorize_url: https://your-idp.com/authorize
  token_url: https://your-idp.com/token
  user_info_url: https://your-idp.com/userinfo
  scopes:
    - openid
    - email
```

## Comparison with Rogue Planet

| Feature | Rogue Planet | Planet CF |
|---------|--------------|-----------|
| Architecture | Static site generator | Dynamic Workers app |
| Config format | INI | YAML + env vars |
| Themes | 5 built-in | 4 built-in |
| Search | N/A | Semantic (Vectorize) |
| Auth | None | OAuth (GitHub, Google) |
| Database | SQLite file | D1 (managed SQLite) |
| Deployment | Any web server | Cloudflare Workers |
| CLI | `rp` commands | Python scripts |

## Directory Structure

```
planet_cf/
├── config/
│   ├── instance.example.yaml    # Template for new instances
│   └── instances/               # Instance-specific configs
│       ├── planetcf.yaml
│       └── planet-python.yaml
├── themes/
│   ├── default/style.css
│   ├── classic/style.css
│   ├── dark/style.css
│   └── minimal/style.css
├── scripts/
│   ├── create_instance.py       # Instance provisioning
│   ├── build_templates.py       # Template compiler
│   └── seed_admins.py           # Admin seeding
├── src/
│   ├── instance_config.py       # Config loader
│   └── ...
├── wrangler.jsonc               # Default instance
├── wrangler.planet-python.jsonc # Per-instance configs
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
3. **Version control instance configs** - Keep `config/instances/*.yaml` in git
4. **Don't commit secrets** - Use `wrangler secret put` for credentials
5. **Test themes locally** - Use `wrangler dev` before deploying

## Troubleshooting

### "Database not found"
Ensure you've created the D1 database and updated `database_id` in wrangler config.

### "OAuth redirect mismatch"
Set `OAUTH_REDIRECT_URI` to match your OAuth app's callback URL.

### Theme not loading
Run `python scripts/build_templates.py` to regenerate embedded templates.
