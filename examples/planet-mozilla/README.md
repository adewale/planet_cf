# Planet Mozilla Example

A comprehensive clone of [Planet Mozilla](https://planet.mozilla.org/), aggregating Mozilla community blogs and news.

## Features

- 190 Mozilla community feeds (from the original Planet Mozilla)
- Custom theme matching the classic planet.mozilla.org design
- Dark header, teal links, red accents
- Responsive design with dark mode support

## Included Files

- `config.yaml` - Full instance configuration with 190 feeds
- `wrangler.jsonc` - Cloudflare Workers configuration
- `theme/style.css` - Planet Mozilla theme CSS
- `static/mozilla-logo.svg` - Mozilla logo for header

## Quick Start

### Deploy with one command

```bash
./scripts/deploy_instance.sh planet-mozilla
```

### Or deploy manually

```bash
# Create D1 database
npx wrangler d1 create planet-mozilla-db
# Update database_id in wrangler.jsonc

# Create Vectorize index
npx wrangler vectorize create planet-mozilla-entries --dimensions 768 --metric cosine

# Create queues
npx wrangler queues create planet-mozilla-feed-queue
npx wrangler queues create planet-mozilla-feed-dlq

# Set secrets
npx wrangler secret put GITHUB_CLIENT_ID --config examples/planet-mozilla/wrangler.jsonc
npx wrangler secret put GITHUB_CLIENT_SECRET --config examples/planet-mozilla/wrangler.jsonc
npx wrangler secret put SESSION_SECRET --config examples/planet-mozilla/wrangler.jsonc

# Run migrations
npx wrangler d1 execute planet-mozilla-db --remote --file migrations/001_initial.sql

# Deploy
npx wrangler deploy --config examples/planet-mozilla/wrangler.jsonc
```

## Theme Details

The Planet Mozilla theme recreates the classic planet.mozilla.org design:

- **Layout**: Right sidebar with classic Planet style
- **Colors**: Teal links (#148cb5), red accents (#b72822), dark header
- **Typography**: Helvetica/Arial for body, Georgia for headings
- **Features**: Dark mode support, responsive design, accessibility focus

## Feed List

The config includes 190 Mozilla community feeds sourced from the original [Planet Mozilla config](https://github.com/mozilla-it/planet.mozilla.org/blob/master/configs/mozilla.ini), including:

- Official Mozilla blogs (Hacks, Security, Add-ons, etc.)
- Mozilla project blogs (Servo, Rust, SpiderMonkey, etc.)
- Individual Mozilla contributor blogs

## Customization

To customize:

1. Edit `theme/style.css` for visual changes
2. Edit `config.yaml` to modify feeds or branding
3. Rebuild templates: `python scripts/build_templates.py --example planet-mozilla`
4. Redeploy: `npx wrangler deploy --config examples/planet-mozilla/wrangler.jsonc`
