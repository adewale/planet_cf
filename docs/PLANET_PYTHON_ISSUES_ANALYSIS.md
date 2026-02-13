# Planet Python Issues Analysis — Planet CF Cross-Reference

Analysis of all non-feed issues from [python/planet](https://github.com/python/planet/issues), segmented into categories, with assessment of whether Planet CF already solves each issue.

> Feed add/edit/remove requests were excluded from this analysis.

---

## 1. Feed Validation & Automated Maintenance

| # | Issue | Status | Planet CF Solves? | How |
|---|-------|--------|-------------------|-----|
| [#614](https://github.com/python/planet/issues/614) | Automated RSS/Atom Feed Validation Workflow | Open | **Yes** | Built-in feed health monitoring with consecutive failure tracking, auto-deactivation, dead-letter queue, and automatic feed recovery on scheduler runs. |
| [#466](https://github.com/python/planet/issues/466) | GitHub Action: weekly link verification job | Open | **Yes** | Every hourly cron cycle checks every feed. Feeds returning errors get `consecutive_failures` incremented. Auto-deactivation at configurable threshold (default 10). Health endpoint (`/health`) shows real-time status. |
| [#233](https://github.com/python/planet/issues/233) | Script to remove dead/deprecated/invalid links | Open | **Yes** | `FetchError` enum classifies errors as permanent (GONE, NOT_FOUND, INVALID_URL) vs transient (TIMEOUT, SERVER_ERROR). Permanently broken feeds are auto-deactivated. Admin dashboard shows failing feeds. |
| [#308](https://github.com/python/planet/issues/308) | 237 of 862 URLs returning errors | Closed | **Yes** | Entire class of problem eliminated. Feeds validated on every fetch cycle, failures tracked, broken feeds auto-deactivated. |

## 2. HTML/XML Rendering Bugs

| # | Issue | Status | Planet CF Solves? | How |
|---|-------|--------|-------------------|-----|
| [#582](https://github.com/python/planet/issues/582) | Python 3 port broke HTML escaping in XML feeds | Open | **Yes** | Uses `BleachSanitizer` for proper HTML sanitization (not Jinja2 `Markup()` passthrough), plus `strip_xml_control_chars()` for XML 1.0 compliance. Content sanitized before rendering. |

## 3. Content Quality & Spam

| # | Issue | Status | Planet CF Solves? | How |
|---|-------|--------|-------------------|-----|
| [#606](https://github.com/python/planet/issues/606) | PSF blog link points to spam (FeedBurner hijack) | Closed | **Partially** | Admin dashboard allows quick URL updates. But detecting URL hijacks still requires human observation. |
| [#534](https://github.com/python/planet/issues/534) | Drop Codementor (low-quality/spam posts) | Closed | **Partially** | Admin dashboard with toggle/remove capability. Audit logging tracks moderation. No automated content quality detection. |
| [#379](https://github.com/python/planet/issues/379) | Chinese spam (domain takeover) | Closed | **Partially** | Admin tooling makes removal fast, but domain takeover detection is not automated. |
| [#378](https://github.com/python/planet/issues/378) | Amazon affiliate link spam | Closed | **Partially** | Admin dashboard allows immediate feed removal with audit trail. |
| [#224](https://github.com/python/planet/issues/224) | End Point Blog not Python-related | Closed | **Partially** | Admin tools allow fast removal. No automated topic relevance checking. |
| [#166](https://github.com/python/planet/issues/166) | Orbited feed no longer Python-related | Closed | **Partially** | Admin tooling for fast moderation, but not automated content analysis. |

## 4. Feed Fetching & SSL/TLS

| # | Issue | Status | Planet CF Solves? | How |
|---|-------|--------|-------------------|-----|
| [#276](https://github.com/python/planet/issues/276) | Feed doesn't show up (TLS issue) | Closed | **Yes** | Modern Python 3.12+ with httpx on Cloudflare Workers. Full modern TLS support, no legacy SSL issues. |
| [#240](https://github.com/python/planet/issues/240) | SSL errors on valid XML feed | Closed | **Yes** | No Python 2.x SSL stack. Modern TLS via httpx and Cloudflare runtime. ETag/Last-Modified conditional requests reduce unnecessary fetches. |
| [#135](https://github.com/python/planet/issues/135) | New article doesn't show up (SSL on old Ubuntu) | Closed | **Yes** | Cloudflare Workers runtime has modern TLS. No dependency on host OS SSL libraries. |
| [#262](https://github.com/python/planet/issues/262) | Posts not showing (filter cutoff) | Closed | **Yes** | Shows 7 days of content by default, with fallback to 50 most recent entries if date range is empty. 90-day retention, 100 entries per feed. |

## 5. Site Infrastructure & Outages

| # | Issue | Status | Planet CF Solves? | How |
|---|-------|--------|-------------------|-----|
| [#597](https://github.com/python/planet/issues/597) | Last update was 5 days ago (cron broke) | Closed | **Yes** | Cloudflare Workers cron triggers — managed infrastructure. No server config to break. Scheduler defined in `wrangler.jsonc`. |
| [#228](https://github.com/python/planet/issues/228) | Page stopped updating (output dir misconfigured) | Closed | **Yes** | No output directories — content served directly from D1 database. No filesystem write step to misconfigure. |
| [#231](https://github.com/python/planet/issues/231) | No HTTPS redirect | Open | **Yes** | Cloudflare provides automatic HTTPS redirection and HSTS (`max-age=31536000`). Security headers set in `src/utils.py`. |
| [#230](https://github.com/python/planet/issues/230) | HTTPS rendering broken (missing CSS/JS) | Open | **Yes** | Static assets served via Cloudflare Workers Static Assets binding. No mixed-content issues — everything HTTPS by default. |

## 6. Broken External Links

| # | Issue | Status | Planet CF Solves? | How |
|---|-------|--------|-------------------|-----|
| [#610](https://github.com/python/planet/issues/610) | Link to planetplanet.org broken | Open | **Yes** | Planet CF doesn't reference planetplanet.org. Standalone project with self-contained templates. |
| [#125](https://github.com/python/planet/issues/125) | planet.jython.org link dead | Closed | **Yes** | External links are configurable per-theme. No hardcoded dependencies on third-party planet sites. |

## 7. Legacy Code & Project Organization

| # | Issue | Status | Planet CF Solves? | How |
|---|-------|--------|-------------------|-----|
| [#491](https://github.com/python/planet/issues/491) | Code says "Requires Python 2.1" | Open | **Yes** | Built from scratch for Python 3.12+. No legacy Python 2 code. |
| [#469](https://github.com/python/planet/issues/469) | Template code hard to find | Closed | **Yes** | Clear directory structure: `templates/` for Jinja2 source, `src/templates.py` for compiled. Documented in `ARCHITECTURE.md` and `LAYOUT.md`. |
| [#526](https://github.com/python/planet/issues/526) | Repo should move to different GitHub org | Open | **N/A** | Governance issue specific to python/ GitHub org. Not a technical problem. |
| [#128](https://github.com/python/planet/issues/128) | sort-ini groups by URL scheme | Closed | **Yes** | Feeds stored in D1 database (full mode) or OPML (lite mode). No `config.ini` sorting issues. |

## 8. Social Media Integration

| # | Issue | Status | Planet CF Solves? | How |
|---|-------|--------|-------------------|-----|
| [#173](https://github.com/python/planet/issues/173) | Articles not appearing in Twitter feed | Open | **No** | No built-in social media syndication. Would need external integration. |
| [#89](https://github.com/python/planet/issues/89) | Specific post missing from Twitter | Closed | **No** | No Twitter integration in Planet CF. |

## 9. Feature Requests

| # | Issue | Status | Planet CF Solves? | How |
|---|-------|--------|-------------------|-----|
| [#307](https://github.com/python/planet/issues/307) | Filter for individual vs corporate blogs | Closed | **Partially** | Semantic search (`/search`) helps users find content. Admin dashboard allows feed categorization. No built-in individual/corporate filter. |

---

## Summary

| Category | Total | Open | Closed | Planet CF Coverage |
|----------|-------|------|--------|-------------------|
| Feed Validation & Automation | 4 | 3 | 1 | 4/4 fully solved |
| HTML/XML Rendering | 1 | 1 | 0 | 1/1 fully solved |
| Content Quality & Spam | 6 | 0 | 6 | 6/6 partially (tooling yes, auto-detection no) |
| Feed Fetching & SSL/TLS | 4 | 0 | 4 | 4/4 fully solved |
| Site Infrastructure & Outages | 4 | 2 | 2 | 4/4 fully solved |
| Broken External Links | 2 | 1 | 1 | 2/2 fully solved |
| Legacy Code & Project Org | 4 | 2 | 2 | 3/4 solved (1 N/A) |
| Social Media Integration | 2 | 1 | 1 | 0/2 not addressed |
| Feature Requests | 1 | 0 | 1 | 1/1 partially |
| **Total** | **28** | **10** | **18** | **19 full, 8 partial, 2 no, 1 N/A** |
