# Lighthouse Performance Assessment for Planet CF

This document describes how to use [Google Lighthouse](https://developer.chrome.com/docs/lighthouse/)
to assess the performance of a deployed Planet CF instance, what metrics matter most
for this application, and what to expect from each audit category.

## Why Lighthouse

Planet CF is a server-rendered feed aggregator with minimal client-side JavaScript.
Lighthouse provides automated audits across five categories that map directly to the
qualities an aggregator should have: fast initial load, accessible markup, correct
meta tags for SEO, and sensible security headers. Because the public pages are
edge-cached with a one-hour TTL, Lighthouse scores will reflect what real visitors
experience after the cache is warm.

## Running Lighthouse

### Chrome DevTools (quickest)

1. Open the deployed instance (e.g. `https://planetcf.com`) in Chrome.
2. Open DevTools → **Lighthouse** tab.
3. Select categories: Performance, Accessibility, Best Practices, SEO.
4. Choose **Mobile** or **Desktop** mode, then click **Analyze page load**.

### Lighthouse CLI

```bash
npm install -g lighthouse

# Desktop audit of the home page
lighthouse https://planetcf.com --output html --output-path ./report.html

# Mobile audit (default)
lighthouse https://planetcf.com --preset perf --output json --output-path ./report.json

# Specific pages
lighthouse https://planetcf.com/search?q=workers --output html --output-path ./search-report.html
```

### Lighthouse CI (GitHub Actions integration)

Add a job to the existing CI pipeline that runs Lighthouse against a preview
deployment or the production URL after deploy:

```yaml
lighthouse:
  needs: check
  if: github.ref == 'refs/heads/main'
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: Run Lighthouse
      uses: treosh/lighthouse-ci-action@v12
      with:
        urls: |
          https://planetcf.com
          https://planetcf.com/search?q=cloudflare
        budgetPath: ./lighthouse-budget.json
        uploadArtifacts: true
```

A companion budget file (`lighthouse-budget.json`) can enforce thresholds:

```json
[
  {
    "path": "/",
    "timings": [
      { "metric": "first-contentful-paint", "budget": 1500 },
      { "metric": "largest-contentful-paint", "budget": 2500 },
      { "metric": "interactive", "budget": 3000 },
      { "metric": "cumulative-layout-shift", "budget": 0.1 }
    ],
    "resourceSizes": [
      { "resourceType": "document", "budget": 100 },
      { "resourceType": "stylesheet", "budget": 15 },
      { "resourceType": "script", "budget": 10 },
      { "resourceType": "total", "budget": 150 }
    ]
  }
]
```

### PageSpeed Insights API

For on-demand checks without installing anything, use Google's hosted version:

```
https://pagespeed.web.dev/analysis?url=https://planetcf.com
```

This runs Lighthouse remotely and includes field data from the Chrome User
Experience Report (CrUX) when available.

## Pages to Audit

| Page | URL | Notes |
|------|-----|-------|
| Home | `/` | Main entry list, largest page, edge-cached |
| Search results | `/search?q=workers` | Vectorize-backed, variable response time |
| Atom feed | `/feed.atom` | XML, Lighthouse won't score but useful for TTFB |
| RSS feed | `/feed.rss` | XML, same as above |
| Admin dashboard | `/admin` | Behind OAuth, audit manually |

The home page (`/`) is the primary target. It is the only page most visitors see,
carries the most content, and loads both the stylesheet and keyboard navigation
script.

## Metrics That Matter

### Performance

| Metric | What it measures | Planet CF context |
|--------|-----------------|-------------------|
| **TTFB** | Time to First Byte | Measures edge cache hit vs. Worker cold start. Expect <100ms on cache hit, 200-800ms on cache miss depending on D1 query time and template rendering. |
| **FCP** | First Contentful Paint | How quickly the header and first article render. Depends on CSS delivery since `style.css` is render-blocking. |
| **LCP** | Largest Contentful Paint | Likely the first `<article>` block or the `<header>` element. No hero images to delay this. |
| **CLS** | Cumulative Layout Shift | Should be near zero. The page uses system fonts (no FOUT), no lazy-loaded images above the fold, and no dynamically injected content on load. |
| **INP** | Interaction to Next Paint | Keyboard navigation (`j`/`k`) and search form are the main interactions. The JS is lightweight (~3.4 KB) so INP should be excellent. |
| **TBT** | Total Blocking Time | Minimal JS execution on page load. The keyboard-nav script runs a single `querySelectorAll` and attaches event listeners. |

### Accessibility

Key areas Lighthouse will check against the current templates:

- `<html lang="en">` is present.
- Search input has `aria-label="Search entries"`.
- Keyboard shortcuts panel uses `role="dialog"` and `aria-modal="true"`.
- Color contrast between orange (`#f38020`) on white may flag as insufficient for small text. The header uses white-on-orange which should pass for large text.
- Feed status indicators use color alone (green/red bullets via `::before` pseudo-elements). Lighthouse may flag this since the `healthy`/`unhealthy` distinction is purely color-based with no text alternative.

### Best Practices

- HTTPS is enforced by Cloudflare.
- `X-Content-Type-Options: nosniff` is set on HTML responses.
- No deprecated APIs are used in the vanilla JS.
- Console errors from failed fetches (e.g. if Vectorize is unavailable) could cause deductions.

### SEO

- `<meta charset>` and `<meta viewport>` are present.
- `<title>` is set dynamically from `planet.name`.
- `<link rel="alternate">` for Atom and RSS feeds is present.
- Missing: `<meta name="description">` tag. Lighthouse will flag this.
- Missing: `<meta name="robots">` tag (not strictly required but Lighthouse checks for it).
- Links use readable text (feed titles, not "click here").

## Expected Findings and Recommendations

### Likely high-scoring areas

1. **TBT / INP**: Near zero. Only ~3.4 KB of JS runs on public pages, all
   non-blocking, with no frameworks or heavy computation.

2. **CLS**: Near zero. System fonts avoid FOUT, layout is CSS grid with fixed
   sidebar width, no content injection on load.

3. **Best Practices**: HTTPS, security headers, modern HTML5 doctype, no
   deprecated APIs.

### Likely areas for improvement

1. **Render-blocking CSS**: `style.css` (10.3 KB, unminified) blocks first paint.
   Options:
   - Inline critical CSS (header + first article styles) in a `<style>` tag and
     load the full stylesheet with `media="print" onload="this.media='all'"`.
   - Minify the stylesheet (could save ~20-30%).

2. **Missing meta description**: Add a `<meta name="description"
   content="{{ planet.description }}">` tag to the `<head>` of `index.html` and
   `search.html`.

3. **Image optimization in entry content**: Aggregated feed content (`entry.content | safe`)
   may contain `<img>` tags without `width`/`height` attributes, `loading="lazy"`,
   or modern formats. These are third-party images from feed sources, so:
   - Consider adding `loading="lazy"` to images in aggregated content via
     post-processing.
   - Consider adding `width` and `height` attributes where dimensions can be
     inferred, or wrapping content images in an aspect-ratio container.

4. **Color contrast**: The orange primary color (`#f38020`) on white background
   may fail WCAG AA for normal-sized text. The contrast ratio is approximately
   3.0:1, below the 4.5:1 requirement for normal text. Options:
   - Darken the link color to `#c05d00` or similar for body text links.
   - The header (white on orange) passes for large text (h1).

5. **Accessibility of feed health indicators**: The green/red bullet points
   for healthy/unhealthy feeds are CSS-only with no text alternative. Consider
   adding `aria-label` or a visually-hidden text span.

## Connecting Lighthouse to Existing Observability

Planet CF already emits wide events (`RequestEvent`) with fields that complement
Lighthouse data:

| Lighthouse metric | Corresponding server metric |
|---|---|
| TTFB | `wall_time_ms` on `RequestEvent` |
| Cache hit ratio | `cache_status` field (`HIT`/`MISS`/`BYPASS`) |
| Response size | `response_size_bytes` |
| Search latency | `search_time_ms` / `generation_time_ms` |

Combining Lighthouse client-side metrics with server-side wide events gives a
full picture: Lighthouse tells you what the user experienced, while
`RequestEvent` tells you why. For example, a high TTFB in Lighthouse with
`cache_status: MISS` in the logs points to a cold-cache scenario, while a high
TTFB with `cache_status: HIT` would indicate a CDN issue.

## Interpreting Results for Cloudflare Workers

A few caveats when reading Lighthouse results for a Workers-based site:

1. **Cold starts**: Cloudflare Workers Python runtime may exhibit cold start
   latency (200-500ms) on the first request after idle. Lighthouse runs a
   single page load, so TTFB may reflect a cold start rather than steady-state.
   Run multiple audits and compare, or warm the Worker first with a preflight
   request.

2. **Edge caching**: Public pages set `Cache-Control: public, max-age=3600,
   stale-while-revalidate=60`. Lighthouse will likely hit the edge cache if
   the page has been visited recently. To test origin performance, add a
   cache-busting query parameter: `?_cb=1` (the Worker will still serve it
   but Cloudflare's cache will treat it as a new URL).

3. **Geographic variance**: Lighthouse runs from wherever you run it (your
   machine or Google's servers). Cloudflare's edge network means performance
   varies by PoP. Use WebPageTest (webpagetest.org) for multi-location testing.

4. **D1 latency**: The home page queries D1 for entries and feeds. D1 read
   replicas are regional, so latency depends on the requesting location
   relative to the nearest replica. The `wall_time_ms` in server logs captures
   this, while Lighthouse's TTFB includes it plus network transit.
