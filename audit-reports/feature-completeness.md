# Feature Completeness Audit

**Date:** 2026-03-11
**Scope:** docs/SPEC.md, README.md, src/ codebase
**Methodology:** Cross-referenced every documented feature, endpoint, and config option against actual implementation

---

## 1. Documented Features vs Exports

### Models (docs/SPEC.md Section 5 vs src/models.py)

All domain models from the spec are implemented:

| Spec Entity | Implemented | Notes |
|---|---|---|
| `FeedId`, `EntryId`, `AdminId` (NewType) | YES | |
| `AuditAction` (Literal) | YES | |
| `FeedStatus` (Literal) | YES | |
| `ContentType` (Literal) | YES | |
| `FeedJob` (dataclass) | YES | |
| `Session` (dataclass) | YES | |
| `ParsedEntry` (dataclass) | YES | |
| `FeedRow`, `EntryRow`, `AdminRow` (TypedDict) | YES | Implementation adds fields not in spec (`first_seen` in EntryRow, `author_name`/`author_email`/`last_fetch_at`/`fetch_error`/`fetch_error_count` in FeedRow) |
| `Ok`, `Err`, `Result` | YES | Implementation uses PEP 695 generics (`Ok[T]`) vs spec's `Generic[T]` |
| `FetchError` (Enum) | YES | |
| `ContentSanitizer` (Protocol) | NO | Not in code; `BleachSanitizer` is used directly without the Protocol |
| `BleachSanitizer` | YES | Enhanced beyond spec (pre-strips script/style, adds `rel=noopener`, lazy loading) |
| `NoOpSanitizer` | YES | |

**Gap:** `ContentSanitizer` Protocol is in the spec but not in the code. This is a minor gap -- the Protocol exists for testability, but `BleachSanitizer` is used directly. The `NoOpSanitizer` exists for tests, so the intent is met without the formal Protocol.
**Recommendation:** Implement it or remove from spec. Low priority since tests work without it.

### Auth Functions (docs/SPEC.md Section 7.1 vs src/auth.py)

All auth functions described or implied in the spec are implemented:
- `create_signed_cookie` -- YES
- `verify_signed_cookie` -- YES (enhanced with grace_seconds)
- `create_session_cookie` -- YES (not in spec, added for cleaner API)
- `get_session_from_cookies` -- YES
- `build_session_cookie_header` -- YES
- `build_clear_session_cookie_header` -- YES
- `build_oauth_state_cookie_header` -- YES
- `build_clear_oauth_state_cookie_header` -- YES
- `parse_cookie_value` -- YES

No missing auth functions.

### Admin Functions (docs/SPEC.md Section 7.3 vs src/admin.py)

| Function | Implemented | Notes |
|---|---|---|
| `admin_error_response` | YES | |
| `parse_opml` | YES | |
| `validate_opml_feeds` | YES | |
| `format_feed_validation_result` | YES | |
| `log_admin_action` | YES | |

No gaps in admin module exports.

---

## 2. Spec vs Implementation

### Spec Describes as Done, But Implementation Differs

| Spec Claim | Actual Status | Severity |
|---|---|---|
| Spec uses `httpx` for HTTP requests (Section 6.2) | Implementation uses `safe_http_fetch` from `wrappers.py` (fetch API via Pyodide) | INFO -- Implementation adapted for Workers runtime. Spec is aspirational/pseudocode, not prescriptive here. |
| Spec class named `PlanetCF` | Implementation class named `Default` | INFO -- Class name changed for Workers convention |
| Spec shows `_apply_retention_policy()` called during HTML generation (Section 6.3) | Implementation runs retention in scheduler only, NOT during page generation | GOOD -- Improvement over spec (retention once/hour vs once/page-load) |
| Spec describes `exponential_backoff` function with jitter (Section 8.3.3) | Not implemented in code | LOW -- Queue retry mechanism with `retry_delay` config handles this. No `calculate_backoff()` function exists. |
| Spec Section 5.4 describes `Result[T, E]` used throughout feed processing | Implementation uses plain dicts for returns, not `Result` type | LOW -- The `Result` type is defined in `models.py` but never used in `main.py`. Feed processing returns `dict` instead. |
| Spec's `_generate_html` applies retention inline | Implementation correctly defers retention to scheduler | GOOD |

### Spec Features Fully Implemented

