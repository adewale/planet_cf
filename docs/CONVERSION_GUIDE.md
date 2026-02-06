# Converting Planet/Venus Sites to PlanetCF

This guide documents how to convert existing Planet or Venus websites to PlanetCF instances with 100% visual fidelity.

## The Golden Rule

**REUSE, DON'T RECREATE.**

The single most important principle: download and use the original site's assets exactly as they are. Never recreate logos, CSS, or images from scratch. Every deviation from the original introduces visual differences.

---

## Step 1: Download Original Assets First

Before writing any code, download everything from the original site.

### 1.1 Logo and Images

```bash
# Create asset directories
mkdir -p examples/planet-python/static/images
mkdir -p examples/planet-mozilla/static/img

# Download logos (use exact original filenames)
curl -o examples/planet-python/static/images/python-logo.gif \
  https://planetpython.org/images/python-logo.gif

curl -o examples/planet-mozilla/static/img/logo.png \
  https://planet.mozilla.org/img/logo.png
```

### 1.2 Background Images

Many Planet sites use background images for headers, footers, and body. Download ALL of them:

```bash
# Planet Mozilla backgrounds
curl -o examples/planet-mozilla/static/img/header-bg.jpg \
  https://planet.mozilla.org/img/header-bg.jpg
curl -o examples/planet-mozilla/static/img/footer.jpg \
  https://planet.mozilla.org/img/footer.jpg
curl -o examples/planet-mozilla/static/img/background.jpg \
  https://planet.mozilla.org/img/background.jpg
```

### 1.3 Original CSS

Download the original CSS files, then adapt selectors (not values):

```bash
# Download original CSS
curl -o examples/planet-python/static/styles/styles.css \
  https://planetpython.org/static/styles/styles.css
```

**Adapt selectors, preserve values:**
- `#menu` → `.sidebar`
- `#logoheader` → `header`
- Keep all colors, fonts, spacing EXACTLY the same

### 1.4 Icons, Bullets, Fonts

Don't forget small assets:

```bash
# Feed icons, bullet images, etc.
curl -o examples/planet-mozilla/static/img/feed-icon.png \
  https://planet.mozilla.org/img/feed-icon.png
```

---

## Step 2: Match Asset Paths Exactly

Serve assets at the SAME paths as the original site:

| Original Path | Our Path | Status |
|---------------|----------|--------|
| `/images/python-logo.gif` | `/static/images/python-logo.gif` | Correct |
| `/img/logo.png` | `/static/img/logo.png` | Correct |
| `/static/logo.svg` (recreated) | (different file) | Wrong |

The `/static/` prefix is added by our routing, but the rest of the path must match.

---

## Step 3: Configure Theme Assets

### 3.1 THEME_LOGOS Configuration

Every theme needs a complete logo configuration:

```python
THEME_LOGOS = {
    "planet-python": {
        "url": "/static/images/python-logo.gif",  # REQUIRED - must match asset path
        "alt": "Planet Python",
        "width": "211",
        "height": "71",
    },
    "planet-mozilla": {
        "url": "/static/img/logo.png",  # REQUIRED - must match asset path
        "alt": "Planet Mozilla",
        "width": "222",
        "height": "44",
    },
}
```

**Critical:** Missing `url` key causes HTTP 500 errors.

### 3.2 THEME_ASSETS for Embedded Images

For Cloudflare Workers (no filesystem), embed images as base64:

```python
THEME_ASSETS = {
    "planet-python": {
        "logo": "data:image/gif;base64,R0lGODlh0wBH...",
    },
    "planet-mozilla": {
        "logo": "data:image/png;base64,iVBORw0KGgo...",
        "header_bg": "data:image/jpeg;base64,...",
        "footer_bg": "data:image/jpeg;base64,...",
        "background": "data:image/jpeg;base64,...",
    },
}
```

---

## Step 4: Match Template Text Exactly

Small text differences are noticeable. Extract and match exact strings:

| Element | Original | Wrong | Correct |
|---------|----------|-------|---------|
| Timestamp label | "Last update:" | "Last updated:" | "Last update:" |
| Date format | "February 01, 2026 01:49 AM UTC" | "2026-02-01 01:49 UTC" | Match original |

