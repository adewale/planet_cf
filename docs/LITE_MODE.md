# Lite Mode Guide

PlanetCF has two deployment modes: **Full** and **Lite**. Lite mode is a read-only feed aggregator that runs entirely on Cloudflare's Free Plan. Full mode adds semantic search, an admin dashboard, and OAuth authentication, but requires paid Cloudflare services.

## Cloudflare Resources: Free vs Paid

| Resource | Lite Mode | Full Mode | Free Plan? | Notes |
|----------|-----------|-----------|------------|-------|
| **D1 Database** | Required | Required | Yes | Stores feeds, entries, config |
| **Queues** | Required | Required | Yes | Feed fetch job processing |
| **Workers** | Required | Required | Yes (100k req/day) | Application runtime |
| **Vectorize** | Not used | Required | No | Semantic search embeddings |
| **Workers AI** | Not used | Required | Limited (10k/day free) | Generates text embeddings |
| **OAuth Secrets** | Not needed | Required | N/A | GitHub/Google auth credentials |

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

In lite mode there is no admin dashboard. All management is done by editing configuration files and redeploying. This is the same workflow used by static site generators like Planet Venus and Rogue Planet.

### Adding Feeds

Edit `assets/feeds.opml` in your instance directory and redeploy:

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

Then redeploy:

```bash
npx wrangler deploy --config examples/my-planet/wrangler.jsonc
```

Alternatively, add feeds to `config.yaml`:

```yaml
initial_feeds:
  - url: https://blog.cloudflare.com/rss/
    title: Cloudflare Blog
  - url: https://github.blog/feed/
    title: GitHub Blog
```

New feeds are picked up on the next cron trigger (hourly) or on the next deployment.

### Removing Feeds

Remove the `<outline>` element from `assets/feeds.opml` (or the entry from `initial_feeds` in `config.yaml`) and redeploy. Existing entries from the removed feed remain in the database until the retention policy deletes them.

To immediately purge a feed's entries, run SQL directly:

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

If you have an OPML file from another aggregator, use it directly as your `assets/feeds.opml`:

```bash
cp exported-feeds.opml examples/my-planet/assets/feeds.opml
npx wrangler deploy --config examples/my-planet/wrangler.jsonc
```

### Changing Display Settings

Edit `config.yaml` or the `vars` section of `wrangler.jsonc`:

```yaml
# config.yaml
content:
  days: 14          # Show entries from last 14 days
  group_by_date: true

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
  "THEME": "dark"
}
```

Available built-in themes: `default`, `classic`, `dark`, `minimal`. You can also create a custom theme in `examples/my-planet/theme/style.css`.

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
2. Create the Vectorize index: `npx wrangler vectorize create my-planet-entries --dimensions 768 --metric cosine`
3. Set OAuth secrets: `npx wrangler secret put GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `SESSION_SECRET`
4. Change `INSTANCE_MODE` from `"lite"` to `"full"` in `wrangler.jsonc`
5. Seed admin users: `uv run python scripts/seed_admins.py`
6. Redeploy: `npx wrangler deploy --config examples/my-planet/wrangler.jsonc`

See the [Multi-Instance Guide](MULTI_INSTANCE.md) for full details.
