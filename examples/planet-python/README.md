# Planet Python Example

A faithful clone of [Planet Python](https://planetpython.org/), the Python community feed aggregator.

## Features

- 500+ Python community feeds (from the original Planet Python)
- Custom theme matching the classic planetpython.org design
- Left sidebar layout with Python blue color scheme
- Georgia serif headings, classic blog aggregator style

> **This example runs in lite mode** (`INSTANCE_MODE: "lite"`): no semantic search, no admin dashboard, no OAuth. Its `wrangler.jsonc` has **no** Vectorize or AI bindings, so do not create a Vectorize index or set OAuth secrets for it.

## Included Files

- `config.yaml` - Documentation-only description of the instance and its feed list (nothing reads it at deploy or runtime)
- `wrangler.jsonc` - Cloudflare Workers configuration (lite mode)
- `assets/static/style.css` - Planet Python theme CSS
- `assets/static/python-logo.svg` - Python logo for header
- `assets/feeds.opml` - the feed list, applied to D1 via `scripts/seed_feeds_from_opml.py`

## Quick Start

### Deploy with one command

```bash
./scripts/deploy_instance.sh planet-python
```

Then seed the feeds (a fresh deploy starts with an empty page):

```bash
uv run python scripts/seed_feeds_from_opml.py --config examples/planet-python/wrangler.jsonc
```

### Or deploy manually

```bash
# Create D1 database
npx wrangler d1 create planet-python-db
# Update database_id in wrangler.jsonc

# Create queues
npx wrangler queues create planet-python-feed-queue
npx wrangler queues create planet-python-feed-dlq

# Run ALL migrations in order (not just 001)
for f in migrations/*.sql; do
  npx wrangler d1 execute planet-python-db --remote --file="$f"
done

# Deploy
npx wrangler deploy --config examples/planet-python/wrangler.jsonc

# Seed feeds into D1 (lite mode reads assets/feeds.opml)
uv run python scripts/seed_feeds_from_opml.py --config examples/planet-python/wrangler.jsonc
```

## Theme Details

The Planet Python theme recreates the classic planetpython.org design:

- **Layout**: Left sidebar (classic Planet style)
- **Colors**: Python blue (#234764, #366D9C), yellow accents (#FFDB4C)
- **Typography**: Georgia serif for headings, Arial for body
- **Links**: Classic web blue (#0000AA) with purple visited state

## Feed List

`assets/feeds.opml` contains 561 Python community feeds sourced from the original [Planet Python config](https://github.com/python/planet/blob/main/config/config.ini). Seed them into D1 with `scripts/seed_feeds_from_opml.py` (see Quick Start).

## Customization

To customize:

1. Edit `assets/static/style.css` for visual changes, then redeploy — CSS is served straight from there.
2. To change the feed list, edit `assets/feeds.opml` and re-run `scripts/seed_feeds_from_opml.py` (editing `config.yaml` has no effect — it is documentation only).
3. To change branding (name, URL, footer, theme), edit the `vars` in `wrangler.jsonc` and redeploy.

```bash
npx wrangler deploy --config examples/planet-python/wrangler.jsonc
```