- Queue-based fan-out (one feed per message) -- YES
- SSRF protection with URL re-validation after redirects -- YES
- HTML sanitization (bleach) -- YES
- Conditional HTTP requests (ETag/Last-Modified) -- YES
- Rate limit handling (429/503 with Retry-After) -- YES
- Feed auto-deactivation after consecutive failures -- YES
- Dead letter queue consumption and logging -- YES
- Semantic search via Vectorize + Workers AI -- YES
- GitHub OAuth authentication -- YES
- Signed session cookies (HMAC-SHA256) -- YES
- Edge caching via Cache-Control headers -- YES
- Database auto-initialization -- YES
- Retention policy (configurable days + max per feed) -- YES

---

## 3. Route/Endpoint Coverage

### Public Routes

| Documented Route | In README | In SPEC | In Code | Notes |
|---|---|---|---|---|
| `GET /` | YES | YES | YES | |
| `GET /index.html` | NO | NO | YES | Alias for `/`, undocumented |
| `GET /titles` | YES | NO | YES | Spec never mentions `/titles` |
| `GET /titles.html` | NO | NO | YES | Alias, undocumented |
| `GET /feed.atom` | YES | YES | YES | |
| `GET /feed.rss` | YES | YES | YES | |
| `GET /feed.rss10` | YES | NO | YES | README lists it, spec does not mention RSS 1.0 |
| `GET /feeds.opml` | YES | YES | YES | |
| `GET /foafroll.xml` | NO | NO | YES | Undocumented FOAF (Friend of a Friend) endpoint |
| `GET /health` | NO | NO | YES | Undocumented health check endpoint |
| `GET /search` | YES | YES | YES | |

### OAuth Routes

| Route | Documented | In Code | Notes |
|---|---|---|---|
| `GET /auth/github` | NO | YES | Undocumented in README/SPEC route tables (mentioned in setup flow) |
| `GET /auth/github/callback` | NO | YES | Undocumented in route tables (mentioned in setup flow) |

### Admin Routes

| Route | In SPEC (Section 7.3) | In Code | Notes |
|---|---|---|---|
| `GET /admin` | YES | YES | |
| `GET /admin/feeds` | YES | YES | |
| `POST /admin/feeds` | YES | YES | |
| `DELETE /admin/feeds/:id` | YES | YES | Also supports POST with `_method=DELETE` form override |
| `PUT /admin/feeds/:id` | YES | YES | |
| `POST /admin/feeds/:id/toggle` | YES | YES | |
| `POST /admin/import-opml` | YES | YES | |
| `POST /admin/regenerate` | YES | YES | |
| `GET /admin/dlq` | YES | YES | |
| `POST /admin/dlq/:id/retry` | YES | YES | |
| `GET /admin/audit` | YES | YES | |
| `POST /admin/logout` | NO | YES | Not in Section 7.3 table but present in spec's code example |
| `POST /admin/feeds/:id/fetch-now` | NO | YES | Undocumented -- synchronous feed fetch for E2E testing |
| `GET /admin/health` | NO | YES | Undocumented -- feed health overview page |
| `POST /admin/reindex` | NO | YES | Undocumented in SPEC Section 7.3 (mentioned in SPEC Section 12) |

### Summary of Route Gaps

**Undocumented routes in code (should add to docs or consider removing):**
1. `GET /index.html` -- Alias for `/`. Document as redirect/alias or leave undocumented (harmless).
2. `GET /titles.html` -- Alias for `/titles`. Same as above.
3. `GET /foafroll.xml` -- FOAF feed. Should be documented in README if intentionally supported.
4. `GET /health` -- Health check endpoint. Should be documented for operators/monitoring.
5. `GET /auth/github` -- OAuth initiation. Should be in route table for completeness.
6. `GET /auth/github/callback` -- OAuth callback. Should be in route table.
7. `POST /admin/feeds/:id/fetch-now` -- Should be documented if it's a permanent feature.
8. `GET /admin/health` -- Feed health page. Should be in admin route table.
9. `POST /admin/reindex` -- Reindex endpoint. Should be in admin route table.
10. `POST /admin/logout` -- Missing from SPEC Section 7.3 route table.

**Documented routes missing from code:** NONE. All documented routes exist.

---

## 4. Config Completeness

### Config Options Documented in README

