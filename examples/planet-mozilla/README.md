# Planet Mozilla Example

A comprehensive clone of [Planet Mozilla](https://planet.mozilla.org/), aggregating Mozilla community blogs and news.

> **This example runs in lite mode** (`INSTANCE_MODE: "lite"`): no semantic search, no admin dashboard, no OAuth. Its `wrangler.jsonc` has **no** Vectorize or AI bindings, so do not create a Vectorize index or set OAuth secrets for it.

## Features

- 207 Mozilla community feeds (from the original Planet Mozilla)
- Custom theme matching the classic planet.mozilla.org design
- Dark header, teal links, red accents
- Responsive design with dark mode support

## Included Files

- `config.yaml` - Documentation-only description of the instance and its feed list (nothing reads it at deploy or runtime)
- `wrangler.jsonc` - Cloudflare Workers configuration (lite mode)
- `assets/static/style.css` - Planet Mozilla theme CSS
- `assets/static/mozilla-logo.svg` - Mozilla logo for header
- `assets/static/fonts/` - Self-hosted Mozilla WOFF2 fonts used by the theme
- `assets/feeds.opml` - the feed list, applied to D1 via `scripts/seed_feeds_from_opml.py`

## Quick Start

### Deploy with one command

```bash
./scripts/deploy_instance.sh planet-mozilla
```

Then seed the feeds (a fresh deploy starts with an empty page):

```bash
uv run python scripts/seed_feeds_from_opml.py --config examples/planet-mozilla/wrangler.jsonc
```

### Or deploy manually

```bash
# Create D1 database
npx wrangler d1 create planet-mozilla-db
# Update database_id in wrangler.jsonc

# Create queues
npx wrangler queues create planet-mozilla-feed-queue
npx wrangler queues create planet-mozilla-feed-dlq

# Run ALL migrations in order (not just 001)
for f in migrations/*.sql; do
  npx wrangler d1 execute planet-mozilla-db --remote --file="$f"
done

# Deploy
npx wrangler deploy --config examples/planet-mozilla/wrangler.jsonc

# Seed feeds into D1 (lite mode reads assets/feeds.opml)
uv run python scripts/seed_feeds_from_opml.py --config examples/planet-mozilla/wrangler.jsonc
```

## Theme Details

The Planet Mozilla theme recreates the classic planet.mozilla.org design:

- **Layout**: Right sidebar with classic Planet style
- **Colors**: Teal links (#148cb5), red accents (#b72822), dark header
- **Typography**: Helvetica/Arial for body, Georgia for headings
- **Features**: Dark mode support, responsive design, accessibility focus

## Feed List

`assets/feeds.opml` contains 207 Mozilla community feeds sourced from the original [Planet Mozilla config](https://github.com/mozilla-it/planet.mozilla.org/blob/master/configs/mozilla.ini), including:

- Official Mozilla blogs (Hacks, Security, Add-ons, etc.)
- Mozilla project blogs (Servo, Rust, SpiderMonkey, etc.)
- Individual Mozilla contributor blogs

## Customization

To customize:

1. Edit `assets/static/style.css` for visual changes, then redeploy — CSS is served straight from there.
2. To change the feed list, edit `assets/feeds.opml` and re-run `scripts/seed_feeds_from_opml.py` (editing `config.yaml` has no effect — it is documentation only).
3. To change branding (name, URL, footer, theme), edit the `vars` in `wrangler.jsonc` and redeploy.

```bash
npx wrangler deploy --config examples/planet-mozilla/wrangler.jsonc
```