---

## Step 5: Detect Layout from CSS

### Sidebar Position

Check CSS for positioning indicators:

```python
# Left sidebar indicators
"float: left" in css and "sidebar" in css
"order: -1" in css
"#left-hand" in css
"margin-left: 19em" in css

# Right sidebar
"order: 1" in css
"float: right" in css
```

- Planet Python: LEFT sidebar
- Planet Mozilla: RIGHT sidebar

---

## Verification Tools

After completing the conversion, use these tools to verify 100% fidelity.

### Tool 1: Automated Converter (`scripts/convert_planet.py`)

Automates the entire conversion process:

```bash
# Install dependencies
pip install requests beautifulsoup4

# Convert a site
python scripts/convert_planet.py https://planetpython.org/ --name planet-python
```

**What it does:**
1. Downloads all assets (images, icons, fonts)
2. Extracts CSS from stylesheets
3. Detects sidebar position
4. Extracts template text
5. Generates wrangler.jsonc config
6. Generates theme_assets.py for integration

**Output:**
```
examples/{name}/
├── wrangler.jsonc          # Ready-to-deploy config
├── theme/
│   └── style.css           # Adapted CSS
├── assets/
│   ├── images/             # Downloaded logos, icons
│   └── styles/             # Original CSS files
└── theme_assets.py         # Python dict for templates.py
```

### Tool 2: Visual Comparison (`scripts/visual_compare.py`)

Compares screenshots pixel-by-pixel:

```bash
# Install dependencies
pip install playwright pillow
playwright install chromium

# Run comparison
python scripts/visual_compare.py --all
python scripts/visual_compare.py --python
python scripts/visual_compare.py --mozilla
```

**Output:**
- Screenshot of original site
- Screenshot of our instance
- Diff image highlighting differences
- Match percentage (target: >85% for structural elements)

### Tool 3: HTTP Verification

Always verify deployments work:

```bash
# Must return 200
curl -s -o /dev/null -w "%{http_code}" https://your-instance.workers.dev/

# Verify assets load
curl -sI https://your-instance.workers.dev/static/images/python-logo.gif | head -3
```

---

## Fidelity Checklist

Before declaring a conversion complete:

### Assets
- [ ] Logo is exact same file (not recreated)
- [ ] Logo served at original path
- [ ] Background images downloaded and served
- [ ] Icons/bullets downloaded and served
- [ ] Fonts match (or are loaded)

### CSS
- [ ] Colors match exactly (use color picker)
- [ ] Font families match
- [ ] Font sizes match
- [ ] Spacing/margins match
- [ ] Sidebar position correct (left/right/none)

### Template
- [ ] "Last update:" text matches
- [ ] Date format matches
- [ ] Section headings match ("Subscriptions", etc.)
- [ ] Footer text matches

### Verification
- [ ] HTTP 200 on main page
- [ ] HTTP 200 on all static assets
- [ ] No console errors
- [ ] Visual comparison > 85% (structural elements)

---

## Manual Verification Checklist

After deploying a converted site, manually verify these key aspects by comparing the original and converted sites side-by-side in browser windows.

### Visual Layout

**Logo and Header**
- [ ] Logo displays in correct position (top-left, centered, etc.)
- [ ] Logo is correct size (not stretched or squeezed)
- [ ] Logo uses original file (not recreated/SVG substitute)
- [ ] Header background color/image matches original
- [ ] Header height matches original

**Sidebar**
- [ ] Sidebar position correct (left vs right vs none)
- [ ] Sidebar width matches original proportionally
- [ ] Sidebar background/border styling matches
- [ ] "Subscriptions" heading style matches
- [ ] Feed list bullet style matches (disc, square, custom)

