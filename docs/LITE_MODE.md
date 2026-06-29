# Lite Mode Guide

Planet CF has two deployment modes: **Full** and **Lite**. Lite mode is a read-only feed aggregator that runs entirely on Cloudflare's Free Plan. Full mode adds semantic search, an admin dashboard, and OAuth authentication, but requires paid Cloudflare services.

## Cloudflare Resources: Free vs Paid

| Resource | Lite Mode | Full Mode | Free Plan? | Notes |
|----------|-----------|-----------|------------|-------|
| **D1 Database** | Required | Required | Yes | Stores feeds, entries, config |
| **Queues** | Required | Required | Yes | Feed fetch job processing |
| **Workers** | Required | Required | Yes (100k req/day) | Application runtime |
| **Vectorize** | Not used | Required | No | Semantic search embeddings |
| **Workers AI** | Not used | Required | Limited (10k/day free) | Generates text embeddings |
| **OAuth Secrets** | Not needed | Required | N/A | GitHub OAuth credentials (only GitHub is implemented) |

Lite mode removes Vectorize and Workers AI bindings entirely from the wrangler config, so these services are never called. Route guards at the application layer return 404 for `/search`, `/auth/*`, and `/admin/*` routes, ensuring no paid-tier code paths execute.

## Feature Comparison

| Feature | Lite Mode | Full Mode |
|---------|-----------|-----------|
| Feed aggregation (hourly cron) | Yes | Yes |
| Homepage with entries | Yes | Yes |
| RSS/Atom output feeds | Yes | Yes |
| OPML export (`/feeds.opml`) | Yes | Yes |
| Entry retention policies | Yes | Yes |
| Dead letter queue processing | Yes | Yes |
| Custom themes | Yes | Yes |
| Semantic search | No | Yes |
| Admin dashboard | No | Yes |
| OAuth authentication | No | Yes |
| OPML import (via UI) | No | Yes |
| Feed health monitoring (via UI) | No | Yes |
| Audit log | No | Yes |
| Manual reindex | No | Yes |

## Admin Tasks in Lite Mode

In lite mode there is no admin dashboard. Feeds live as rows in the D1 `feeds` table, exactly as in full mode — there is **no** deploy-time or cron-time import of feeds from any file. Deploying a fresh lite instance yields an empty planet until you seed feeds into D1.

The supported way to manage the feed list under version control is to keep an OPML file at `assets/feeds.opml` in your instance directory and run **`scripts/seed_feeds_from_opml.py`** whenever it changes. The script reads your `wrangler.jsonc`, detects `INSTANCE_MODE: "lite"`, loads `assets/feeds.opml` from the same directory, and upserts each feed into D1 (`ON CONFLICT(url) DO UPDATE`). This is an explicit step you run — redeploying the worker does **not** trigger it.

### Adding Feeds

1. Edit `assets/feeds.opml` in your instance directory:

```xml
<!-- examples/my-planet/assets/feeds.opml -->
<opml version="2.0">
  <head>
    <title>My Planet Feeds</title>
  </head>
  <body>
    <outline type="rss" text="Cloudflare Blog"
             xmlUrl="https://blog.cloudflare.com/rss/"
             htmlUrl="https://blog.cloudflare.com"/>
    <outline type="rss" text="GitHub Blog"
             xmlUrl="https://github.blog/feed/"
             htmlUrl="https://github.blog"/>
  </body>
</opml>
```

2. Seed the feeds into D1 (preview first with `--dry-run`):

```bash
# Reads INSTANCE_MODE/database name from the config; loads assets/feeds.opml in lite mode
uv run python scripts/seed_feeds_from_opml.py \
  --config examples/my-planet/wrangler.jsonc --dry-run

uv run python scripts/seed_feeds_from_opml.py \
  --config examples/my-planet/wrangler.jsonc
```

You only need to redeploy the worker when the **code or config** changes — not when the feed list changes. New feeds start being fetched on the next hourly cron after they are inserted (requires a cron-enabled config; see the deployment guide).

### Removing Feeds

The seeding script only adds/updates feeds; it never deletes. Re-running it after removing an `<outline>` from `assets/feeds.opml` leaves the old feed in D1. To remove a feed, deactivate or delete it directly with SQL (below). Existing entries from a removed feed remain until the retention policy deletes them.