| Config Option | README Documents | Code Reads It | Notes |
|---|---|---|---|
| `PLANET_NAME` | YES | YES (`config.py:get_planet_config`) | |
| `PLANET_DESCRIPTION` | YES | YES (`config.py:get_planet_config`) | |
| `PLANET_URL` | NO (not in table) | YES (`config.py:get_planet_config`) | Used but not in README config tables |
| `THEME` | YES | YES (`main.py:_get_theme`) | |
| `CONTENT_DAYS` | YES | YES (`config.py:get_content_days`) | |
| `HTTP_TIMEOUT_SECONDS` | YES | YES (`config.py:get_http_timeout`) | |
| `FEED_TIMEOUT_SECONDS` | YES | YES (`config.py:get_feed_timeout`) | |
| `RETENTION_MAX_ENTRIES_PER_FEED` | YES | YES (`config.py:get_max_entries_per_feed`) | |
| `FEED_FAILURE_THRESHOLD` | YES | YES (`config.py:get_feed_failure_threshold`) | |
| `RETENTION_DAYS` | YES | YES (`config.py:get_retention_days`) | |
| `FEED_AUTO_DEACTIVATE_THRESHOLD` | YES | YES (`config.py:get_feed_auto_deactivate_threshold`) | |
| `GROUP_BY_DATE` | YES | **NO** | **PHANTOM CONFIG**: Documented as default `true` but never read by any code |
| `SHOW_ADMIN_LINK` | YES | YES (`main.py:1841`) | |
| `SEARCH_ENABLED` | YES | **NO** | **PHANTOM CONFIG**: Documented as default `true` but never read by any code |

### Config Options Used by Code but NOT Documented in README

| Config Option | Where Used | Default | Should Document? |
|---|---|---|---|
| `PLANET_URL` | `config.py:get_planet_config`, `main.py` cache prewarm | `https://www.planetcloudflare.dev` | YES -- essential for deployments |
| `PLANET_OWNER_NAME` | `config.py:get_user_agent`, `main.py:_export_opml` | `""` / `"Planet CF"` | YES -- used in OPML export and User-Agent |
| `PLANET_OWNER_EMAIL` | `config.py:get_user_agent` | `""` | YES if USER_AGENT_TEMPLATE is documented |
| `USER_AGENT_TEMPLATE` | `config.py:get_user_agent` | None (uses default UA) | Probably not -- advanced/niche |
| `INSTANCE_MODE` | `instance_config.py:is_lite_mode` | `"full"` | YES -- controls lite vs full mode |
| `EMBEDDING_MAX_CHARS` | `config.py:get_embedding_max_chars` | `2000` | Optional -- advanced tuning |
| `SEARCH_SCORE_THRESHOLD` | `config.py:get_search_score_threshold` | `0.3` | Optional -- advanced tuning |
| `SEARCH_TOP_K` | `config.py:get_search_top_k` | `50` | Optional -- advanced tuning |
| `FEED_RECOVERY_ENABLED` | `config.py:get_feed_recovery_enabled` | `True` | YES -- operators should know this exists |
| `FEED_RECOVERY_LIMIT` | `config.py:get_feed_recovery_limit` | `2` | YES -- pairs with above |
| `ENABLE_RSS10` | `main.py:1828` | `""` (disabled) | Optional -- theme-specific |
| `ENABLE_FOAF` | `main.py:1831` | `""` (disabled) | Optional -- theme-specific |
| `HIDE_SIDEBAR_LINKS` | `main.py:1835` | `""` (not hidden) | Optional -- theme-specific |
| `FOOTER_TEXT` | `main.py:1867` | `"Powered by Planet CF"` | YES -- common customization |
| `DEPLOYMENT_ENVIRONMENT` | `main.py:347` (observability) | `""` | Optional -- observability |
| `DEPLOYMENT_VERSION` | `main.py:343` (observability) | `""` | Optional -- observability |

### Spec (docs/SPEC.md) Config Coverage

The SPEC Section 9.1 documents these vars in the example wrangler.jsonc:
- `PLANET_NAME` -- YES in code
- `PLANET_DESCRIPTION` -- YES in code
- `PLANET_URL` -- YES in code
- `PLANET_OWNER_NAME` -- YES in code
- `PLANET_OWNER_EMAIL` -- YES in code
- `RETENTION_DAYS` -- YES in code
- `RETENTION_MAX_ENTRIES_PER_FEED` -- YES in code
- `FEED_TIMEOUT_SECONDS` -- YES in code
- `HTTP_TIMEOUT_SECONDS` -- YES in code
- `GITHUB_CLIENT_ID` -- YES (secret)

All spec-documented config options are implemented.

---

## 5. Critical Findings

### CRITICAL: Phantom Config Options (docs claim features that don't exist)

1. **`GROUP_BY_DATE`** -- README documents this as a config option with default `true`, but no code anywhere reads it. Entries are always grouped by date. The README implies this can be set to `false` to disable date grouping, but that behavior does not exist.
   - **Recommendation:** Remove from README. There is no un-grouped mode.

