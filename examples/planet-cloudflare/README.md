# Planet Cloudflare Example - Full Mode

This is the full-featured Planet CF deployment example. It includes all features: semantic search, admin interface, and OAuth authentication.

## Features

- RSS/Atom feed aggregation with hourly updates
- **Semantic search** powered by Vectorize and Workers AI
- **Admin interface** with GitHub OAuth authentication
- Queue-based feed fetching with automatic retries and dead-letter queue
- On-demand HTML/RSS/Atom/OPML generation with edge caching

## Included Files

- `config.yaml` - Instance configuration
- `wrangler.jsonc` - Cloudflare Workers configuration
- `theme/style.css` - Default theme CSS
- `static/` - Static assets (favicon, admin.js, etc.)

## Quick Start

### 1. Copy this example

```bash
cp -r examples/planet-cloudflare examples/my-planet
```

### 2. Update configuration

Edit `examples/my-planet/config.yaml` and `wrangler.jsonc`:
- Change instance ID, name, description, URL
- Update resource names (database, queues, vectorize index)

### 3. Deploy with the deploy script

```bash
./scripts/deploy_instance.sh my-planet
```

Or use the create script for a fresh start:

```bash
python scripts/create_instance.py --id my-planet --name "My Planet" --deploy
```

### 4. Manual Deployment (Alternative)

```bash
# Create D1 database
npx wrangler d1 create my-planet-db
# Copy the database_id to wrangler.jsonc

# Create Vectorize index
npx wrangler vectorize create my-planet-entries --dimensions 768 --metric cosine

# Create queues
npx wrangler queues create my-planet-feed-queue
npx wrangler queues create my-planet-feed-dlq

# Set secrets
npx wrangler secret put GITHUB_CLIENT_ID --config examples/my-planet/wrangler.jsonc
npx wrangler secret put GITHUB_CLIENT_SECRET --config examples/my-planet/wrangler.jsonc
npx wrangler secret put SESSION_SECRET --config examples/my-planet/wrangler.jsonc

# Run migrations
npx wrangler d1 execute my-planet-db --remote --file migrations/001_initial.sql

# Deploy
npx wrangler deploy --config examples/my-planet/wrangler.jsonc
```

## Customization

### Theme

To use a custom theme:

1. Edit `theme/style.css` with your styles
2. Rebuild templates: `python scripts/build_templates.py --example my-planet`
3. Redeploy

### Static Assets

Add custom static assets to the `static/` directory:
- `favicon.ico` - Browser favicon
- `apple-touch-icon.png` - iOS home screen icon
- Custom images or scripts

See the [Multi-Instance Guide](../../docs/MULTI_INSTANCE.md) for more details.