To deactivate or purge a feed's entries, run SQL directly:

```bash
# Find the feed ID
npx wrangler d1 execute my-planet-db --remote \
  --command "SELECT id, title FROM feeds WHERE url = 'https://example.com/feed.xml'"

# Deactivate the feed
npx wrangler d1 execute my-planet-db --remote \
  --command "UPDATE feeds SET is_active = 0 WHERE id = <FEED_ID>"

# Optionally delete its entries
npx wrangler d1 execute my-planet-db --remote \
  --command "DELETE FROM entries WHERE feed_id = <FEED_ID>"
```

### Bulk Import from OPML

If you have an OPML file from another aggregator, drop it in as your `assets/feeds.opml` and seed it into D1:

```bash
cp exported-feeds.opml examples/my-planet/assets/feeds.opml
uv run python scripts/seed_feeds_from_opml.py --config examples/my-planet/wrangler.jsonc
```

You can also point the script straight at a URL or file without touching `assets/feeds.opml`:

```bash
uv run python scripts/seed_feeds_from_opml.py \
  --url https://planetpython.org/opml.xml --db my-planet-db
```

### Changing Display Settings

Edit `config.yaml` or the `vars` section of `wrangler.jsonc`:

```yaml
# config.yaml
content:
  days: 14          # Show entries from last 14 days

# Or in wrangler.jsonc vars:
# "CONTENT_DAYS": "14"
# "RETENTION_DAYS": "90"
# "RETENTION_MAX_ENTRIES_PER_FEED": "100"
```

Redeploy to apply changes.

### Changing the Theme

Set the `THEME` variable in `wrangler.jsonc`:

```json
"vars": {
  "THEME": "planet-python"
}
```

Available built-in themes: `default`, `planet-python`, `planet-mozilla` (an unknown value falls back to `default`). To customize the look, edit your instance's stylesheet at `examples/my-planet/assets/static/style.css` — that is the file Cloudflare's Static Assets serves at `/static/style.css`. There is no separate `theme/` directory.

### Checking Feed Health

Without the admin dashboard, check feed status via D1 SQL:

```bash
# List all feeds and their status
npx wrangler d1 execute my-planet-db --remote \
  --command "SELECT id, title, is_active, consecutive_failures, last_fetch_at, fetch_error FROM feeds ORDER BY title"

# Show only failing feeds
npx wrangler d1 execute my-planet-db --remote \
  --command "SELECT title, consecutive_failures, fetch_error FROM feeds WHERE consecutive_failures > 0 ORDER BY consecutive_failures DESC"
```

### Retrying Failed Feeds

Reset a feed's failure counter so it gets picked up on the next cron:

```bash
npx wrangler d1 execute my-planet-db --remote \
  --command "UPDATE feeds SET consecutive_failures = 0, is_active = 1 WHERE id = <FEED_ID>"
```

### Viewing Recent Entries

```bash
npx wrangler d1 execute my-planet-db --remote \
  --command "SELECT title, author, published_at FROM entries ORDER BY published_at DESC LIMIT 20"
```

## Lite vs Full: When to Choose Each

**Choose Lite mode when:**
- You want a simple, free feed aggregator
- You manage feeds via version control (OPML file in git)
- You don't need search or an admin UI
- You want minimal infrastructure to maintain

**Choose Full mode when:**
- You need semantic search across entries
- You want a web-based admin dashboard
- Multiple admins need to manage feeds
- You want audit logging and feed health monitoring

## Upgrading from Lite to Full

To upgrade an existing lite instance to full mode:

1. Add Vectorize and AI bindings to `wrangler.jsonc` (see `examples/planet-cloudflare/wrangler.jsonc` for reference)
2. Create the Vectorize index: `npx wrangler vectorize create my-planet-entries --dimensions 768 --metric cosine` (768 dimensions must match the Workers AI model, currently `@cf/baai/bge-base-en-v1.5`)
3. Set OAuth secrets: `npx wrangler secret put GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `SESSION_SECRET`
4. Change `INSTANCE_MODE` from `"lite"` to `"full"` in `wrangler.jsonc`
5. Seed admin users: `uv run python scripts/seed_admins.py`
6. Redeploy: `npx wrangler deploy --config examples/my-planet/wrangler.jsonc`

See the [Multi-Instance Guide](MULTI_INSTANCE.md) for full details.
