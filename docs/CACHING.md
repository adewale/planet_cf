# Caching

Planet CF uses Cloudflare's edge network to serve pages as close to visitors as possible. Because the Worker runs Python via Pyodide (WebAssembly), cold-start TTFB is ~1-3s. The entire caching strategy exists to hide that cold start so real visitors almost never experience it.

## Workers.dev vs Custom Domain

**Cloudflare does not cache responses from `*.workers.dev` domains by default.** Cache-Control headers are ignored on workers.dev — every request runs the Worker. Edge caching only activates when a Worker is deployed behind a Cloudflare zone (custom domain).

| Instance | Domain | Edge caching | Notes |
|----------|--------|-------------|-------|
| **Production** | `www.planetcloudflare.dev` | Active | Custom domain via `routes` in `wrangler.production.jsonc` |
| **test-planet** | `*.workers.dev` | Inactive | No zone — every request hits the Worker |
| **planet-python** | `planetpython.org` | Depends on DNS | Active if domain is proxied through Cloudflare |
| **planet-mozilla** | `planet.mozilla.org` | Depends on DNS | Same |

This means:
- **Cache-Control headers**, **pre-warming**, and **cache purging** only matter for custom-domain deployments
- On workers.dev, these features execute harmlessly (prewarm fetches run but don't populate edge cache; purge deletes nothing)
- The code is designed to degrade gracefully: all caching operations are best-effort and no-op when there's nothing to cache or purge

## Architecture Overview

```
Visitor ──▶ Cloudflare Edge ──▶ Worker (Pyodide)
               │                      │
               │  Cache HIT?          │
               │  ◀── yes ── serve    │
               │         (custom      │
               │          domain      │
               │          only)       │
               │                      │
               │  Cache MISS?         │
               │  ──── run Worker ──▶ │
               │  ◀── cache response  │
```

Three layers work together (on custom domains):

1. **Cache-Control headers** on HTML/feed responses for Cloudflare's edge cache
2. **Cron-based cache pre-warming** to keep the edge warm between visitors
3. **Workers Static Assets** for CSS/JS/images (served before the Worker runs)

## Cache-Control Headers

All public HTML and feed responses include (`src/utils.py:214-216`):

```
Cache-Control: public, max-age=3600, stale-while-revalidate=3600
```

This creates a two-phase caching window:

| Window | Duration | Behavior |
|--------|----------|----------|
| **Fresh** | 0-60 min | Edge serves cached response directly. Zero Worker invocations. |
| **Stale** | 60-120 min | Edge serves stale response instantly while refreshing in the background. |
| **Expired** | 120+ min | Only if no visitor arrives for 2+ hours does the cache fully expire. |

Visitors in both the fresh and stale windows get edge-cached responses (~20-50ms).

### Cacheable Routes

These routes return `Cache-Control` headers and are cached at the edge (registered as `cacheable=True` routes in `src/main.py`, see the router built in `_create_router`):

| Route | Content Type |
|-------|-------------|
| `/` | HTML (homepage) |
| `/index.html` | HTML (alias) |
| `/titles` | HTML (titles-only) |
| `/titles.html` | HTML (alias) |
| `/feed.atom` | Atom XML |
| `/feed.rss` | RSS 2.0 XML |
| `/feed.rss10` | RSS 1.0 XML |
| `/feeds.opml` | OPML |
| `/foafroll.xml` | FOAF |

### Non-Cacheable Routes

| Route | Cache-Control | Reason |
|-------|--------------|--------|
| `/search` | `max-age=0` | User-specific query results |
| `/admin/*` | `no-store` | Authentication-gated, state-mutating |
| `/auth/github*` | (none) | OAuth endpoints return 302 redirects with only a `Location` header — no `Cache-Control` is set. (Redirects to the provider/back are not meaningfully cacheable anyway.) |
| `/health` | (none) | Must reflect current state |

## Edge Cache Pre-Warming

After the hourly cron scheduler enqueues feed fetches and runs retention cleanup, it requests the four most important pages on itself (`src/main.py`, the prewarm loop in the scheduler over `CACHEABLE_PATHS`):

```python
for path in CACHEABLE_PATHS:
    await safe_http_fetch(f"{base_url}{path}", headers=warm_headers)
```

This ensures the edge always has a fresh copy, even if no real visitor has come recently. Combined with `stale-while-revalidate`, there is no realistic window where a visitor hits an uncached Worker.

| Time | Event | Visitor experience |
|------|-------|-------------------|
| 0:00 | Cron fires, fetches feeds, pre-warms cache | Cache now fresh |
| 0:01-1:00 | Visitors get cached responses | ~20-50ms |
| 1:00-2:00 | `stale-while-revalidate` window | ~20-50ms (stale but fast) |
| 2:00 | Next cron fires, pre-warms again | Cache refreshed |

The `PLANET_URL` environment variable determines the base URL for pre-warming. Instances without `PLANET_URL` skip pre-warming silently.

## Cache Purging

When an admin action modifies content (add feed, remove feed, import OPML, regenerate), the edge cache for public pages may be stale. Planet CF uses a dual-layer purge strategy to invalidate cached responses.

After a content-modifying admin action completes, `_purge_edge_cache()` (`src/main.py`) purges the same paths that cron pre-warms:

```python
CACHEABLE_PATHS = ("/", "/titles", "/feed.atom", "/feed.rss")
```

### Dual-layer purge strategy

Purging runs two independent layers in sequence. Both are best-effort: failures are logged but do not fail the admin action.

**Layer 1 — Global purge (all PoPs):** If `CLOUDFLARE_ZONE_ID` and `CLOUDFLARE_API_TOKEN` secrets are configured, calls the [Cloudflare Purge API](https://developers.cloudflare.com/cache/how-to/purge-cache/purge-by-single-file/) (`POST /zones/{zone_id}/purge_cache` with `{"files": [...]}`) to invalidate cached responses across all edge locations worldwide. This requires a Cloudflare API token with `Cache Purge` permission scoped to the zone.

**Layer 2 — Local PoP purge (defense-in-depth):** Always runs, regardless of whether Layer 1 succeeded. Uses the [Cache API](https://developers.cloudflare.com/workers/runtime-apis/cache/) (`caches.default.delete(url)`) to purge from the data center where the admin request landed. This is a fallback that ensures the admin's own region sees fresh content immediately.

### Graceful degradation across instance types

The purge logic degrades safely based on what's configured:

| Scenario | Layer 1 (global) | Layer 2 (local) | Effect |
|----------|-----------------|-----------------|--------|
| Custom domain + both secrets set | Runs | Runs | Full global purge |
| Custom domain + secrets missing | Skipped | Runs | Local PoP only; other PoPs wait for TTL |
| `*.workers.dev` (no zone) | Skipped | Runs (no-op) | Nothing to purge; no edge cache exists |
| `PLANET_URL` not set | Both skipped | Both skipped | Entire method is a no-op |

This design means:
- **Production** (`www.planetcloudflare.dev`): Gets full global purge when secrets are configured
- **test-planet** (`*.workers.dev`): Purge code runs harmlessly — no edge cache to invalidate
- **Other instances** (planet-python, planet-mozilla): Get global purge if their operators add the secrets; local-only otherwise
- **No instance can break** from missing configuration — the worst case is stale content for up to 1 hour (the existing TTL)

### Admin actions that trigger purging

| Action | Why purge? |
|--------|-----------|
| Add feed | New feed's entries will appear on homepage |
| Remove feed | Feed's entries removed from homepage |
| Import OPML | Multiple feeds added |
| Regenerate | Explicit cache refresh request |
| Fetch-now | New entries fetched synchronously |

### Actions that do NOT trigger purging

| Action | Why not? |
|--------|----------|
| Update feed (title/toggle) | No immediate content change; entries refresh on next cron |
| Retry DLQ | Queues a future fetch; no immediate content change |
| Reindex | Search index only; no HTML/feed content change |
| View audit log | Read-only |

## Workers Static Assets

CSS, JS, images, and favicons are served by [Workers Static Assets](https://developers.cloudflare.com/workers/static-assets/) (the `assets` binding in each `wrangler.jsonc`):

```jsonc
"assets": {
  "directory": "./assets/",
  "binding": "ASSETS"
}
```

With the default `run_worker_first = false`, Cloudflare serves matching files from the assets directory at the edge **before the Worker runs**. A request for `/static/style.css` is served directly from the CDN with:

- Zero Pyodide cold start
- Zero Worker CPU cost
- Automatic tiered edge caching

Static assets and Worker responses use independent cache paths. Purging Worker-generated pages does not affect static assets.

## Conditional GETs (Upstream Feed Fetching)

When fetching upstream feeds, the Worker stores and reuses `ETag` and `Last-Modified` headers from each response (`src/main.py`, the conditional-request headers in the feed fetch path):

```python
if etag:
    headers["If-None-Match"] = str(etag)
if last_modified:
    headers["If-Modified-Since"] = str(last_modified)
```

If the feed hasn't changed, the upstream server returns 304 Not Modified with no body, saving bandwidth and parse time. Both values are stored in the `feeds` table and sent on every subsequent fetch.

This is outbound caching (our Worker as a client), not edge caching (our Worker as a server). The two are independent.

## What's Not Cached

| Feature | Status | Notes |
|---------|--------|-------|
| `Vary` headers | Not set | Low risk: no content negotiation on public routes |
| `CDN-Cache-Control` | Not used | `Cache-Control` applies to both browser and edge identically |
| `ETag` on HTML responses | Not generated | Edge handles revalidation via `stale-while-revalidate` |
| `Last-Modified` on HTML | Not generated | Same as above |
| Content-hashed static assets | Not used | Theme customization per instance makes hashing complex |
| Surrogate keys / Cache Tags | Not used | URL-based purge via REST API is simpler for 4 paths |
| Custom cache key rules | Not configured | Low value: search (the main query-string route) isn't cached |

These are deliberate trade-offs, not gaps. For a feed aggregator that updates hourly and serves relatively small pages, the current strategy provides excellent cache hit rates with minimal complexity.
