# Planet CF Design Guide

A reference for maintaining visual consistency across Planet CF.

---

## Color Palette

### CSS Variables (defined in `:root`)

```css
/* Accent - Cloudflare Orange, used sparingly */
--accent: #f6821f;
--accent-dark: #e5731a;      /* Hover states */
--accent-light: #fff7ed;     /* Focus rings, highlights */
--accent-subtle: #fed7aa;    /* Decorative accents */

/* Text Hierarchy */
--text-primary: #111827;     /* Headings, important text */
--text-secondary: #374151;   /* Body text, descriptions */
--text-muted: #6b7280;       /* Metadata, timestamps, labels */

/* Backgrounds */
--bg-primary: #ffffff;       /* Cards, inputs, main surfaces */
--bg-secondary: #f9fafb;     /* Page background */
--bg-tertiary: #f3f4f6;      /* Footer, code backgrounds */

/* Borders */
--border-light: #e5e7eb;     /* Default borders */
--border-medium: #d1d5db;    /* Hover states, form focus */

/* Code Blocks */
--code-bg: #1f2937;          /* Dark background */
--code-text: #f3f4f6;        /* Light text */

/* Semantic Colors */
--success: #059669;          /* Healthy feeds, success states */
--error: #dc2626;            /* Errors, unhealthy feeds */
```

### Usage Guidelines
- **Accent orange**: Links, hover states, focus rings, CTAs. Never for large areas.
- **Text colors**: Use `--text-primary` for headings, `--text-secondary` for body copy.
- **Backgrounds**: Layer from `--bg-secondary` (page) to `--bg-primary` (cards).

---

## Typography

### Font Families

| Context | Font Stack | Usage |
|---------|-----------|-------|
| **Serif (Content)** | Georgia, Times New Roman, serif | Body text, article content |
| **Serif (Headings)** | Palatino Linotype, Book Antiqua, Palatino, Georgia, serif | h1-h6 headings |
| **Sans-serif (UI)** | -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif | Sidebar, meta, buttons, form labels |
| **Monospace (Code)** | SF Mono, Fira Code, Consolas, monospace | Code blocks, inline code |

### Font Sizes

| Element | Size | Notes |
|---------|------|-------|
| Body | 18px | Base size, comfortable reading |
| Header h1 | 1.75rem | Site title |
| Article h3 | 1.25rem | Entry titles |
| Content | 1.0625rem | Article body text |
| Meta/timestamps | 0.875rem | Secondary info |
| Section labels | 0.8rem | Uppercase, letter-spacing: 0.08em |
| Sidebar items | 0.925rem | Feed list |

### Line Heights
- Body: `1.8` (generous for readability)
- Content paragraphs: `1.85`
- Headings: `1.3` - `1.35`

---

## Spacing System

### Core Values
- **Container max-width**: 1200px
- **Container margin**: 2rem auto
- **Grid gap**: 2rem (main/sidebar)
- **Sidebar width**: 300px

### Common Spacing
| Value | Usage |
|-------|-------|
| 0.25rem | Small gaps, tight spacing |
| 0.5rem | Button padding (sm), separators |
| 0.625rem | Input padding, form gaps |
| 0.75rem | Table cells, list items |
| 1rem | Standard margin/padding |
| 1.25rem | Article content spacing |
| 1.5rem | Card padding, section gaps |
| 2rem | Header padding, major sections |
| 2.5rem | Day section margins |

---

## Component Patterns

### Buttons

```css
/* Default Button (outlined) */
button {
    padding: 0.625rem 1.25rem;
    background: var(--bg-primary);
    color: var(--accent);
    border: 2px solid var(--accent);
    border-radius: 6px;
    font-weight: 600;
}
button:hover {
    background: var(--accent);
    color: white;
}
```

**Admin Button Variants** (dashboard only):
- `.btn-primary` - Blue (#007bff) for main actions
- `.btn-success` - Green (#28a745) for add/create
- `.btn-danger` - Red (#dc3545) for delete/logout
- `.btn-warning` - Yellow (#ffc107) for retry/rebuild
- `.btn-sm` - Smaller padding for inline actions

### Cards (Articles)

```css
article {
    background: var(--bg-primary);
    border: 1px solid var(--border-light);
    border-radius: 8px;
    padding: 1.5rem;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}
article:hover {
    box-shadow: 0 4px 6px -1px rgba(0,0,0,0.07);
    border-color: var(--border-medium);
}
```

### Form Inputs

```css
input {
    padding: 0.75rem 1rem;
    border: 1px solid var(--border-light);
    border-radius: 6px;
    background: var(--bg-secondary);
}
input:focus {
    border-color: var(--accent);
    background: var(--bg-primary);
    box-shadow: 0 0 0 3px var(--accent-light);
    outline: none;
}
```

### Sidebar

```css
.sidebar {
    background: var(--bg-primary);
    border: 1px solid var(--border-light);
    border-radius: 10px;
    padding: 1.5rem;
    position: sticky;
    top: 1rem;
}
```

### Status Indicators
- **Healthy**: Green dot (`--success`) before feed name
- **Unhealthy**: Red dot (`--error`) before feed name
- Use 6px circles with `border-radius: 50%`

---

## Design Philosophy

### Core Principles

1. **Warm & Readable**
   - Serif fonts for content create a classic, readable feel
   - Generous line-height (1.8) for comfortable scanning
   - 18px base font for optimal readability

2. **Subtle & Restrained**
   - Accent orange used sparingly (links, focus, hover)
   - Shadows are minimal (`rgba(0,0,0,0.04)` to `0.07`)
   - Borders are light gray, not harsh

3. **Content-First**
   - Articles are the star; clean white cards on muted background
   - No visual noise; icons and decorations are minimal
   - Date groupings use subtle uppercase labels

4. **Progressive Enhancement**
   - Hover states add depth (shadow, border color)
   - Focus states are obvious (accent ring)
   - Transitions are quick (0.15s-0.2s)

### Key Visual Decisions

| Decision | Implementation |
|----------|---------------|
| Brand color | Cloudflare orange (#f6821f) |
| Content typography | Serif for elegance and readability |
| UI typography | System sans-serif for clarity |
| Card style | White, 1px border, subtle shadow |
| Border radius | 6px (inputs, buttons) to 10px (cards, sidebar) |
| Responsive | Single column below 768px |

### Accessibility Notes
- Focus rings use 3px accent-light box-shadow
- Color contrast ratios meet WCAG AA
- Interactive elements have visible hover/focus states
- Font sizes remain readable at base level

---

## Quick Reference

```
Accent:     #f6821f (orange)
Text:       #111827 / #374151 / #6b7280
Background: #ffffff / #f9fafb / #f3f4f6
Border:     #e5e7eb / #d1d5db
Success:    #059669
Error:      #dc2626

Body font:  Georgia, serif @ 18px
UI font:    system-ui, sans-serif
Radius:     6px (small) / 8-10px (large)
```
