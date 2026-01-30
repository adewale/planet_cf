# Planet Python Example

A faithful clone of [Planet Python](https://planetpython.org/), the Python community feed aggregator.

## Features

- 500+ Python community feeds (from the original Planet Python)
- Custom theme matching the classic planetpython.org design
- Left sidebar layout with Python blue color scheme
- Georgia serif headings, classic blog aggregator style

## Included Files

- `config.yaml` - Full instance configuration with 561 feeds
- `wrangler.jsonc` - Cloudflare Workers configuration
- `theme/style.css` - Planet Python theme CSS
- `static/python-logo.svg` - Python logo for header

## Quick Start

### Deploy with one command

```bash
./scripts/deploy_instance.sh planet-python
```

### Or deploy manually

```bash
# Create D1 database
npx wrangler d1 create planet-python-db
# Update database_id in wrangler.jsonc

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
npx wrangler d1 execute planet-python-db --remote --file migrations/001_initial.sql

# Deploy
npx wrangler deploy --config examples/planet-python/wrangler.jsonc
```

## Theme Details

The Planet Python theme recreates the classic planetpython.org design:

- **Layout**: Left sidebar (classic Planet style)
- **Colors**: Python blue (#234764, #366D9C), yellow accents (#FFDB4C)
- **Typography**: Georgia serif for headings, Arial for body
- **Links**: Classic web blue (#0000AA) with purple visited state

## Feed List

The config includes 561 Python community feeds sourced from the original [Planet Python config](https://github.com/python/planet/blob/main/config/config.ini).

## Customization

To customize:

1. Edit `theme/style.css` for visual changes
2. Edit `config.yaml` to modify feeds or branding
3. Rebuild templates: `python scripts/build_templates.py --example planet-python`
4. Redeploy: `npx wrangler deploy --config examples/planet-python/wrangler.jsonc`
