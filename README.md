# Planet CF

A feed aggregator built on Cloudflare's Python Workers platform.

## Features

- RSS/Atom feed aggregation with hourly updates
- Semantic search powered by Vectorize and Workers AI
- GitHub OAuth for admin authentication
- On-demand HTML/RSS/Atom/OPML generation with edge caching
- Queue-based feed fetching with automatic retries and dead-letter queue

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

## Architecture

- **Scheduler (cron):** Runs hourly, enqueues each feed as a separate queue message
- **Queue Consumer:** Fetches feeds with timeout protection, retries, and dead-lettering
- **HTTP Handler:** Generates HTML/RSS/Atom on-demand, cached at edge for 1 hour
- **Auth:** Stateless GitHub OAuth with HMAC-signed session cookies

## License

MIT
