# Security Audit Report -- Planet CF

**Date:** 2026-03-11
**Auditor:** Claude Opus 4.6
**Scope:** Full source review of `src/` (17 modules), configuration files, and dependency manifest
**Methodology:** Manual code review tracing user input from HTTP entry points through processing, storage, and rendering

---

## Executive Summary

Planet CF demonstrates strong security fundamentals: parameterized SQL throughout, HMAC-signed sessions with constant-time comparison, comprehensive SSRF protection, XXE mitigation, and a well-configured Content Security Policy. The audit identified **0 Critical**, **1 High**, **4 Medium**, and **5 Low** severity findings. The most significant issue is the use of Jinja2's `|safe` filter on feed content that, while sanitized by bleach, creates a fragile trust boundary where any regression in the sanitizer would expose stored XSS.

---

## Findings

### 1. Stored XSS via `|safe` on Feed Content (depends on bleach sanitizer correctness)

**Severity:** High
**Files:** `src/templates.py` (lines 63, 854, 1144), `src/models.py` (lines 256-363), `src/main.py` (line 1025)
**Category:** Injection -- XSS

**Description:**
Feed entry content is rendered with `{{ entry.content | safe }}` in three templates (default index, planet-python, planet-mozilla). This bypasses Jinja2's autoescape and outputs raw HTML to the browser. The content IS sanitized by `BleachSanitizer.clean()` before database storage (line 1025 in main.py), which strips dangerous tags and attributes. However:

1. The sanitization happens only at **write time** (during `_upsert_entry`). If a bleach bypass is discovered (bleach has had bypass CVEs historically), all previously stored content is trusted.
2. The regex post-processing in `BleachSanitizer.clean()` (lines 334-348 of models.py) adds `target="_blank"` and `rel="noopener noreferrer"` via regex substitution on already-cleaned HTML. Regex on HTML is inherently fragile. A crafted `href` attribute could potentially survive the bleach cleaning step and the subsequent regex transformations in an unexpected state.
3. The `javascript:` stripping regex (line 343) uses a pattern that matches `javascript:` anywhere in the href value, which is good, but relies on case-insensitive matching against a single pattern. Encoded variants (`java&#115;cript:`) would be handled by bleach's protocol allowlist, but the defense-in-depth layer is only as strong as the regex.

**Risk:** If bleach is bypassed (e.g., via a novel mutation XSS technique), an attacker who controls a feed's content can execute JavaScript in every visitor's browser, including admin sessions.

**Recommendation:**
- Consider re-sanitizing content at **render time** as well, not just write time. This protects against stored payloads from before a bleach fix.
- Pin bleach to a specific minor version and monitor for security advisories.
- Add a CSP `script-src` nonce or hash to further limit the blast radius. Currently `script-src 'self'` is set, which helps significantly but does not protect against injection of `<a>` tags with `javascript:` or `<img onerror>` payloads if they somehow survive sanitization (bleach removes `onerror`, but the point is defense-in-depth).

---

### 2. Missing CSRF Protection on State-Changing Admin POST Endpoints

**Severity:** Medium
**File:** `src/main.py` (lines 2559-2674)
**Category:** Authentication and Authorization

**Description:**
Admin routes are protected by session cookie verification (HMAC-signed, HttpOnly, SameSite=Lax). The `SameSite=Lax` attribute provides partial CSRF protection: it blocks cross-site POST requests from forms on attacker-controlled sites in modern browsers. However:

1. There is no explicit CSRF token validated on POST/PUT/DELETE operations. If SameSite enforcement is relaxed (e.g., older browsers, or specific redirect-based scenarios), an attacker could forge requests.
2. The logout endpoint (`/admin/logout`, POST) clears the session -- a CSRF-triggered logout is low-impact but still a nuisance vector.
3. The `_method=DELETE` override pattern (line 2636) processes form data where `_method` field determines action, which is a CSRF-via-POST vector if SameSite is bypassed.

**Risk:** In browsers without SameSite support, or through redirect chains that cause cookies to be sent, an attacker could trigger admin actions (add/remove feeds, trigger regeneration) on behalf of an authenticated admin who visits a malicious page.

