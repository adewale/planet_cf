# CRAP Design Principles Audit -- Planet CF UI

**Date:** 2026-03-11
**Scope:** Default theme (primary), planet-python theme, planet-mozilla theme, admin dashboard
**Files reviewed:**
- `/Users/ade/Documents/projects/planet_cf/assets/static/style.css`
- `/Users/ade/Documents/projects/planet_cf/assets/static/admin.js`
- `/Users/ade/Documents/projects/planet_cf/assets/static/keyboard-nav.js`
- `/Users/ade/Documents/projects/planet_cf/src/templates.py` (all embedded templates)
- `/Users/ade/Documents/projects/planet_cf/examples/planet-python/assets/static/style.css`
- `/Users/ade/Documents/projects/planet_cf/examples/planet-python/assets/static/styles/styles.css`
- `/Users/ade/Documents/projects/planet_cf/examples/planet-mozilla/assets/static/style.css`
- `/Users/ade/Documents/projects/planet_cf/examples/planet-cloudflare/assets/static/style.css`

---

## 1. Contrast

### Strengths

- **Well-defined color hierarchy.** The default theme uses a disciplined 3-tier text system (`--text-primary: #111827`, `--text-secondary: #374151`, `--text-muted: #6b7280`) against white/near-white backgrounds. All pass WCAG AA contrast ratios.
- **Code blocks stand out.** Dark background (`--code-bg: #1f2937`) with light text (`--code-text: #f3f4f6`) creates strong visual separation from body content.
- **Feed health indicators.** The orange/red dot system (`.healthy::before` = accent orange, `.unhealthy::before` = error red) provides semantic meaning at a glance.
- **Admin status badges** in `health.html` use distinct background/text color pairs per state (green for healthy, yellow for warning, red for failing, gray for inactive).

### Issues

**C-1. Search button lacks contrast against its surroundings.**
The `.search-form button` has `background: var(--bg-primary)` (white) with `color: var(--text-secondary)` (dark gray) and a `border: 1px solid var(--border-medium)`. It looks nearly identical to the search input field. A primary action button should be visually distinct.

- **File:** `assets/static/style.css`, lines 126-137
- **Fix:** Give the search button the accent fill: `background: var(--accent); color: white; border: 1px solid var(--accent);`. The input field already signals "type here" through its lighter background; the button should signal "click me."

**C-2. Article title links are indistinguishable from non-link headings.**
`article h3 a` uses `color: var(--text-primary)` with `text-decoration: none`. Until the user hovers, these look identical to static heading text. The hover state (`color: var(--accent)`) is the only cue they are interactive.

- **File:** `assets/static/style.css`, lines 196-204
- **Fix:** Add a persistent underline or color difference. Either `color: var(--accent)` always, or `text-decoration: underline; text-decoration-color: var(--accent-subtle);` so the link nature is visible pre-hover.

