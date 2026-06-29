# Default Example - Minimal Lite Mode

This is the minimal starting point for a new Planet CF instance. It runs in **lite mode**, which provides simple, read-only feed aggregation without semantic search or admin authentication.

## Features

- Simple feed aggregation with hourly updates
- No OAuth required (no admin interface)
- No Vectorize required (no semantic search)
- Minimal Cloudflare resources needed
- Version-controlled feed list via `assets/feeds.opml`, applied to D1 with `scripts/seed_feeds_from_opml.py`

## Directory Structure

- `wrangler.jsonc` - Wrangler configuration with lite mode enabled
- `config.yaml` - Documentation-only description of the instance (nothing reads it at deploy or runtime; the Worker reads `wrangler.jsonc` "vars")
- `assets/` - Static assets served via Cloudflare's ASSETS binding
  - `feeds.opml` - Your feed list (seed it into D1 with `scripts/seed_feeds_from_opml.py`; editing it does not change anything until you re-run the seeder)
  - `static/` - Images and CSS (e.g. `static/style.css`)

## Quick Start

### 1. Copy this example

```bash
cp -r examples/default examples/my-planet
```

### 2. Update configuration

Edit `examples/my-planet/wrangler.jsonc` (this is the file the Worker actually uses):
- Update the worker `name` and the `vars` (PLANET_NAME, PLANET_URL, etc.)
- Replace the D1 `database_name`/`database_id` and queue names with your own

(`config.yaml` is documentation only — changing it has no effect on the deployed Worker.)

### 3. Create Cloudflare resources

```bash
# Create D1 database
npx wrangler d1 create my-planet-db
# Copy the database_id into wrangler.jsonc

# Create queues
npx wrangler queues create my-planet-feed-queue
npx wrangler queues create my-planet-feed-dlq
```

### 4. Run migrations

Apply **all** migrations in order (not just `001`):

```bash
for f in migrations/*.sql; do
  npx wrangler d1 execute my-planet-db --remote --file="$f"
done
```

### 5. Seed your feeds

A freshly deployed instance has an empty `feeds` table and will show an empty page. Put your feeds in `examples/my-planet/assets/feeds.opml`, then seed them into D1:

```bash
uv run python scripts/seed_feeds_from_opml.py --config examples/my-planet/wrangler.jsonc
```

### 6. Deploy

```bash
npx wrangler deploy --config examples/my-planet/wrangler.jsonc
```

## Upgrading to Full Mode

To enable semantic search and admin interface, copy from `examples/planet-cloudflare/` instead, which includes:

- Vectorize binding for semantic search
- AI binding for embedding generation
- OAuth configuration for admin authentication

See the [Multi-Instance Guide](../../docs/MULTI_INSTANCE.md) for more details.
