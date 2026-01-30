# Planet CF

A feed aggregator built on Cloudflare's Python Workers platform.

## Features

- RSS/Atom feed aggregation with hourly updates
- Semantic search powered by Vectorize and Workers AI
- GitHub OAuth for admin authentication
- On-demand HTML/RSS/Atom/OPML generation with edge caching
- Queue-based feed fetching with automatic retries and dead-letter queue

## Smart Defaults

Planet CF is designed to "just work" with minimal configuration, inspired by Rogue Planet's philosophy. Here are the smart defaults that make deployment easier:

### Content Display Fallback

When there are no entries in the configured display range (e.g., last 7 days), the homepage automatically shows the **50 most recent entries** instead of an empty page.

| Setting | Default | Override |
|---------|---------|----------|
| Display range | 7 days | `CONTENT_DAYS` |
| Fallback entries | 50 | Built-in constant |

### Feed Processing Defaults

Sensible defaults for reliable feed fetching:

| Setting | Default | Override |
|---------|---------|----------|
| HTTP timeout | 30 seconds | `HTTP_TIMEOUT_SECONDS` |
| Feed processing timeout | 60 seconds | `FEED_TIMEOUT_SECONDS` |
| Max entries per feed | 50 | `MAX_ENTRIES_PER_FEED` |
| Retry attempts | 3 | `FEED_FAILURE_THRESHOLD` |
| Retention period | 90 days | `RETENTION_DAYS` |
| Auto-deactivate after | 10 failures | `FEED_AUTO_DEACTIVATE_THRESHOLD` |

### Theme Fallback

If a specified theme doesn't exist, the build script gracefully falls back to the `default` theme instead of erroring. This prevents deployment failures due to theme misconfiguration.

```bash
# Even if 'my-custom-theme' doesn't exist, build succeeds with default theme
python scripts/build_templates.py --theme my-custom-theme
# Warning: Theme 'my-custom-theme' not found...
# Falling back to 'default' theme.
```

### Database Auto-Initialization

On first request, if the database tables don't exist, they are automatically created. This simplifies deployment by eliminating the need to manually run migrations for new instances.

**Note:** For production deployments, explicit migration via `wrangler d1 execute` is still recommended for version control.

### Configuration Defaults

All configuration values have sensible defaults so minimal setup works:

| Setting | Default | Notes |
|---------|---------|-------|
| Planet name | Derived from ID | `planet-python` becomes "Planet Python" |
| Planet description | "A feed aggregator" | `PLANET_DESCRIPTION` |
| Theme | `default` | `THEME` |
| Group by date | true | `GROUP_BY_DATE` |
| Show admin link | true | `SHOW_ADMIN_LINK` |
| Search enabled | true | `SEARCH_ENABLED` |

### Overriding Defaults

All defaults can be overridden via environment variables in `wrangler.jsonc`:

```jsonc
{
  "vars": {
    "PLANET_NAME": "My Custom Planet",
    "CONTENT_DAYS": "14",
    "RETENTION_DAYS": "180",
    "MAX_ENTRIES_PER_FEED": "100"
  }
}
```

Or via the `config/instance.yaml` for multi-instance deployments.

## Quick Start

### Prerequisites

