# Default Example - Minimal Lite Mode

This is the minimal starting point for a new Planet CF instance. It runs in **lite mode**, which provides simple, read-only feed aggregation without semantic search or admin authentication.

## Features

- Simple feed aggregation with hourly updates
- No OAuth required (no admin interface)
- No Vectorize required (no semantic search)
- Minimal Cloudflare resources needed
- Version-controlled feed management via `assets/feeds.opml`

## Directory Structure

- `wrangler.jsonc` - Wrangler configuration with lite mode enabled
- `templates/` - HTML templates (index, search, titles, admin)
- `theme/` - Custom CSS styling
- `assets/` - Static assets served via Cloudflare's ASSETS binding
  - `feeds.opml` - Your feed list (edit this to add/remove feeds)
  - `static/` - Images, CSS, and other static files

## Quick Start

### 1. Copy this example

```bash
cp -r examples/default examples/my-planet
```

### 2. Update configuration

Edit `examples/my-planet/config.yaml`:
- Change `planet.id` to your instance ID
- Update `planet.name`, `description`, `url`
- Add feeds to `initial_feeds`

Edit `examples/my-planet/wrangler.jsonc`:
- Update worker name and environment variables
- Replace resource names with your instance ID

### 3. Create Cloudflare resources

```bash
# Create D1 database
npx wrangler d1 create my-planet-db
# Copy the database_id to wrangler.jsonc

# Create queues
npx wrangler queues create my-planet-feed-queue
npx wrangler queues create my-planet-feed-dlq
```

### 4. Run migrations

```bash
npx wrangler d1 execute my-planet-db --remote --file migrations/001_initial.sql
```

### 5. Deploy

```bash
npx wrangler deploy --config examples/my-planet/wrangler.jsonc
```

## Upgrading

### To Admin Mode (add web-based feed management)

1. Set OAuth secrets (`GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `SESSION_SECRET`)
2. Change `INSTANCE_MODE` from `"lite"` to `"admin"` in `wrangler.jsonc`
3. Redeploy

### To Full Mode (add semantic search)

Copy from `examples/planet-cloudflare/` instead, which includes Vectorize and AI bindings.

See the [Instance Modes Guide](../../docs/INSTANCE_MODES.md) for more details.