**C-3. Admin link in footer uses inline gray (#999) styling, making it deliberately invisible.**
The admin link uses `style="color: #999; font-size: 0.8em;"` inline, blending with muted footer text. While intentionally low-key, it falls below WCAG AA contrast (4.5:1) against `--bg-tertiary: #f3f4f6`. The ratio for #999 on #f3f4f6 is approximately 2.8:1.

- **File:** `src/templates.py`, line 119 and 238
- **Fix:** Move to a CSS class (`.admin-link { color: var(--text-muted); font-size: 0.8rem; }`) and validate contrast. `var(--text-muted)` (#6b7280) passes AA on both bg-primary and bg-tertiary.

**C-4. planet-python theme: `#content-body` uses `font-size: 75%`.**
This aggressive shrink combined with `#body-main { font-size: 100% }` means base text renders at ~77% of the root 103% size (~12px), which is uncomfortably small for extended reading.

- **File:** `examples/planet-python/assets/static/style.css`, line 96
- **Fix:** Increase to at least `font-size: 87.5%` (14px) or restructure the cascade.

**C-5. Inline error style in planet-python search uses bare hex.**
`style="color: #c00;"` for errors. This is hardcoded and disconnected from the design system's `--error: #dc2626`.

- **File:** `src/templates.py`, line 1052
- **Fix:** Use the theme's `.search-error` class or at least reference the custom property.

---

## 2. Repetition

### Strengths

- **CSS custom properties provide excellent token reuse.** Every color, shadow, and border is defined once in `:root` and reused throughout. This is the single strongest design-system decision in the codebase.
- **Consistent card pattern.** Articles, search results, and sidebar all use the same recipe: `bg-primary` background, `border-light` border, `shadow-sm`, `border-radius: 8px`. Hover states consistently upgrade to `shadow-md`.
- **Font strategy is deliberate.** Body/content in serif (Georgia), headings in display serif (Palatino), UI chrome in system sans-serif. Three tiers, clearly assigned.
- **Transition timing is uniform.** Nearly every interactive element uses `0.15s ease` or `0.2s ease` transitions.

### Issues

**R-1. Inconsistent border-radius values.**
Articles use `8px`, sidebar uses `10px`, search results use `10px`, shortcuts panel uses `10px`, admin sections use `8px`. This creates a subtle "almost the same" visual inconsistency.

- **Files:** `assets/static/style.css`, lines 175, 353, 504, 599
- **Fix:** Standardize on one value. Add `--radius-card: 8px;` and `--radius-lg: 10px;` to `:root` and use them consistently. Pick one for cards (suggest `8px`) and one for modals/panels.

**R-2. Two parallel button systems.**
The base `button` element has `border: 2px solid var(--accent)` with an outline/ghost style, while `.btn` uses `border: none` with filled backgrounds. These are both used in the admin dashboard (the "Refresh Feeds" uses `.btn` while "Delete" uses `.btn.btn-danger`), but the base `button` style leaks into any unstyled button in any template.

- **Files:** `assets/static/style.css`, lines 546-577
- **Fix:** Unify to one system. Make the bare `button` reset minimal (`appearance: none; cursor: pointer;`) and use `.btn` + `.btn-primary`, `.btn-ghost` variants for all styled buttons.

**R-3. Inline styles break the repetition pattern.**
The admin dashboard template embeds ~55 lines of `<style>` overrides inside `admin/dashboard.html` and another ~35 in `admin/health.html`. These override the base stylesheet with one-off values (e.g., `.section { padding: 1rem }` vs the article card's `1.5rem`). The admin error page and login page each define their own completely independent design with hardcoded hex colors (`#667eea`, `#764ba2`, `#24292e`).

- **File:** `src/templates.py`, lines 311-366 (dashboard), 583-619 (health), 496-551 (error), 729-767 (login)
- **Fix:** Extract admin styles into a separate `admin.css` static file. For login/error pages, at minimum extract shared `.card` and `.btn` styles to avoid 4 different definitions of what a button looks like.

**R-4. Hardcoded hex colors outside the design token system.**
Several places bypass CSS custom properties:
  - `.search-notice` uses `background: #f0f7ff; border: 1px solid #c9e0ff;` (lines 488-489)
  - `.btn-warning` uses `background: #f59e0b;` (line 577)
  - Admin inline styles use `color: #666;` (lines 452, 463, 473)

- **Fix:** Add `--warning: #f59e0b;` and `--info-bg: #f0f7ff; --info-border: #c9e0ff;` to `:root`. Replace all hardcoded values with variable references.

**R-5. planet-mozilla and planet-python themes share no design tokens with default.**
Each theme is an entirely independent CSS file with its own hardcoded colors. While this is understandable for community themes that replicate external sites, it means any cross-theme feature (keyboard shortcuts panel, feed health indicators) must be manually duplicated.

The planet-python theme's `style.css` _does_ include a `.shortcuts-panel` section, but the planet-mozilla theme relies on CSS in its own `style.css` for the same component with different styling (no border-radius, different font, different padding). This is a repetition gap that will cause bugs when the feature evolves.

---

## 3. Alignment

### Strengths

- **CSS Grid layout is well-structured.** The `.container` uses `grid-template-columns: 1fr 300px` which creates a clean, predictable two-column layout.
- **Sidebar top alignment is explicitly handled.** The comment on line 357 (`margin-top: 3.25rem`) documents an intentional offset to align the sidebar top with the first article card, accounting for the day heading height. This shows alignment awareness.
- **Flex-based header** with `align-items: baseline` ensures logo text and subtitle share a common baseline.

### Issues

**A-1. Sidebar alignment relies on a magic number.**
`margin-top: 3.25rem` aligns the sidebar with the first article only when the day heading has a specific height. If the date text wraps (e.g., "Wednesday, 11 March 2026"), the alignment breaks. Different font sizes at different breakpoints will also invalidate this.

- **File:** `assets/static/style.css`, line 358
- **Fix:** Instead of the magic margin, use `align-self: start;` on the sidebar (already achieved by `height: fit-content`) and apply `grid-row: 1 / -1;` to keep it alongside all content. Or use a CSS sub-grid approach if you want true cross-column alignment.

**A-2. Feed list items have asymmetric left padding.**
`.feeds li` has `padding-left: 1rem` to make room for the health indicator dot (the `::before` pseudo-element uses `margin-left: -1rem`). But the dot is only 6px wide with `margin-right: calc(1rem - 6px)`, creating a 10px gap between the dot and the text. Feeds without a dot (no `.healthy` or `.unhealthy` class) have a left indent with nothing in it.

- **File:** `assets/static/style.css`, lines 378-427
- **Fix:** Only apply the padding offset when a health class is present: `.feeds li.healthy, .feeds li.unhealthy { padding-left: 1rem; }` with default `padding-left: 0;`. Alternatively, always show a dot (gray for unknown state).

**A-3. Default titles page mixes `em` and `rem` units for spacing.**
The `.titles-only` section uses `0.3em`, `0.5em`, `0.25em`, `0.85em`, and `0.9em` while the rest of the stylesheet uses `rem` units. This means spacing will scale differently when nested inside containers with different font sizes.

- **File:** `assets/static/style.css`, lines 662-723
- **Fix:** Convert to `rem` for consistency: `padding: 0.3rem 0`, `margin-bottom: 0.5rem`, etc.

**A-4. planet-python theme uses absolute positioning for layout.**
`#content-body { position: absolute; left: 0; top: 63px; }` and `#left-hand-navigation { position: absolute; left: 3%; top: 110px; }`. This creates alignment that is fragile across viewports and impossible to maintain responsively.

- **File:** `examples/planet-python/assets/static/style.css`, lines 86-100, 110-121
- **Fix:** The planet-python `style.css` overrides (the file the instance actually uses) already partially addresses this with flexbox (`main-container { display: flex }`). But the original `styles/styles.css` still contains the absolute positioning. Ensure only the modern layout is used.

**A-5. Search page sidebar has inline margin.**
`<p style="margin-top: 1rem;"><a href="/">... Back to home</a></p>` uses inline style instead of a class.

- **File:** `src/templates.py`, line 293
- **Fix:** Add a `.back-link { margin-top: 1rem; }` class or use the existing spacing patterns.

---

## 4. Proximity

### Strengths

- **Article card structure is well-grouped.** Title, meta (author + date), and content are visually clustered inside a bordered card with consistent internal spacing. The `.meta` sits between title and content with `margin-bottom: 1rem`, creating clear visual separation.
- **Day-level grouping.** Articles are grouped under date headings (`section.day`) with `margin-bottom: 2.5rem` between day groups, creating clear temporal clusters.
- **Admin feed items** bundle related information (title, URL, status, toggle, delete) into a single `.feed-item` flex container.

### Issues

**P-1. Sidebar mixes unrelated content without visual separation.**
The sidebar contains: (1) sidebar-links (RSS/titles), (2) search form, (3) "Subscriptions" heading + feed list, (4) optional submission link, (5) optional related sites sections. Between the search form and the Subscriptions heading, there is only the heading itself -- no border, divider, or spacing increase. The search form has `border-bottom: 1px solid var(--border-light)` but nothing separates subscriptions from optional related sites.

- **File:** `assets/static/style.css`, sidebar section; `src/templates.py`, lines 72-114
- **Fix:** Add `margin-top: 1.5rem;` to `.sidebar h2` (already partially done at `1.25rem`) and consider adding a light top border: `.sidebar h2 { border-top: 1px solid var(--border-light); padding-top: 1rem; }` for all section breaks after the first.

**P-2. `.sidebar-links` class has no CSS styling.**
The `sidebar-links` div wraps RSS/titles-only/Planet Planet links but has zero CSS rules. These links render with no margin, no visual grouping, no spacing from the search form below them. They are visually orphaned.

- **File:** `src/templates.py`, lines 74-78; `assets/static/style.css` (class absent)
- **Fix:** Add:
  ```css
  .sidebar-links {
      display: flex;
      gap: 0.75rem;
      margin-bottom: 1rem;
      font-size: 0.875rem;
  }
  .sidebar-links a {
      color: var(--accent);
      text-decoration: none;
  }
  ```

**P-3. `.submission-link` and `.related-links` have no CSS styling.**
Both classes are used in templates but have zero corresponding CSS rules. The submission link will inherit default paragraph styling, and related-links will use default list styling with bullets (the `.feeds` class that removes bullets is not applied to these).

- **File:** `src/templates.py`, lines 101, 107-110; `assets/static/style.css` (classes absent)
- **Fix:** Add explicit rules. At minimum:
  ```css
  .submission-link { margin-top: 1rem; font-size: 0.875rem; }
  .related-links { list-style: none; }
  .related-links li { padding: 0.375rem 0; font-size: 0.925rem; }
  ```

**P-4. Admin dashboard tab content sections lack internal proximity cues.**
Each `.tab-content` contains a `.section` with an `h2` and form content, but the DLQ and Audit tabs show dynamically loaded items (`.dlq-item`, `.audit-item`) that have `margin-bottom: 0.5rem`. When multiple items load, the space between them (0.5rem) is the same as the internal spacing within items, making it hard to distinguish where one item ends and the next begins.

- **File:** `src/templates.py`, inline styles (line 358)
- **Fix:** Increase inter-item gap to `0.75rem` or add a more prominent visual separator.

**P-5. Footer groups unrelated items on the same line.**
Line 119 of the template packs: footer_text + admin link + keyboard hint into one `<p>`. These serve three different purposes (attribution, admin access, user guidance). The middle-dot separators create a flat list rather than a hierarchy.

- **File:** `src/templates.py`, line 119
- **Fix:** Split into separate paragraphs or use flexbox with `justify-content: center; gap: 1.5rem;` to create more breathing room. The keyboard hint (`Press ? for shortcuts`) especially deserves its own visual space since it is an actionable instruction.

---

## 5. Cross-Cutting Issues

### Missing CSS for template classes

The following classes are used in HTML templates but have **zero CSS rules** anywhere in `assets/static/style.css`:

| Class | Used in | Impact |
|---|---|---|
| `.sidebar-links` | index.html, titles.html | Links render unstyled, no spacing |
| `.search-label` | index.html, titles.html | Label renders with default styles |
| `.submission-link` | index.html, titles.html | Paragraph renders with inherited styles |
| `.related-links` | index.html, titles.html | List shows default bullets |
| `.nav-level-one` | index.html, titles.html | Heading renders as normal h2 |
| `.nav-level-two` | index.html, titles.html | No effect (same as .related-links) |
| `.nav-level-three` | index.html, titles.html | No effect |
| `.logo-link` | index.html, titles.html | Link renders with default anchor style |
| `.logo` | index.html, titles.html | Image has no special sizing/positioning |
| `.search-page` | search.html | No differentiation from normal main |

### Inline style proliferation

The admin templates contain **17 inline `style=` attributes** that bypass the design system. This undermines repetition (every instance is a one-off) and makes theme-wide changes impossible.

### Theme isolation gap

The keyboard shortcuts panel (`.shortcuts-panel`) is styled in all three themes, but each theme has a different visual treatment. The default uses `border-radius: 10px` with a drop shadow; planet-python uses a flat border with no radius; planet-mozilla inherits the planet-python styling. If a new feature is added to the shortcuts panel, it must be updated in three places.

---

## 6. Priority Recommendations

Ordered by impact/effort ratio:

1. **Add CSS for orphaned classes** (P-2, P-3) -- low effort, fixes unstyled content that is live today.
2. **Make search button visually distinct** (C-1) -- single CSS change, improves main page usability.
3. **Standardize border-radius via tokens** (R-1) -- small refactor, prevents "almost aligned" visual noise.
4. **Extract admin inline styles to admin.css** (R-3) -- moderate effort, eliminates 55+ lines of embedded CSS and makes admin pages themeable.
5. **Replace hardcoded hex with CSS variables** (R-4, C-5) -- sweep through templates and CSS, ensures consistency.
6. **Fix sidebar alignment magic number** (A-1) -- investigate CSS grid sub-alignment, fragile at present.
7. **Make article title links visually interactive** (C-2) -- design decision needed on whether to use color or underline.
8. **Unify button systems** (R-2) -- moderate refactor, reduces confusion between `button` and `.btn`.
9. **Normalize units in titles-only section** (A-3) -- small cleanup, prevents future spacing drift.
10. **Fix footer admin link contrast** (C-3) -- move inline style to class, validate WCAG.
