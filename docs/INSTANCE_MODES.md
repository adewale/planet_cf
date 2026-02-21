# Instance Modes

PlanetCF has three deployment modes: **Lite**, **Admin**, and **Full**. Each mode is a superset of the previous one.

| Mode | Search | Admin Dashboard | OAuth | Vectorize/AI | Free Plan? |
|------|--------|-----------------|-------|--------------|------------|
| **Lite** | No | No | No | Not used | Yes |
| **Admin** | No | Yes | Yes | Not used | Yes |
| **Full** | Yes | Yes | Yes | Required | No (Vectorize is paid) |

Set the mode via `INSTANCE_MODE` in `wrangler.jsonc`:

```json
"vars": {
  "INSTANCE_MODE": "admin"
}
```

## Cloudflare Resources by Mode

| Resource | Lite | Admin | Full | Free Plan? | Notes |
|----------|------|-------|------|------------|-------|
| **D1 Database** | Required | Required | Required | Yes | Stores feeds, entries, config |
| **Queues** | Required | Required | Required | Yes | Feed fetch job processing |
| **Workers** | Required | Required | Required | Yes (100k req/day) | Application runtime |
| **Vectorize** | Not used | Not used | Required | No | Semantic search embeddings |
| **Workers AI** | Not used | Not used | Required | Limited free tier | Generates text embeddings |
| **OAuth Secrets** | Not needed | Required | Required | N/A | GitHub auth credentials |

## Feature Comparison

| Feature | Lite | Admin | Full |
|---------|------|-------|------|
| Feed aggregation (hourly cron) | Yes | Yes | Yes |
| Homepage with entries | Yes | Yes | Yes |
| RSS/Atom output feeds | Yes | Yes | Yes |
| OPML export (`/feeds.opml`) | Yes | Yes | Yes |
| Entry retention policies | Yes | Yes | Yes |
| Dead letter queue processing | Yes | Yes | Yes |
| Custom themes | Yes | Yes | Yes |
| OAuth authentication | No | Yes | Yes |
| Admin dashboard | No | Yes | Yes |
| OPML import (via UI) | No | Yes | Yes |
| Feed health monitoring (via UI) | No | Yes | Yes |
| Audit log | No | Yes | Yes |
| Manual feed reindex | No | Yes | Yes |
| Semantic search | No | No | Yes |

## When to Choose Each Mode

**Choose Lite mode when:**
- You want a simple, free feed aggregator
- You manage feeds via version control (OPML file in git)
- You don't need search or an admin UI
- You want minimal infrastructure to maintain

**Choose Admin mode when:**
- You need a web-based admin dashboard to manage feeds
- Multiple maintainers need to add/remove feeds via the UI
- You want audit logging and feed health monitoring
- You don't need semantic search
- You want to stay on the Cloudflare Free Plan

**Choose Full mode when:**
- You need semantic search across entries
- You're willing to pay for Vectorize and Workers AI
- You want every feature available

## Admin Tasks by Mode

### Lite Mode — File-Based Management

In lite mode there is no admin dashboard. All management is done by editing configuration files and redeploying. This is the same workflow used by static site generators like Planet Venus and Rogue Planet.

#### Adding Feeds

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
  </body>
</opml>
```

Then redeploy:

```bash
npx wrangler deploy --config examples/my-planet/wrangler.jsonc
```

#### Removing Feeds

Remove the `<outline>` element from `assets/feeds.opml` and redeploy. Existing entries remain in the database until the retention policy deletes them.

#### Checking Feed Health

Without the admin dashboard, check feed status via D1 SQL:

```bash
npx wrangler d1 execute my-planet-db --remote \
  --command "SELECT title, consecutive_failures, fetch_error FROM feeds WHERE consecutive_failures > 0 ORDER BY consecutive_failures DESC"
```

### Admin Mode — Web-Based Management

In admin mode, the admin dashboard is available at `/admin`. Authenticated admins can:
- Add and remove feeds through the UI
- Import feeds from OPML files
- Monitor feed health and error rates
- View the audit log
- Trigger manual feed refreshes

Search is not available — the `/search` route returns a 404.

### Full Mode — All Features

Full mode adds semantic search to all admin-mode features. Entries are automatically embedded via Workers AI and indexed in Vectorize. Users can search across all aggregated content at `/search`.

## Upgrade Paths

### Lite to Admin

1. Set OAuth secrets:
   ```bash
   npx wrangler secret put GITHUB_CLIENT_ID --config examples/my-planet/wrangler.jsonc
   npx wrangler secret put GITHUB_CLIENT_SECRET --config examples/my-planet/wrangler.jsonc
   npx wrangler secret put SESSION_SECRET --config examples/my-planet/wrangler.jsonc
   ```
2. Seed admin users: `uv run python scripts/seed_admins.py`
3. Change `INSTANCE_MODE` from `"lite"` to `"admin"` in `wrangler.jsonc`
4. Redeploy: `npx wrangler deploy --config examples/my-planet/wrangler.jsonc`

### Admin to Full

1. Create the Vectorize index:
   ```bash
   npx wrangler vectorize create my-planet-entries --dimensions 768 --metric cosine
   ```
2. Add Vectorize and AI bindings to `wrangler.jsonc` (see `examples/planet-cloudflare/wrangler.jsonc` for reference)
3. Change `INSTANCE_MODE` from `"admin"` to `"full"`
4. Redeploy: `npx wrangler deploy --config examples/my-planet/wrangler.jsonc`

### Lite to Full (Direct)

Follow the Lite-to-Admin steps, then the Admin-to-Full steps. Or see the [Multi-Instance Guide](MULTI_INSTANCE.md) for the combined one-command approach.

## Downgrade Paths

### Full to Admin

1. Change `INSTANCE_MODE` from `"full"` to `"admin"` in `wrangler.jsonc`
2. Optionally remove the `vectorize` and `ai` sections from `wrangler.jsonc`
3. Redeploy

Existing search indices are preserved but unused. The `/search` route returns a 404.

### Admin to Lite

1. Change `INSTANCE_MODE` from `"admin"` to `"lite"`
2. Optionally remove OAuth secrets
3. Redeploy

The admin dashboard and auth routes return 404. Feed management reverts to file-based OPML editing.