**Content Area**
- [ ] Main content area margins match original
- [ ] Date headers use same font family (Georgia, Helvetica, etc.)
- [ ] Date headers use same color (#366D9C, #b72822, etc.)
- [ ] Entry author headings styled correctly (italic, bold, etc.)
- [ ] Entry title links styled correctly

**Footer**
- [ ] Footer background color/image matches
- [ ] Footer text color matches
- [ ] Footer positioning matches (fixed, relative)

### Color Verification

Use browser DevTools or a color picker to verify exact colors:

| Element | Planet Python | Planet Mozilla |
|---------|---------------|----------------|
| Primary heading | #366D9C | #b72822 |
| Links | #00A | #148cb5 |
| Visited links | #551A8B | #636 |
| Body text | #000 | #000 |
| Header background | #F7F7F7 | #455372 |
| Footer background | #FFF | #2a2a2a |

### Font Verification

| Element | Planet Python | Planet Mozilla |
|---------|---------------|----------------|
| Body text | Arial/Verdana | Helvetica/Arial |
| Headings | Georgia (serif) | Helvetica (sans-serif) |
| Date headers | Georgia, italic | Georgia, normal |
| Sidebar text | Verdana | Helvetica |

### Responsive Behavior

- [ ] At 700px width, layout adjusts properly
- [ ] At 480px width, layout remains usable
- [ ] Logo scales appropriately on mobile
- [ ] Sidebar moves below content on narrow screens

### Functional Verification

- [ ] RSS feed link works (`/feed.rss`)
- [ ] Atom feed link works (`/feed.atom`)
- [ ] OPML file accessible (`/feeds.opml`)
- [ ] "Titles only" link works (if applicable)
- [ ] Search form functions (if applicable)
- [ ] All subscription links open in new tab or navigate correctly
- [ ] Keyboard shortcuts work (n/p navigation, ? for help)

### Browser Compatibility

Test in at least two browsers:
- [ ] Chrome/Edge: Layout renders correctly
- [ ] Firefox: Layout renders correctly
- [ ] Safari: Layout renders correctly (if available)

### Common Visual Issues to Check

| Issue | What to Look For | Fix |
|-------|------------------|-----|
| Logo wrong size | Stretched/squeezed appearance | Check width/height attributes |
| Wrong sidebar | Left vs right placement | Check CSS `order` property |
| Missing backgrounds | Solid color instead of image | Download and serve original images |
| Wrong fonts | Sans-serif vs serif headings | Check CSS font-family |
| Link colors off | Links look different | Check CSS link colors |
| Spacing issues | Too much/too little margin | Compare with original CSS |

---

## Technical Notes for Cloudflare Workers

### Binary Data Handling

Cloudflare Workers Python corrupts binary data when passed directly to `Response()`. Use JavaScript typed arrays:

```python
from js import Uint8Array
from pyodide.ffi import to_js

# Convert Python bytes to JavaScript Uint8Array
js_array = Uint8Array.new(to_js(image_data))
return Response(js_array, headers={"Content-Type": "image/gif"})
```

### No Filesystem Access

Workers run in WebAssembly - no `open()`, no `pathlib`. Assets must be:
1. Embedded as base64 in Python code at build time, OR
2. Stored in Cloudflare bindings (KV, R2) and fetched at runtime

---

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| HTTP 500 | Missing 'url' in THEME_LOGOS | Add url key |
| Logo not showing | Wrong path or CSS `display: none` | Use original path, check CSS |
| Binary corruption | Direct Response() | Use js.Uint8Array |
| Wrong sidebar position | CSS order property | Check order: -1 vs 1 |
| Missing backgrounds | Solid color substitution | Download original images |
| Low pixel match (<85%) | Dynamic content | Compare structure only |

---

## Results Achieved

| Site | Initial | Final | Structural |
|------|---------|-------|------------|
| Planet Python | 67.58% | 86.69% | ~95% |
| Planet Mozilla | 79.79% | 91.54% | ~95% |

The remaining 5-15% difference is dynamic content (different blog posts), not structural differences.

---

## Files Reference

| File | Purpose |
|------|---------|
| `scripts/convert_planet.py` | Automated converter |
| `scripts/visual_compare.py` | Visual comparison |
| `scripts/build_templates.py` | HTML template compiler |
| `examples/planet-python/` | Planet Python instance |
| `examples/planet-mozilla/` | Planet Mozilla instance |
| `src/templates.py` | Embedded HTML templates (generated) |
| `src/main.py` | Worker entrypoint and business logic |