- [Cloudflare account](https://dash.cloudflare.com/sign-up)
- [Node.js](https://nodejs.org/) (for wrangler CLI)
- [uv](https://docs.astral.sh/uv/) (Python package manager)

### 1. Clone and Install

```bash
git clone https://github.com/adewale/planet_cf.git
cd planet_cf
uv sync
npm install
```

### 2. Create Cloudflare Resources

```bash
# Create D1 database
npx wrangler d1 create planetcf

# Create Vectorize index
npx wrangler vectorize create planetcf-entries --dimensions=768 --metric=cosine

# Create queues
npx wrangler queues create planetcf-feed-queue
npx wrangler queues create planetcf-feed-dlq
```

Update `wrangler.jsonc` with your database ID from the output above.

### 3. Apply Database Migrations

```bash
npx wrangler d1 execute planetcf --remote --file=migrations/001_initial.sql
```

### 4. Set Up GitHub OAuth

1. Go to [GitHub Developer Settings](https://github.com/settings/developers)
2. Click "New OAuth App"
3. Fill in:
   - **Application name:** `Planet CF`
   - **Homepage URL:** `https://your-worker.workers.dev`
   - **Authorization callback URL:** `https://your-worker.workers.dev/auth/github/callback`
4. Copy the Client ID and generate a Client Secret

### 5. Configure Secrets

```bash
# GitHub OAuth credentials
npx wrangler secret put GITHUB_CLIENT_ID
# Enter your GitHub OAuth App Client ID

npx wrangler secret put GITHUB_CLIENT_SECRET
# Enter your GitHub OAuth App Client Secret

# Session signing key (generate a random 32-byte hex string)
openssl rand -hex 32
npx wrangler secret put SESSION_SECRET
# Paste the generated hex string
```

### 6. Add Admin User

Add yourself as an admin using your **GitHub username** (the login name that appears in your GitHub profile URL, e.g., `adewale` from `github.com/adewale`):

```bash
npx wrangler d1 execute planetcf --remote --command \
  "INSERT INTO admins (github_username, display_name, is_active) VALUES ('YOUR_GITHUB_USERNAME', 'Your Name', 1);"
```

**Format:** Use your exact GitHub login name without `@` or URL prefix:
- ✅ Correct: `adewale`
- ❌ Wrong: `@adewale`, `https://github.com/adewale`

### 7. Deploy

```bash
npx wrangler deploy
```

## Usage

### Public Pages

| URL | Description |
|-----|-------------|
| `/` | Main aggregated feed page |
| `/feed.atom` | Atom feed |
| `/feed.rss` | RSS feed |
| `/feeds.opml` | OPML export of all subscriptions |
| `/search?q=query` | Semantic search |

### Admin Pages

| URL | Description |
|-----|-------------|
| `/admin` | Admin dashboard (requires GitHub login) |

## Development

### Run Locally

```bash
# Start local development server
npx wrangler dev

# In another terminal, apply local migrations
npx wrangler d1 execute planetcf --local --file=migrations/001_initial.sql
```

### Run Tests

```bash
uv run pytest tests/ -v
```

### Lint

```bash
uvx ruff check src/
```

## Examples and Multi-Instance Deployment

Planet CF includes ready-to-deploy examples in the `examples/` directory:

| Example | Description |
|---------|-------------|
| `examples/default/` | Minimal lite-mode starting point |
| `examples/planet-cloudflare/` | Full-featured configuration |
| `examples/planet-python/` | Planet Python clone (500+ feeds) |
| `examples/planet-mozilla/` | Planet Mozilla clone (190 feeds) |

### Quick Start with Examples

```bash
# Deploy Planet Python
./scripts/deploy_instance.sh planet-python

# Create a new instance from an example
python scripts/create_instance.py --id my-planet --from-example planet-cloudflare

# Create a fresh instance
python scripts/create_instance.py \
  --id my-planet \
  --name "My Planet" \
  --deploy
```

The deploy script handles:
- Creating D1 database and auto-updating config
- Creating Vectorize index
- Creating queues
- Interactive prompts for GitHub OAuth secrets
- Running database migrations
- Deploying the worker

See [docs/MULTI_INSTANCE.md](docs/MULTI_INSTANCE.md) for detailed configuration options.

## Architecture

- **Scheduler (cron):** Runs hourly, enqueues each feed as a separate queue message
- **Queue Consumer:** Fetches feeds with timeout protection, retries, and dead-lettering
- **HTTP Handler:** Generates HTML/RSS/Atom on-demand, cached at edge for 1 hour
- **Auth:** Stateless GitHub OAuth with HMAC-signed session cookies

## License

MIT
