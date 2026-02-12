# Feed Debugging Guide

Lessons learned from debugging feed display issues.

## Common Issues and Diagnostic Steps

### 0. Content in Markdown Format (boristane.com case)

**Symptoms**: Content displays with raw Markdown syntax like `[text](url)`, `## Heading`, or triple backticks.

**Root Cause**: The RSS feed provides content in Markdown format within `<content:encoded>` instead of HTML. Planet CF expects HTML and doesn't process Markdown.

**Diagnosis**:
```bash
# Check if content:encoded contains Markdown
curl -s "https://example.com/rss.xml" | grep -A5 "content:encoded" | head -20
# Look for: [text](url), ##, ```, >, - lists, etc.
```

**Potential Fixes**:
1. Add Markdown-to-HTML conversion (e.g., using `mistune` or `commonmark`)
2. Detect Markdown patterns and convert before sanitization
3. Contact feed author to provide HTML content

**Current Status**: Not implemented - feeds providing Markdown will display raw syntax.

### 1. Content Being Stripped (jilles.me case)

**Symptoms**: Code blocks or formatted content appears mangled, truncated, or missing.

**Root Cause**: The HTML sanitizer (`BleachSanitizer` in `models.py`) strips tags not in `ALLOWED_TAGS`.

**Diagnosis**:
```bash
# Check what HTML structure the source uses
curl -s "https://example.com/article" | grep -E "(<pre|<code|class=.*code)"

# Check what's stored in DB
npx wrangler d1 execute planetcf --remote --command "SELECT substr(content, 1, 500) FROM entries WHERE feed_id = X"
```

**Fix**: Add necessary tags to `ALLOWED_TAGS` and attributes to `ALLOWED_ATTRS` in `src/models.py`.

---

### 2. Feed Returns 304 Not Modified (ETag caching)

**Symptoms**: Feed shows `last_success_at` updated but entries aren't created/updated.

**Root Cause**: Feed has cached ETag. Server returns 304, so entries aren't re-processed.

**Diagnosis**:
```bash
# Check feed's cached ETag
npx wrangler d1 execute planetcf --remote --command "SELECT etag, last_modified FROM feeds WHERE id = X"
```

**Fix**: Clear ETag to force full re-fetch:
```bash
npx wrangler d1 execute planetcf --remote --command "UPDATE feeds SET etag = NULL, last_modified = NULL WHERE id = X"
```

---

### 3. Entries Outside Retention Window

**Symptoms**: Feed fetches successfully but few/no entries appear.

**Root Cause**: Entries older than `RETENTION_DAYS` (default 90) are filtered out.

**Diagnosis**:
```bash
# Check retention settings
grep RETENTION wrangler.jsonc

# Check entry dates in feed
curl -s "https://example.com/rss.xml" | grep -E "<pubDate|<updated"
```

**Fix**: Only entries within retention window are kept. This is by design.

---

### 4. Feed Parsing Errors

**Symptoms**: `consecutive_failures > 0`, `fetch_error` has message.

**Diagnosis**:
```bash
# Check feed health
npx wrangler d1 execute planetcf --remote --command "SELECT url, consecutive_failures, fetch_error FROM feeds WHERE id = X"

# Test feed directly
curl -s "https://example.com/rss.xml" | head -50
```

---

### 5. Summary-Only Feeds

**Symptoms**: Entries only have short descriptions, no full content.

**Root Cause**: RSS feed only has `<description>` (summary), not `<content:encoded>`.

**Diagnosis**:
```bash
# Check if feed has full content
curl -s "https://example.com/rss.xml" | grep -E "content:encoded|<content"
```

**Note**: Planet CF displays whatever content the feed provides. It does not fetch full article content from the original URL. If a feed only provides summaries, entries will show summaries.

---

## Debugging Workflow

1. **Check feed status**:
   ```bash
   npx wrangler d1 execute planetcf --remote --command "SELECT * FROM feeds WHERE url LIKE '%example%'"
   ```

2. **Check entry count**:
   ```bash
   npx wrangler d1 execute planetcf --remote --command "SELECT COUNT(*) FROM entries WHERE feed_id = X"
   ```

3. **Check entry content**:
   ```bash
   npx wrangler d1 execute planetcf --remote --command "SELECT id, title, substr(content, 1, 200) FROM entries WHERE feed_id = X LIMIT 3"
   ```

4. **Force re-fetch** (if needed):
   ```bash
   # Clear cache headers
   npx wrangler d1 execute planetcf --remote --command "UPDATE feeds SET etag = NULL, last_modified = NULL WHERE id = X"

   # Delete entries to re-process
   npx wrangler d1 execute planetcf --remote --command "DELETE FROM entries WHERE feed_id = X"

   # Trigger scheduler (via admin panel or wait for hourly cron)
   ```

5. **Check rendered output**:
   ```bash
   curl -s "https://your-instance.workers.dev" | grep -A10 "example.com"
   ```