**Recommendation:**
- Add a per-session CSRF token (generated at login, stored in the signed session cookie payload, validated on each POST/PUT/DELETE).
- Alternatively, require a custom request header (e.g., `X-Requested-With`) on all mutating admin endpoints, which cannot be set by cross-origin forms.

---

### 3. Information Disclosure in Configuration Error Response

**Severity:** Medium
**File:** `src/main.py` (lines 2549-2556)
**Category:** Data Exposure

**Description:**
When auth secrets are not configured, `_check_auth_secrets()` returns an HTML response listing the exact missing secret names:

```python
f"<p>{', '.join(missing)} not configured. "
f"Set the required secrets for admin/auth functionality.</p>"
```

This reveals the internal configuration variable names (`SESSION_SECRET`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`) to any unauthenticated user who visits `/auth/github` or `/admin`.

**Risk:** Attacker gains knowledge of the authentication infrastructure (GitHub OAuth) and specific secret names, aiding targeted attacks.

**Recommendation:**
- Return a generic error message to the user (e.g., "Admin authentication is not configured. Contact the site administrator.").
- Log the specific missing secrets server-side only.

---

### 4. OAuth `redirect_uri` Fallback Derives Origin from Request

**Severity:** Medium
**File:** `src/main.py` (lines 3528-3543)
**Category:** Authentication -- Open Redirect

**Description:**
When `OAUTH_REDIRECT_URI` is not set, the code constructs the redirect URI from `request.url`:

```python
url_str = str(url)
parsed = urlparse(url_str)
origin = f"{parsed.scheme}://{parsed.netloc}"
redirect_uri = f"{origin}/auth/github/callback"
```

The code comment notes that "In Cloudflare Workers, request.url is not user-controlled" -- this is correct for production deployments behind Cloudflare's edge. However, in local development (`wrangler dev`), the Host header could potentially be manipulated by a client to influence the constructed origin. This would cause the OAuth state to be exchanged at an attacker-controlled callback URL.

The production configuration comments recommend setting `OAUTH_REDIRECT_URI`, and the wrangler config documents this, but it is not enforced.

**Risk:** Low in production (Cloudflare Workers normalizes request.url), but Medium in development environments where `wrangler dev` may pass through the Host header. Could lead to OAuth token theft if `OAUTH_REDIRECT_URI` is not set.

**Recommendation:**
- Enforce that `OAUTH_REDIRECT_URI` must be set when `DEPLOYMENT_ENVIRONMENT` is `production`. Return an error if it's missing in production, rather than falling back to request-derived URLs.
- Log a warning when the fallback path is used.

---

### 5. `client_id` Not URL-Encoded in OAuth Authorization URL

**Severity:** Medium
**File:** `src/main.py` (lines 3545-3550)
**Category:** Injection -- URL parameter injection

**Description:**
The OAuth authorization URL is constructed via f-string interpolation without URL-encoding the parameters:

```python
auth_url = (
    f"https://github.com/login/oauth/authorize"
    f"?client_id={client_id}"
    f"&redirect_uri={redirect_uri}"
    f"&scope=read:user"
    f"&state={state}"
)
```

If `client_id` or `redirect_uri` contain special characters (e.g., `&`, `=`, `#`), they could inject additional query parameters or alter the URL structure. In practice, `client_id` is a hex string from GitHub and `state` is from `secrets.token_urlsafe()`, but `redirect_uri` could contain characters that need encoding (e.g., port numbers with colons are fine, but query strings in the configured URI would break).

**Risk:** If `OAUTH_REDIRECT_URI` or `GITHUB_CLIENT_ID` contain unexpected characters, the authorization URL could be malformed, potentially causing the state parameter to be ignored or the redirect to go to an unintended location.

**Recommendation:**
- Use `urllib.parse.urlencode` to construct the query string properly.

---

### 6. Health Endpoint Exposes Aggregate Feed Counts Without Authentication

**Severity:** Low
**File:** `src/main.py` (lines 2218-2266)
**Category:** Data Exposure

**Description:**
The `/health` endpoint returns aggregate feed health statistics (total, healthy, warning, failing, inactive counts) without authentication. While this data is not sensitive per se, it reveals operational information about the instance.

**Risk:** An attacker can learn the number of feeds, how many are failing, and the overall health state. This could inform timing of attacks (e.g., knowing the system is degraded).

**Recommendation:**
- This is an acceptable trade-off for monitoring. Consider rate-limiting or requiring a simple API key if the instance is not public.
- No action required for a public planet aggregator.

---

### 7. Bleach Dependency -- Deprecated Library

**Severity:** Low
**File:** `pyproject.toml` (line 28), `uv.lock` (bleach 6.3.0)
**Category:** Dependency Risks

**Description:**
Bleach was officially deprecated by Mozilla in January 2023. While version 6.x is maintained for security fixes, no new features are being added and the project recommends migrating to alternatives. The current version (6.3.0) has no known CVEs, but future security issues may receive slower patches.

**Risk:** If a bleach bypass is discovered, the fix may be delayed or unavailable, leaving the `|safe` rendered content (Finding #1) vulnerable.

**Recommendation:**
- Evaluate migration to `nh3` (Rust-based HTML sanitizer with Python bindings), which is the recommended replacement. It is faster and has a smaller attack surface.
- If staying with bleach, pin to `>=6.3.0` and set up automated dependency vulnerability scanning.

---

### 8. Session Cookie Lacks `__Host-` Prefix

**Severity:** Low
**File:** `src/auth.py` (lines 169-183)
**Category:** Configuration -- Session Security

**Description:**
The session cookie is named `session` with attributes `HttpOnly; Secure; SameSite=Lax; Path=/`. This is a solid baseline, but it does not use the `__Host-` prefix, which provides additional protections:

- `__Host-` prefix forces `Secure`, `Path=/`, and prohibits `Domain` attribute.
- Without it, a sibling subdomain (if one were compromised) could potentially set a cookie that shadows the session cookie.

**Risk:** Low -- requires compromise of a sibling subdomain on the same registrable domain.

**Recommendation:**
- Rename the cookie to `__Host-session` for additional defense-in-depth.

---

### 9. Dynamic SQL in `_update_feed` Constructs Column Names from Validated Input

**Severity:** Low
**File:** `src/main.py` (lines 2970-2994)
**Category:** Injection -- SQL

**Description:**
The `_update_feed` method builds a dynamic SQL UPDATE statement:

```python
if "is_active" in data:
    updates.append("is_active = ?")
if "title" in data:
    updates.append("title = ?")
sql = f"UPDATE feeds SET {', '.join(updates)} WHERE id = ?"
```

The column names are hardcoded strings (not user-supplied), and values use parameterized binding. This is **not vulnerable to SQL injection** because the column names come from the code's own if-branches, not from user input. However, the pattern of f-string SQL construction is easy to extend unsafely if a future developer adds a branch that interpolates user data into the column name.

**Risk:** No current vulnerability. Theoretical risk of regression if the pattern is extended without care.

**Recommendation:**
- Add a code comment noting that column names must remain hardcoded.
- Consider using an allowlist pattern: `ALLOWED_UPDATE_FIELDS = {"is_active", "title"}` and validating keys against it.

---

### 10. Error Messages in Feed Validation May Leak Internal Details

**Severity:** Low
**File:** `src/main.py` (lines 2789-2795)
**Category:** Data Exposure

**Description:**
In `_validate_feed_url`, non-timeout exceptions return `_truncate_error(e)` directly to the admin user:

```python
return {"valid": False, "error": error_msg}
```

This is then displayed on the admin error page. While the admin is an authenticated user, error messages from `feedparser` or `httpx` could contain internal details like IP addresses, file paths, or stack traces.

**Risk:** Low -- only visible to authenticated admins, but could leak internal network topology.

**Recommendation:**
- Classify errors into user-friendly categories (network error, parse error, timeout) and return generic messages. Log the full details server-side.

---

## Positive Security Controls (No Action Needed)

The following controls were verified as correctly implemented:

### SQL Injection Protection
- **All SQL queries use parameterized binding** via D1's `.prepare().bind()` pattern. No user input is interpolated into SQL strings.
- The one `PRAGMA table_info()` call (line 540) uses table names from a hardcoded `_EXPECTED_COLUMNS` dict, not user input. The `# noqa: S608` suppression is justified.
- `SearchQueryBuilder` correctly escapes LIKE patterns with `escape_like_pattern()` and uses bind parameters.

### SSRF Protection
- `is_safe_url()` (lines 238-288) blocks private IPs, localhost, cloud metadata endpoints (AWS, GCP, Azure, Alibaba, Oracle), `.internal`/`.local` domains, and non-HTTP schemes.
- URL validation runs both before the initial fetch AND after redirects (re-validation at line 926).
- Feed URLs from OPML imports are also SSRF-validated (line 3075).

### XXE Protection
- OPML parsing uses `ET.XMLParser(forbid_dtd=True)` in both `admin.py` (line 76) and `main.py` (line 3042), preventing DOCTYPE declarations and entity expansion.

### Session Security
- HMAC-SHA256 signed cookies with constant-time comparison via `hmac.compare_digest()`.
- Session expiration with configurable TTL (7 days) and grace period (5 seconds).
- `HttpOnly; Secure; SameSite=Lax` cookie attributes.
- OAuth state parameter for CSRF protection on the OAuth flow, using `secrets.token_urlsafe(32)`.

### Content Security Policy
- `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src https: data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`
- `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Strict-Transport-Security`, `Referrer-Policy: strict-origin-when-cross-origin`.
- Applied to all HTML responses via `SECURITY_HEADERS` dict.

### Authentication Gate
- Admin routes use `requires_auth=True` in route definition AND validate session in `_handle_admin()`.
- After session verification, the code re-checks the `admins` table to ensure the user is still active (handles revocation).
- Lite mode correctly disables auth/admin/search routes.

### Input Validation
- `validate_feed_id()` validates feed IDs as positive integers, preventing path traversal.
- Search query length is bounded to 1000 characters with a max of 10 words.
- OPML imports are capped at 100 feeds (`MAX_OPML_FEEDS`).
- Reindex has a 5-minute cooldown to prevent DoS.

### XML Output Safety
- RSS feed content uses CDATA with `]]>` breakout prevention (`]]>` -> `]]]]><![CDATA[>`).
- `strip_xml_control_chars()` removes illegal XML 1.0 control characters at the content processing layer.
- `xml_escape()` in utils.py handles `&`, `<`, `>` for XML contexts.

### Dependency Versions (as of audit date)
| Package | Version | Known CVEs |
|---------|---------|------------|
| bleach | 6.3.0 | None (deprecated project) |
| feedparser | 6.0.12 | None |
| httpx | 0.28.1 | None |
| Jinja2 | 3.1.6 | None |
| MarkupSafe | 3.0.3 | None |

---

## Risk Summary

| # | Finding | Severity | Category |
|---|---------|----------|----------|
| 1 | Stored XSS via `\|safe` on bleach-sanitized feed content | High | Injection |
| 2 | Missing CSRF tokens on admin POST endpoints | Medium | Auth |
| 3 | Config error reveals secret variable names | Medium | Data Exposure |
| 4 | OAuth redirect_uri fallback derives from request | Medium | Auth |
| 5 | OAuth URL parameters not URL-encoded | Medium | Injection |
| 6 | Health endpoint exposes operational data | Low | Data Exposure |
| 7 | Bleach dependency is deprecated | Low | Dependencies |
| 8 | Session cookie lacks `__Host-` prefix | Low | Configuration |
| 9 | Dynamic SQL pattern could regress | Low | Injection |
| 10 | Error messages may leak internals to admins | Low | Data Exposure |

---

## Recommended Priority Actions

1. **Short-term (next deploy):** Fix Finding #3 (replace secret names in error with generic message). Zero code risk, immediate information disclosure reduction.
2. **Short-term:** Fix Finding #5 (use `urlencode` for OAuth URL construction). Minimal code change, prevents potential URL injection.
3. **Medium-term:** Evaluate migrating from bleach to `nh3` (Finding #7) and consider render-time re-sanitization (Finding #1).
4. **Medium-term:** Add CSRF tokens to admin operations (Finding #2).
5. **Medium-term:** Enforce `OAUTH_REDIRECT_URI` in production (Finding #4).
