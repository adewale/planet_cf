# Planet Cloudflare Example - Full Mode

This is the full-featured Planet CF deployment example. It includes all features: semantic search, admin interface, and OAuth authentication.

## Features

- RSS/Atom feed aggregation with hourly updates
- **Semantic search** powered by Vectorize and Workers AI
- **Admin interface** with GitHub OAuth authentication
- Queue-based feed fetching with automatic retries and dead-letter queue
- On-demand HTML/RSS/Atom/OPML generation with edge caching

## Included Files

- `config.yaml` - Documentation-only instance description (nothing reads it at deploy or runtime; the Worker reads `wrangler.jsonc` "vars")
- `wrangler.jsonc` - Cloudflare Workers configuration
- `assets/static/style.css` - Theme CSS (served at `/static/style.css`)
- `assets/static/` - Other static assets (favicons, `admin.js`, images)

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

# Run ALL migrations in order (not just 001)
for f in migrations/*.sql; do
  npx wrangler d1 execute my-planet-db --remote --file="$f"
done

# Deploy
npx wrangler deploy --config examples/my-planet/wrangler.jsonc
```

After deploying, the `feeds` table is empty until you seed it. Add feeds via the admin dashboard, or seed in bulk from an OPML file with `scripts/seed_feeds_from_opml.py`.

## Customization

### Theme

CSS is served straight from `assets/static/style.css` — edit that file and redeploy. There is no separate `theme/` directory and no build step for CSS (only the HTML templates are compiled into `src/templates.py`, and that is done from the canonical `templates/` sources, not per-example).

### Static Assets

Add custom static assets to the `assets/static/` directory:
- `favicon.ico` - Browser favicon
- `apple-touch-icon.png` - iOS home screen icon
- Custom images or scripts

See the [Multi-Instance Guide](../../docs/MULTI_INSTANCE.md) for more details.