2. **`SEARCH_ENABLED`** -- README documents this as a config option with default `true`, but no code reads it. Search availability is controlled by `INSTANCE_MODE` (lite mode disables search), not by a `SEARCH_ENABLED` toggle.
   - **Recommendation:** Remove from README, or implement it. If intent is to disable search independently of lite mode, implement it. Otherwise, update docs to say search is controlled via `INSTANCE_MODE`.

### HIGH: Undocumented Public Endpoints

3. **`GET /health`** -- Returns JSON feed health summary. Used by deployment verification scripts. Not in README or SPEC route tables.
   - **Recommendation:** Add to README route table. Operators and monitoring tools need this.

4. **`GET /foafroll.xml`** -- FOAF (Friend of a Friend) RDF feed. Exists in code but no docs mention it.
   - **Recommendation:** Add to README if intentionally supported, or note it as a theme-specific feature.

### MEDIUM: Undocumented Admin Endpoints

5. **`POST /admin/feeds/:id/fetch-now`** -- Synchronous feed fetch (bypasses queue). Not in SPEC Section 7.3 table.
   - **Recommendation:** Add to admin API docs if permanent, or mark as internal/testing.

6. **`GET /admin/health`** -- Feed health overview page. Not in SPEC Section 7.3 table.
   - **Recommendation:** Add to admin API docs.

7. **`POST /admin/reindex`** -- Search index rebuild. Mentioned in SPEC Section 12 but missing from the Section 7.3 admin route table.
   - **Recommendation:** Add to Section 7.3 table.

8. **`POST /admin/logout`** -- Missing from SPEC Section 7.3 route table (present in code examples later in the spec).
   - **Recommendation:** Add to Section 7.3 table.

### LOW: Spec Aspirational Content vs Implementation

9. **`ContentSanitizer` Protocol** -- Defined in SPEC Section 5.5 but not in `src/models.py`. Code uses `BleachSanitizer` directly.
   - **Recommendation:** Either add the Protocol to `models.py` or remove from spec. Low impact.

10. **`Result[T, E]` type** -- Defined in code and spec but never used in actual feed processing. `_process_single_feed` returns plain dicts.
    - **Recommendation:** Either refactor to use `Result` or acknowledge in spec that it's available for future use.

11. **Exponential backoff with jitter** -- SPEC Section 8.3.3 describes a `calculate_backoff` function. Not implemented; queue `retry_delay` handles retries.
    - **Recommendation:** Remove from spec or note that queue retry_delay serves this purpose.

### LOW: Undocumented Config Options Worth Documenting

12. **`FOOTER_TEXT`** -- Common customization, default "Powered by Planet CF". Should be in README config table.

13. **`FEED_RECOVERY_ENABLED`** / **`FEED_RECOVERY_LIMIT`** -- Auto-recovery of disabled feeds. Should be in README since it affects operational behavior.

14. **`PLANET_URL`** -- Essential for deployments but not in README config tables (only mentioned in Quick Start).

---

## 6. Action Items Summary

| # | Action | Priority | Side to Change |
|---|---|---|---|
| 1 | Remove `GROUP_BY_DATE` from README config table | CRITICAL | Docs |
| 2 | Remove `SEARCH_ENABLED` from README or implement it | CRITICAL | Docs or Code |
| 3 | Add `/health` to README public routes table | HIGH | Docs |
| 4 | Add `/foafroll.xml` to README (or note as theme-specific) | HIGH | Docs |
| 5 | Add `/admin/feeds/:id/fetch-now` to SPEC admin table | MEDIUM | Docs |
| 6 | Add `/admin/health` to SPEC admin table | MEDIUM | Docs |
| 7 | Add `/admin/reindex` to SPEC Section 7.3 admin table | MEDIUM | Docs |
| 8 | Add `/admin/logout` to SPEC Section 7.3 admin table | MEDIUM | Docs |
| 9 | Add `FOOTER_TEXT` to README config table | LOW | Docs |
| 10 | Add `FEED_RECOVERY_ENABLED`/`FEED_RECOVERY_LIMIT` to README | LOW | Docs |
| 11 | Add `PLANET_URL` to README config table | LOW | Docs |
| 12 | Remove `ContentSanitizer` Protocol from SPEC or add to code | LOW | Either |
| 13 | Remove `calculate_backoff` from SPEC Section 8.3.3 | LOW | Docs |
| 14 | Acknowledge `Result` type is defined but unused in SPEC | LOW | Docs |
