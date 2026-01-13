# src/main.py
"""
Planet CF - Feed Aggregator for Cloudflare Python Workers

Main Worker entrypoint handling all triggers:
- scheduled(): Hourly cron to enqueue feed fetches
- queue(): Queue consumer for feed fetching
- fetch(): HTTP request handling (generates content on-demand)
"""

import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import secrets
import time
from datetime import datetime
from urllib.parse import parse_qs, urlparse
from xml.sax.saxutils import escape

import feedparser
import httpx
from workers import Response, WorkerEntrypoint

from observability import (
    FeedFetchEvent,
    GenerationEvent,
    PageServeEvent,
    Timer,
    emit_event,
)
from templates import (
    TEMPLATE_ADMIN_DASHBOARD,
    TEMPLATE_INDEX,
    TEMPLATE_SEARCH,
    render_template,
)
from models import BleachSanitizer

# =============================================================================
# Configuration
# =============================================================================

FEED_TIMEOUT_SECONDS = 60  # Max wall time per feed
HTTP_TIMEOUT_SECONDS = 30  # HTTP request timeout
USER_AGENT = "PlanetCF/1.0 (+https://planetcf.com)"
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days

# HTML sanitizer instance (uses settings from types.py)
_sanitizer = BleachSanitizer()

# Cloud metadata endpoints to block (SSRF protection)
BLOCKED_METADATA_IPS = {
    "169.254.169.254",  # AWS/GCP/Azure metadata
    "100.100.100.200",  # Alibaba Cloud metadata
    "192.0.0.192",  # Oracle Cloud metadata
}


# =============================================================================
# Response Helpers
# =============================================================================


def html_response(content: str, cache_max_age: int = 3600) -> Response:
    """Create an HTML response with caching and security headers."""
    csp = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src * data:; "
        "frame-ancestors 'none'"
    )
    return Response(
        content,
        headers={
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": f"public, max-age={cache_max_age}, stale-while-revalidate=60",
            "Content-Security-Policy": csp,
        },
    )


def json_response(data: dict, status: int = 200) -> Response:
    """Create a JSON response."""
    return Response(
        json.dumps(data),
        status=status,
        headers={"Content-Type": "application/json"},
    )


def json_error(message: str, status: int = 400) -> Response:
    """Create a JSON error response."""
    return json_response({"error": message}, status=status)


def redirect_response(location: str) -> Response:
    """Create a redirect response."""
    return Response("", status=302, headers={"Location": location})


def feed_response(content: str, content_type: str, cache_max_age: int = 3600) -> Response:
    """Create a feed response (Atom/RSS/OPML) with caching headers."""
    return Response(
        content,
        headers={
            "Content-Type": f"{content_type}; charset=utf-8",
            "Cache-Control": f"public, max-age={cache_max_age}, stale-while-revalidate=60",
        },
    )


# =============================================================================
# Main Worker Class
# =============================================================================


class Default(WorkerEntrypoint):
    """
    Main Worker entrypoint handling all triggers:
    - scheduled(): Hourly cron to enqueue feed fetches
    - queue(): Queue consumer for feed fetching
    - fetch(): HTTP request handling (generates content on-demand)
    """

    # =========================================================================
    # Cron Handler - Scheduler
    # =========================================================================

    async def scheduled(self, event):
        """
        Hourly cron trigger - enqueue feeds for fetching.
        Content (HTML/RSS/Atom) is generated on-demand by fetch(), not pre-generated.
        """
        return await self._run_scheduler()

    async def _run_scheduler(self):
        """
        Hourly scheduler - enqueue each active feed as a separate message.

        Each feed gets its own queue message to ensure:
        - Isolated retries (only failed feed is retried)
        - Isolated timeouts (slow feed doesn't block others)
        - Accurate dead-lettering (DLQ shows exactly which feeds fail)
        - Parallel processing (consumers can scale independently)
        """

        # Get all active feeds from D1
        result = await self.env.DB.prepare("""
            SELECT id, url, etag, last_modified
            FROM feeds
            WHERE is_active = 1
        """).all()

        feeds = result.results
        enqueue_count = 0

        # Enqueue each feed as a SEPARATE message
        # Do NOT batch multiple feeds into one message
        for feed in feeds:
            message = {
                "feed_id": feed["id"],
                "url": feed["url"],
                "etag": feed.get("etag"),
                "last_modified": feed.get("last_modified"),
                "scheduled_at": datetime.utcnow().isoformat(),
            }

            await self.env.FEED_QUEUE.send(message)
            enqueue_count += 1

        print(f"Scheduler: Enqueued {enqueue_count} feeds as separate messages")

        return {"enqueued": enqueue_count}

    # =========================================================================
    # Queue Handler - Feed Fetcher
    # =========================================================================

    async def queue(self, batch):
        """
        Process a batch of feed messages from the queue.

        Each message contains exactly ONE feed to fetch.
        This ensures isolated retries and timeouts per feed.
        """

        print(f"Feed Fetcher: Received batch of {len(batch.messages)} feed(s)")

        for message in batch.messages:
            feed_job = message.body
            feed_url = feed_job.get("url", "unknown")
            feed_id = feed_job.get("feed_id", 0)

            # Initialize wide event for this feed fetch
            event = FeedFetchEvent(
                feed_id=feed_id,
                feed_url=feed_url,
                queue_message_id=str(getattr(message, "id", "")),
                queue_attempt=getattr(message, "attempts", 1),
            )

            with Timer() as timer:
                try:
                    # Wrap entire feed processing in a timeout
                    # This is WALL TIME, not CPU time - network I/O counts here
                    result = await asyncio.wait_for(
                        self._process_single_feed(feed_job, event), timeout=FEED_TIMEOUT_SECONDS
                    )

                    event.wall_time_ms = timer.elapsed()
                    event.outcome = "success"
                    event.entries_added = result.get("entries_added", 0)
                    event.entries_found = result.get("entries_found", 0)
                    message.ack()

                except TimeoutError:
                    event.wall_time_ms = timer.elapsed()
                    event.outcome = "error"
                    event.error_type = "TimeoutError"
                    event.error_message = f"Timeout after {FEED_TIMEOUT_SECONDS}s"
                    event.error_retriable = True
                    await self._record_feed_error(feed_id, "Timeout")
                    message.retry()

                except Exception as e:
                    event.wall_time_ms = timer.elapsed()
                    event.outcome = "error"
                    event.error_type = type(e).__name__
                    event.error_message = str(e)[:500]
                    event.error_retriable = not isinstance(e, ValueError)
                    await self._record_feed_error(feed_id, str(e))
                    message.retry()

            # Emit wide event (sampling applied)
            emit_event(event)

    async def _process_single_feed(self, job, event: FeedFetchEvent | None = None):
        """
        Fetch, parse, and store a single feed.

        This function should complete within FEED_TIMEOUT_SECONDS.

        Args:
            job: Feed job dict with feed_id, url, etag, last_modified
            event: Optional FeedFetchEvent to populate with details
        """

        feed_id = job["feed_id"]
        url = job["url"]
        etag = job.get("etag")
        last_modified = job.get("last_modified")

        # SSRF protection - validate URL before fetching
        if not self._is_safe_url(url):
            raise ValueError(f"URL failed SSRF validation: {url}")

        # Build conditional request headers (good netizen behavior)
        headers = {"User-Agent": USER_AGENT}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        # Fetch with timeout and track HTTP latency
        with Timer() as http_timer:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
                response = await client.get(url, headers=headers, follow_redirects=True)

        # Populate event with HTTP details
        if event:
            event.http_latency_ms = http_timer.elapsed_ms
            event.http_status = response.status_code
            event.http_cached = response.status_code == 304
            event.http_redirected = bool(response.history)
            event.response_size_bytes = len(response.content) if response.content else 0
            event.etag_present = bool(response.headers.get("etag"))
            event.last_modified_present = bool(response.headers.get("last-modified"))

        # Re-validate final URL after redirects (SSRF protection)
        final_url = str(response.url)
        if final_url != url and not self._is_safe_url(final_url):
            raise ValueError(f"Redirect target failed SSRF validation: {final_url}")

        # Handle 429/503 with Retry-After (good netizen behavior)
        if response.status_code in (429, 503):
            retry_after = response.headers.get("Retry-After")
            error_msg = f"Rate limited (HTTP {response.status_code})"
            if retry_after:
                error_msg += f", retry after {retry_after}"
                await self._set_feed_retry_after(feed_id, retry_after)
            raise httpx.HTTPStatusError(error_msg, request=response.request, response=response)

        # Handle 304 Not Modified - feed hasn't changed
        if response.status_code == 304:
            await self._update_feed_success(feed_id, etag, last_modified)
            return {"status": "not_modified", "entries_added": 0, "entries_found": 0}

        # Handle permanent redirects (301, 308) - update stored URL
        if response.history:
            for resp in response.history:
                if resp.status_code in (301, 308):
                    new_url = str(response.url)
                    await self._update_feed_url(feed_id, new_url)
                    print(f"Feed URL updated: {url} -> {new_url}")
                    break

        response.raise_for_status()

        # Parse feed with feedparser
        feed_data = feedparser.parse(response.text)

        if feed_data.bozo and not feed_data.entries:
            raise ValueError(f"Feed parse error: {feed_data.bozo_exception}")

        # Extract cache headers from response
        new_etag = response.headers.get("etag")
        new_last_modified = response.headers.get("last-modified")

        # Update feed metadata
        await self._update_feed_metadata(feed_id, feed_data.feed, new_etag, new_last_modified)

        # Process and store entries
        entries_added = 0
        entries_found = len(feed_data.entries)
        if event:
            event.entries_found = entries_found

        for entry in feed_data.entries:
            entry_id = await self._upsert_entry(feed_id, entry)
            if entry_id:
                entries_added += 1

        # Mark fetch as successful
        await self._update_feed_success(feed_id, new_etag, new_last_modified)

        print(f"Feed processed: {url}, {entries_added} new/updated entries")
        return {"status": "ok", "entries_added": entries_added, "entries_found": entries_found}

    async def _upsert_entry(self, feed_id, entry):
        """Insert or update a single entry with sanitized content."""

        # Generate stable GUID
        guid = entry.get("id") or entry.get("link") or entry.get("title")
        if not guid:
            return None

        # Extract content (prefer full content over summary)
        content = ""
        if hasattr(entry, "content") and entry.content:
            content = entry.content[0].get("value", "")
        elif hasattr(entry, "summary"):
            content = entry.summary or ""

        # Sanitize HTML (XSS prevention)
        sanitized_content = self._sanitize_html(content)

        # Parse published date
        published_at = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            published_at = datetime(*entry.published_parsed[:6]).isoformat()
        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
            published_at = datetime(*entry.updated_parsed[:6]).isoformat()
        else:
            published_at = datetime.utcnow().isoformat()

        title = entry.get("title", "")

        # Upsert to D1
        result = (
            await self.env.DB.prepare("""
            INSERT INTO entries (feed_id, guid, url, title, author, content, summary, published_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(feed_id, guid) DO UPDATE SET
                title = excluded.title,
                content = excluded.content,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
        """)
            .bind(
                feed_id,
                guid,
                entry.get("link"),
                title,
                entry.get("author"),
                sanitized_content,
                (entry.get("summary") or "")[:500],  # Truncate summary
                published_at,
            )
            .first()
        )

        entry_id = result["id"] if result else None

        # Index for semantic search
        if entry_id and title:
            await self._index_entry_for_search(entry_id, title, sanitized_content)

        return entry_id

    async def _index_entry_for_search(self, entry_id, title, content):
        """Generate embedding and store in Vectorize for semantic search."""

        # Combine title and content for embedding (truncate to model limit)
        text = f"{title}\n\n{content[:2000]}"

        # Generate embedding using Workers AI with cls pooling for accuracy
        embedding_result = await self.env.AI.run(
            "@cf/baai/bge-base-en-v1.5", {"text": [text], "pooling": "cls"}
        )

        vector = embedding_result["data"][0]

        # Upsert to Vectorize with entry_id as the vector ID
        await self.env.SEARCH_INDEX.upsert(
            [
                {
                    "id": str(entry_id),
                    "values": vector,
                    "metadata": {"title": title[:200], "entry_id": entry_id},
                }
            ]
        )

    def _sanitize_html(self, html_content):
        """Sanitize HTML to prevent XSS attacks (CVE-2009-2937 mitigation)."""
        return _sanitizer.clean(html_content)

    def _is_safe_url(self, url):
        """SSRF protection - reject internal/private URLs."""

        try:
            parsed = urlparse(url)
        except Exception as e:
            print(f"URL parse error for {url}: {type(e).__name__}: {e}")
            return False

        # Only allow http/https
        if parsed.scheme not in ("http", "https"):
            return False

        hostname = parsed.hostname.lower() if parsed.hostname else ""

        if not hostname:
            return False

        # Block localhost variants
        if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return False

        # Block cloud metadata endpoints
        if hostname in BLOCKED_METADATA_IPS:
            return False

        # Block private IP ranges
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False
            # Block IPv6 unique local addresses (fd00::/8)
            if ip.version == 6 and ip.packed[0] == 0xFD:
                return False
        except ValueError:
            pass  # Not an IP address

        # Block internal domain patterns
        if hostname.endswith(".internal") or hostname.endswith(".local"):
            return False

        # Block cloud metadata hostnames
        metadata_hosts = [
            "metadata.google.internal",
            "metadata.azure.internal",
            "instance-data",
        ]
        if any(hostname == h or hostname.endswith("." + h) for h in metadata_hosts):
            return False

        return True

    async def _update_feed_success(self, feed_id, etag, last_modified):
        """Mark feed fetch as successful."""
        await (
            self.env.DB.prepare("""
            UPDATE feeds SET
                last_fetch_at = CURRENT_TIMESTAMP,
                last_success_at = CURRENT_TIMESTAMP,
                etag = ?,
                last_modified = ?,
                fetch_error = NULL,
                consecutive_failures = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """)
            .bind(etag, last_modified, feed_id)
            .run()
        )

    async def _record_feed_error(self, feed_id, error_message):
        """Record a feed fetch error."""
        await (
            self.env.DB.prepare("""
            UPDATE feeds SET
                last_fetch_at = CURRENT_TIMESTAMP,
                fetch_error = ?,
                fetch_error_count = fetch_error_count + 1,
                consecutive_failures = consecutive_failures + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """)
            .bind(error_message[:500], feed_id)
            .run()
        )

    async def _update_feed_url(self, feed_id, new_url):
        """Update feed URL after permanent redirect."""
        await (
            self.env.DB.prepare("""
            UPDATE feeds SET
                url = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """)
            .bind(new_url, feed_id)
            .run()
        )

    async def _set_feed_retry_after(self, feed_id, retry_after: str):
        """
        Store Retry-After time for a feed (good netizen behavior).

        The retry_after value can be:
        - A number of seconds (e.g., "3600")
        - An HTTP date (e.g., "Wed, 21 Oct 2015 07:28:00 GMT")
        """
        # Parse retry_after - could be seconds or HTTP date
        try:
            seconds = int(retry_after)
            retry_until = datetime.utcnow().isoformat() + "Z"
            # Add seconds to current time
            from datetime import timedelta

            retry_until = (datetime.utcnow() + timedelta(seconds=seconds)).isoformat() + "Z"
        except ValueError:
            # Assume it's an HTTP date, store as-is for simplicity
            retry_until = retry_after

        await (
            self.env.DB.prepare("""
            UPDATE feeds SET
                fetch_error = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """)
            .bind(f"Rate limited until {retry_until}", feed_id)
            .run()
        )

    async def _update_feed_metadata(self, feed_id, feed_info, etag, last_modified):
        """Update feed title and other metadata from feed content."""
        title = feed_info.get("title")
        site_url = feed_info.get("link")

        await (
            self.env.DB.prepare("""
            UPDATE feeds SET
                title = COALESCE(?, title),
                site_url = COALESCE(?, site_url),
                etag = ?,
                last_modified = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """)
            .bind(title, site_url, etag, last_modified, feed_id)
            .run()
        )

    # =========================================================================
    # HTTP Handler
    # =========================================================================

    async def fetch(self, request):
        """Handle HTTP requests."""

        # Initialize page serve event
        url = request.url
        path = (
            url.pathname
            if hasattr(url, "pathname")
            else url.split("?")[0].split("://", 1)[-1].split("/", 1)[-1]
        )
        if not path.startswith("/"):
            path = "/" + path

        event = PageServeEvent(
            method=request.method,
            path=path,
            user_agent=(request.headers.get("user-agent", ""))[:200],
            referer=(request.headers.get("referer", ""))[:200],
            country=getattr(request.cf, "country", None) if hasattr(request, "cf") else None,
            colo=getattr(request.cf, "colo", None) if hasattr(request, "cf") else None,
        )

        with Timer() as timer:
            try:
                # Public routes
                if path == "/" or path == "/index.html":
                    response = await self._serve_html()
                    event.content_type = "html"

                elif path == "/feed.atom":
                    response = await self._serve_atom()
                    event.content_type = "atom"

                elif path == "/feed.rss":
                    response = await self._serve_rss()
                    event.content_type = "rss"

                elif path == "/feeds.opml":
                    response = await self._export_opml()
                    event.content_type = "opml"

                elif path == "/search":
                    response = await self._search_entries(request)
                    event.content_type = "search"

                elif path.startswith("/static/"):
                    response = await self._serve_static(path)
                    event.content_type = "static"

                # OAuth callback
                elif path == "/auth/github/callback":
                    response = await self._handle_github_callback(request)
                    event.content_type = "auth"

                # Admin routes (require authentication)
                elif path.startswith("/admin"):
                    response = await self._handle_admin(request, path)
                    event.content_type = "admin"

                else:
                    response = Response("Not Found", status=404)
                    event.content_type = "error"

            except Exception as e:
                print(f"Request error for {path}: {type(e).__name__}: {e}")
                event.wall_time_ms = timer.elapsed()
                event.status_code = 500
                emit_event(event)
                raise

        # Finalize and emit event
        event.wall_time_ms = timer.elapsed()
        event.status_code = response.status
        emit_event(event)

        return response

    async def _serve_html(self):
        """
        Generate and serve the HTML page on-demand.

        No KV caching - edge cache handles repeat requests:
        - First request: D1 query + Jinja2 render (~300-500ms)
        - Edge caches response for 1 hour
        - Subsequent requests: 0ms (served from edge)

        For a planet aggregator with ~10-20 cache misses/hour globally,
        this latency is acceptable and eliminates KV complexity.
        """
        html = await self._generate_html()
        return html_response(html)

    async def _generate_html(self, trigger: str = "http", triggered_by: str | None = None):
        """
        Generate the aggregated HTML page on-demand.
        Called by fetch() for / requests. Edge cache handles caching.

        Args:
            trigger: What triggered generation ("http", "cron", "admin_manual")
            triggered_by: Admin username if manually triggered
        """

        # Initialize generation event
        event = GenerationEvent(trigger=trigger, triggered_by=triggered_by)

        with Timer() as total_timer:
            # Get planet config from environment
            planet = self._get_planet_config()

            # Apply retention policy first (delete old entries and their vectors)
            await self._apply_retention_policy()

            # Query entries (last 30 days, max 100 per feed) - track D1 query time
            with Timer() as d1_timer:
                entries_result = await self.env.DB.prepare("""
                    WITH ranked AS (
                        SELECT
                            e.*,
                            f.title as feed_title,
                            f.site_url as feed_site_url,
                            ROW_NUMBER() OVER (PARTITION BY e.feed_id ORDER BY e.published_at DESC) as rn
                        FROM entries e
                        JOIN feeds f ON e.feed_id = f.id
                        WHERE e.published_at >= datetime('now', '-30 days')
                        AND f.is_active = 1
                    )
                    SELECT * FROM ranked WHERE rn <= 100
                    ORDER BY published_at DESC
                    LIMIT 500
                """).all()

                # Get feeds for sidebar
                feeds_result = await self.env.DB.prepare("""
                    SELECT
                        id, title, site_url, last_success_at,
                        CASE WHEN consecutive_failures < 3 THEN 1 ELSE 0 END as is_healthy
                    FROM feeds
                    WHERE is_active = 1
                    ORDER BY title
                """).all()

            event.d1_query_time_ms = d1_timer.elapsed_ms

            entries = entries_result.results
            feeds = feeds_result.results

            # Group entries by date
            entries_by_date = {}
            for entry in entries:
                date_str = entry["published_at"][:10]  # YYYY-MM-DD
                if date_str not in entries_by_date:
                    entries_by_date[date_str] = []

                entry["published_at_formatted"] = self._format_datetime(entry["published_at"])
                entries_by_date[date_str].append(entry)

            for feed in feeds:
                feed["last_success_at_relative"] = self._relative_time(feed["last_success_at"])

            # Render template - track template time
            with Timer() as render_timer:
                html = render_template(
                    TEMPLATE_INDEX,
                    planet=planet,
                    entries_by_date=entries_by_date,
                    feeds=feeds,
                    generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
                )

            event.template_render_time_ms = render_timer.elapsed_ms

        # Populate and emit event
        event.wall_time_ms = total_timer.elapsed_ms
        event.entries_total = len(entries)
        event.feeds_active = len(feeds)
        event.feeds_healthy = sum(1 for f in feeds if f.get("is_healthy"))
        event.html_size_bytes = len(html.encode("utf-8"))
        emit_event(event)

        return html

    async def _apply_retention_policy(self):
        """Delete entries older than 30 days or beyond 100 per feed, and clean up vectors."""

        # Get IDs of entries to delete
        to_delete = await self.env.DB.prepare("""
            WITH ranked_entries AS (
                SELECT
                    id,
                    feed_id,
                    published_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY feed_id
                        ORDER BY published_at DESC
                    ) as rn
                FROM entries
            ),
            entries_to_delete AS (
                SELECT id FROM ranked_entries
                WHERE rn > 100
                OR published_at < datetime('now', '-30 days')
            )
            SELECT id FROM entries_to_delete
        """).all()

        deleted_ids = [row["id"] for row in to_delete.results]

        if deleted_ids:
            # Delete vectors from Vectorize
            await self.env.SEARCH_INDEX.deleteByIds([str(id) for id in deleted_ids])

            # Delete entries from D1 (in batches to stay under parameter limit)
            for i in range(0, len(deleted_ids), 50):
                batch = deleted_ids[i : i + 50]
                placeholders = ",".join("?" * len(batch))
                await (
                    self.env.DB.prepare(f"""
                    DELETE FROM entries WHERE id IN ({placeholders})
                """)
                    .bind(*batch)
                    .run()
                )

            print(f"Retention: Deleted {len(deleted_ids)} old entries and their vectors")

    def _format_datetime(self, iso_string):
        """Format ISO datetime string for display."""
        if not iso_string:
            return ""
        try:
            dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
            return dt.strftime("%B %d, %Y at %I:%M %p")
        except (ValueError, AttributeError):
            return iso_string

    def _relative_time(self, iso_string):
        """Convert ISO datetime to relative time (e.g., '2 hours ago')."""
        if not iso_string:
            return "never"
        try:
            dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
            now = datetime.utcnow()
            delta = now - dt.replace(tzinfo=None)

            if delta.days > 30:
                return f"{delta.days // 30} months ago"
            elif delta.days > 0:
                return f"{delta.days} days ago"
            elif delta.seconds > 3600:
                return f"{delta.seconds // 3600} hours ago"
            elif delta.seconds > 60:
                return f"{delta.seconds // 60} minutes ago"
            else:
                return "just now"
        except (ValueError, AttributeError):
            return "unknown"

    async def _serve_atom(self):
        """Generate and serve Atom feed on-demand."""
        entries = await self._get_recent_entries(50)
        planet = self._get_planet_config()
        atom = self._generate_atom_feed(planet, entries)
        return feed_response(atom, "application/atom+xml")

    async def _serve_rss(self):
        """Generate and serve RSS feed on-demand."""
        entries = await self._get_recent_entries(50)
        planet = self._get_planet_config()
        rss = self._generate_rss_feed(planet, entries)
        return feed_response(rss, "application/rss+xml")

    async def _get_recent_entries(self, limit):
        """Query recent entries for feeds."""

        result = (
            await self.env.DB.prepare("""
            SELECT e.*, f.title as feed_title, f.site_url as feed_site_url
            FROM entries e
            JOIN feeds f ON e.feed_id = f.id
            WHERE f.is_active = 1
            ORDER BY e.published_at DESC
            LIMIT ?
        """)
            .bind(limit)
            .all()
        )

        return result.results

    def _get_planet_config(self):
        """Get planet configuration from environment."""
        return {
            "name": getattr(self.env, "PLANET_NAME", None) or "Planet CF",
            "description": getattr(self.env, "PLANET_DESCRIPTION", None)
            or "Aggregated posts from Cloudflare employees and community",
            "link": getattr(self.env, "PLANET_URL", None) or "https://planetcf.com",
        }

    def _generate_atom_feed(self, planet, entries):
        """Generate Atom 1.0 feed XML."""

        feed_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>{escape(planet["name"])}</title>
  <subtitle>{escape(planet["description"])}</subtitle>
  <link href="{planet["link"]}" rel="alternate"/>
  <link href="{planet["link"]}/feed.atom" rel="self"/>
  <id>{planet["link"]}/</id>
  <updated>{datetime.utcnow().isoformat()}Z</updated>
'''
        for entry in entries:
            feed_xml += f'''  <entry>
    <title>{escape(entry.get("title", ""))}</title>
    <link href="{escape(entry.get("url", ""))}" rel="alternate"/>
    <id>{escape(entry.get("guid", entry.get("url", "")))}</id>
    <published>{entry.get("published_at", "")}Z</published>
    <author><name>{escape(entry.get("author", entry.get("feed_title", "")))}</name></author>
    <content type="html">{escape(entry.get("content", ""))}</content>
  </entry>
'''
        feed_xml += "</feed>"
        return feed_xml

    def _generate_rss_feed(self, planet, entries):
        """Generate RSS 2.0 feed XML."""

        feed_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{escape(planet["name"])}</title>
    <description>{escape(planet["description"])}</description>
    <link>{planet["link"]}</link>
    <atom:link href="{planet["link"]}/feed.rss" rel="self" type="application/rss+xml"/>
    <lastBuildDate>{datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")}</lastBuildDate>
'''
        for entry in entries:
            feed_xml += f"""    <item>
      <title>{escape(entry.get("title", ""))}</title>
      <link>{escape(entry.get("url", ""))}</link>
      <guid>{escape(entry.get("guid", entry.get("url", "")))}</guid>
      <pubDate>{entry.get("published_at", "")}</pubDate>
      <author>{escape(entry.get("author", ""))}</author>
      <description><![CDATA[{entry.get("content", "")}]]></description>
    </item>
"""
        feed_xml += """  </channel>
</rss>"""
        return feed_xml

    async def _export_opml(self):
        """Export all active feeds as OPML."""
        import html

        feeds = await self.env.DB.prepare("""
            SELECT url, title, site_url
            FROM feeds
            WHERE is_active = 1
            ORDER BY title
        """).all()

        owner_name = getattr(self.env, "PLANET_OWNER_NAME", "Planet CF")

        opml = f"""<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head>
    <title>Planet CF Subscriptions</title>
    <dateCreated>{datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")}</dateCreated>
    <ownerName>{owner_name}</ownerName>
  </head>
  <body>
    <outline text="Planet CF Feeds" title="Planet CF Feeds">
"""

        for feed in feeds.results:
            title = html.escape(feed["title"] or feed["url"])
            xml_url = html.escape(feed["url"])
            html_url = html.escape(feed["site_url"] or "")
            opml += f'      <outline type="rss" text="{title}" title="{title}" xmlUrl="{xml_url}" htmlUrl="{html_url}"/>\n'

        opml += """    </outline>
  </body>
</opml>"""

        return Response(
            opml,
            headers={
                "Content-Type": "application/xml; charset=utf-8",
                "Content-Disposition": 'attachment; filename="planetcf-feeds.opml"',
            },
        )

    async def _search_entries(self, request):
        """Search entries by semantic similarity."""

        # Parse query string
        url_str = str(request.url)
        query = ""
        if "?" in url_str:
            qs = parse_qs(url_str.split("?", 1)[1])
            query = qs.get("q", [""])[0]

        if not query or len(query) < 2:
            return json_error("Query too short")

        # Generate embedding for search query
        embedding_result = await self.env.AI.run(
            "@cf/baai/bge-base-en-v1.5", {"text": [query], "pooling": "cls"}
        )
        query_vector = embedding_result["data"][0]

        # Search Vectorize
        results = await self.env.SEARCH_INDEX.query(
            query_vector, {"topK": 20, "returnMetadata": True}
        )

        # Fetch full entries from D1
        if not results.matches:
            # Return HTML search page with no results
            planet = self._get_planet_config()
            html = render_template(TEMPLATE_SEARCH, planet=planet, query=query, results=[])
            return html_response(html, cache_max_age=0)

        entry_ids = [int(m.id) for m in results.matches]
        placeholders = ",".join("?" * len(entry_ids))

        entries = (
            await self.env.DB.prepare(f"""
            SELECT e.*, f.title as feed_title, f.site_url as feed_site_url
            FROM entries e
            JOIN feeds f ON e.feed_id = f.id
            WHERE e.id IN ({placeholders})
        """)
            .bind(*entry_ids)
            .all()
        )

        # Sort by Vectorize score
        entry_map = {e["id"]: e for e in entries.results}
        sorted_results = [
            {**entry_map[int(m.id)], "score": m.score}
            for m in results.matches
            if int(m.id) in entry_map
        ]

        # Return HTML search results page
        planet = self._get_planet_config()
        html = render_template(TEMPLATE_SEARCH, planet=planet, query=query, results=sorted_results)
        return html_response(html, cache_max_age=0)

    async def _serve_static(self, path):
        """Serve static files."""
        # In production, static files would be served via assets binding
        # For now, just return CSS inline
        if path == "/static/style.css":
            css = self._get_default_css()
            return Response(
                css,
                headers={
                    "Content-Type": "text/css",
                    "Cache-Control": "public, max-age=86400",
                },
            )
        return Response("Not Found", status=404)

    def _get_default_css(self):
        """Return default CSS styling."""
        return """
/* Planet CF Styles */
:root {
    --primary-color: #f38020;
    --text-color: #333;
    --bg-color: #fff;
    --sidebar-bg: #f5f5f5;
    --border-color: #ddd;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    line-height: 1.6;
    color: var(--text-color);
    background: var(--bg-color);
}

header {
    background: var(--primary-color);
    color: white;
    padding: 2rem;
    text-align: center;
}

header h1 { margin-bottom: 0.5rem; }
header a { color: white; }

.search-form {
    margin-top: 1rem;
    display: flex;
    justify-content: center;
    gap: 0.5rem;
}

.search-form input {
    padding: 0.5rem 1rem;
    border: none;
    border-radius: 4px;
    width: 300px;
}

.search-form button {
    padding: 0.5rem 1rem;
    background: white;
    color: var(--primary-color);
    border: none;
    border-radius: 4px;
    cursor: pointer;
}

.container {
    display: grid;
    grid-template-columns: 1fr 300px;
    gap: 2rem;
    max-width: 1200px;
    margin: 2rem auto;
    padding: 0 1rem;
}

main { min-width: 0; }

.day { margin-bottom: 2rem; }
.day h2 {
    border-bottom: 2px solid var(--primary-color);
    padding-bottom: 0.5rem;
    margin-bottom: 1rem;
}

article {
    background: white;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 1rem;
}

article h3 { margin-bottom: 0.5rem; }
article h3 a { color: var(--primary-color); text-decoration: none; }
article h3 a:hover { text-decoration: underline; }

.meta {
    color: #666;
    font-size: 0.9rem;
    margin-bottom: 1rem;
}

.content {
    overflow-wrap: break-word;
}

.content img {
    max-width: 100%;
    height: auto;
}

.content pre {
    background: #f5f5f5;
    padding: 1rem;
    overflow-x: auto;
    border-radius: 4px;
}

.sidebar {
    background: var(--sidebar-bg);
    padding: 1.5rem;
    border-radius: 8px;
    height: fit-content;
    position: sticky;
    top: 1rem;
}

.sidebar h2 {
    margin-bottom: 1rem;
    font-size: 1.1rem;
}

.feeds {
    list-style: none;
}

.feeds li {
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--border-color);
}

.feeds li.unhealthy { color: #c00; }
.feeds .last-updated {
    display: block;
    font-size: 0.8rem;
    color: #666;
}

footer {
    text-align: center;
    padding: 2rem;
    background: #f5f5f5;
    margin-top: 2rem;
}

footer a { color: var(--primary-color); }

/* Search results */
.search-results {
    list-style: none;
}

.search-results li {
    background: white;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 1rem;
}

.search-results h3 { margin-bottom: 0.5rem; }
.search-results .score { margin-left: 1rem; color: #666; }

/* Admin styles */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 1rem 0;
}

th, td {
    padding: 0.75rem;
    text-align: left;
    border-bottom: 1px solid var(--border-color);
}

th { background: var(--sidebar-bg); }
tr.unhealthy { background: #fee; }

.add-feed-form {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1rem;
}

.add-feed-form input {
    padding: 0.5rem;
    border: 1px solid var(--border-color);
    border-radius: 4px;
}

.add-feed-form input[type="url"] { flex: 1; }

button {
    padding: 0.5rem 1rem;
    background: var(--primary-color);
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
}

button:hover { opacity: 0.9; }

/* Responsive */
@media (max-width: 768px) {
    .container {
        grid-template-columns: 1fr;
    }
    .sidebar {
        position: static;
    }
    .search-form input { width: 200px; }
}
"""

    # =========================================================================
    # Admin Routes
    # =========================================================================

    async def _handle_admin(self, request, path):
        """Handle admin routes with GitHub OAuth."""

        # Verify signed session cookie (stateless, no KV)
        session = self._verify_signed_cookie(request)
        if not session:
            return self._redirect_to_github_oauth()

        # Verify user is still an authorized admin (may have been revoked)
        admin = (
            await self.env.DB.prepare(
                "SELECT * FROM admins WHERE github_username = ? AND is_active = 1"
            )
            .bind(session["github_username"])
            .first()
        )

        if not admin:
            return Response("Unauthorized: Not an admin", status=403)

        # Route admin requests
        method = request.method

        if path == "/admin" or path == "/admin/":
            return await self._serve_admin_dashboard(admin)

        if path == "/admin/feeds" and method == "GET":
            return await self._list_feeds()

        if path == "/admin/feeds" and method == "POST":
            return await self._add_feed(request, admin)

        if path.startswith("/admin/feeds/") and method == "DELETE":
            feed_id = path.split("/")[-1]
            return await self._remove_feed(feed_id, admin)

        if path.startswith("/admin/feeds/") and method == "PUT":
            feed_id = path.split("/")[-1]
            return await self._update_feed(request, feed_id, admin)

        if path.startswith("/admin/feeds/") and method == "POST":
            # Handle form override for DELETE
            form = await request.formData()
            if form.get("_method") == "DELETE":
                feed_id = path.split("/")[-1]
                return await self._remove_feed(feed_id, admin)
            return Response("Method not allowed", status=405)

        if path == "/admin/import-opml" and method == "POST":
            return await self._import_opml(request, admin)

        if path == "/admin/regenerate" and method == "POST":
            return await self._trigger_regenerate(admin)

        if path == "/admin/dlq" and method == "GET":
            return await self._view_dlq()

        if path == "/admin/audit" and method == "GET":
            return await self._view_audit_log()

        if path == "/admin/logout" and method == "POST":
            return self._logout(request)

        return Response("Not Found", status=404)

    async def _serve_admin_dashboard(self, admin):
        """Serve the admin dashboard."""
        feeds_result = await self.env.DB.prepare("""
            SELECT * FROM feeds ORDER BY title
        """).all()

        planet = self._get_planet_config()
        html = render_template(
            TEMPLATE_ADMIN_DASHBOARD,
            planet=planet,
            admin=admin,
            feeds=feeds_result.results,
        )
        return html_response(html, cache_max_age=0)

    async def _list_feeds(self):
        """List all feeds as JSON."""
        result = await self.env.DB.prepare("""
            SELECT * FROM feeds ORDER BY title
        """).all()
        return json_response({"feeds": result.results})

    async def _add_feed(self, request, admin):
        """Add a new feed."""
        form = await request.formData()
        url = form.get("url")
        title = form.get("title")

        if not url:
            return json_error("URL is required")

        # Validate URL (SSRF protection)
        if not self._is_safe_url(url):
            return json_error("Invalid or unsafe URL")

        try:
            result = (
                await self.env.DB.prepare("""
                INSERT INTO feeds (url, title, is_active)
                VALUES (?, ?, 1)
                RETURNING id
            """)
                .bind(url, title)
                .first()
            )

            feed_id = result["id"] if result else None

            # Audit log
            await self._log_admin_action(
                admin["id"], "add_feed", "feed", feed_id, {"url": url, "title": title}
            )

            # Redirect back to admin
            return redirect_response("/admin")

        except Exception as e:
            return json_error(str(e), status=500)

    async def _remove_feed(self, feed_id, admin):
        """Remove a feed."""
        try:
            feed_id = int(feed_id)

            # Get feed info for audit log
            feed = (
                await self.env.DB.prepare("SELECT * FROM feeds WHERE id = ?").bind(feed_id).first()
            )

            if not feed:
                return json_error("Feed not found", status=404)

            # Delete feed (entries will cascade)
            await self.env.DB.prepare("DELETE FROM feeds WHERE id = ?").bind(feed_id).run()

            # Audit log
            await self._log_admin_action(
                admin["id"],
                "remove_feed",
                "feed",
                feed_id,
                {"url": feed["url"], "title": feed.get("title")},
            )

            # Redirect back to admin
            return redirect_response("/admin")

        except Exception as e:
            return json_error(str(e), status=500)

    async def _update_feed(self, request, feed_id, admin):
        """Update a feed (enable/disable)."""
        try:
            feed_id = int(feed_id)
            data = await request.json()

            is_active = data.get("is_active", 1)

            await (
                self.env.DB.prepare("""
                UPDATE feeds SET
                    is_active = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """)
                .bind(is_active, feed_id)
                .run()
            )

            # Audit log
            await self._log_admin_action(
                admin["id"], "update_feed", "feed", feed_id, {"is_active": is_active}
            )

            return json_response({"success": True})

        except Exception as e:
            return json_error(str(e), status=500)

    async def _import_opml(self, request, admin):
        """Import feeds from uploaded OPML file. Admin only."""
        import xml.etree.ElementTree as ET

        form = await request.formData()
        opml_file = form.get("opml")

        if not opml_file:
            return json_error("No file uploaded")

        content = await opml_file.text()

        # Parse OPML
        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            return json_error(f"Invalid OPML: {e}")

        imported = 0
        skipped = 0
        errors = []

        for outline in root.iter("outline"):
            xml_url = outline.get("xmlUrl")
            if not xml_url:
                continue

            title = outline.get("title") or outline.get("text") or xml_url
            html_url = outline.get("htmlUrl")

            # Validate URL (SSRF protection)
            if not self._is_safe_url(xml_url):
                errors.append(f"Skipped unsafe URL: {xml_url}")
                continue

            try:
                await (
                    self.env.DB.prepare("""
                    INSERT INTO feeds (url, title, site_url, is_active)
                    VALUES (?, ?, ?, 1)
                    ON CONFLICT(url) DO NOTHING
                """)
                    .bind(xml_url, title, html_url)
                    .run()
                )
                imported += 1
            except Exception as e:
                skipped += 1
                errors.append(f"Failed to import {xml_url}: {e}")

        # Audit log
        await self._log_admin_action(
            admin["id"],
            "import_opml",
            "feeds",
            None,
            {"imported": imported, "skipped": skipped, "errors": errors[:10]},
        )

        # Redirect back to admin
        return redirect_response("/admin")

    async def _trigger_regenerate(self, admin):
        """Force regeneration by clearing edge cache (not really possible, but log the action)."""
        # In practice, edge cache expires on its own. This is more of a manual trigger to re-fetch.
        await self._log_admin_action(admin["id"], "manual_refresh", None, None, {})

        # Queue all active feeds for immediate fetch
        await self._run_scheduler()

        return redirect_response("/admin")

    async def _view_dlq(self):
        """View dead letter queue contents."""
        # DLQ is managed by Cloudflare Queues - this would need queue API access
        return json_response({"message": "DLQ viewing requires Cloudflare dashboard"})

    async def _view_audit_log(self):
        """View audit log."""
        result = await self.env.DB.prepare("""
            SELECT al.*, a.github_username, a.display_name
            FROM audit_log al
            LEFT JOIN admins a ON al.admin_id = a.id
            ORDER BY al.created_at DESC
            LIMIT 100
        """).all()
        return json_response({"audit_log": result.results})

    async def _log_admin_action(self, admin_id, action, target_type, target_id, details):
        """Log an admin action to the audit log."""
        await (
            self.env.DB.prepare("""
            INSERT INTO audit_log (admin_id, action, target_type, target_id, details)
            VALUES (?, ?, ?, ?, ?)
        """)
            .bind(admin_id, action, target_type, target_id, json.dumps(details))
            .run()
        )

    # =========================================================================
    # OAuth & Session Management
    # =========================================================================

    def _verify_signed_cookie(self, request):
        """
        Verify the signed session cookie (stateless, no KV).
        Cookie format: base64(json_payload).signature
        """

        cookies = request.headers.get("Cookie", "")
        session_cookie = None
        for cookie in cookies.split(";"):
            if cookie.strip().startswith("session="):
                session_cookie = cookie.strip()[8:]
                break

        if not session_cookie or "." not in session_cookie:
            return None

        try:
            payload_b64, signature = session_cookie.rsplit(".", 1)

            # Verify signature
            expected_sig = hmac.new(
                self.env.SESSION_SECRET.encode(), payload_b64.encode(), hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(signature, expected_sig):
                return None

            # Decode payload
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))

            # Check expiration
            if payload.get("exp", 0) < time.time():
                return None

            return payload
        except Exception as e:
            print(f"Session cookie verification failed: {type(e).__name__}: {e}")
            return None

    def _redirect_to_github_oauth(self):
        """Redirect to GitHub OAuth authorization."""

        state = secrets.token_urlsafe(32)
        planet_url = getattr(self.env, "PLANET_URL", "https://planetcf.com")
        client_id = getattr(self.env, "GITHUB_CLIENT_ID", "")

        auth_url = (
            f"https://github.com/login/oauth/authorize"
            f"?client_id={client_id}"
            f"&redirect_uri={planet_url}/auth/github/callback"
            f"&scope=read:user"
            f"&state={state}"
        )

        return Response(
            "",
            status=302,
            headers={
                "Location": auth_url,
                "Set-Cookie": f"oauth_state={state}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=600",
            },
        )

    async def _handle_github_callback(self, request):
        """Handle GitHub OAuth callback."""

        url_str = str(request.url)
        qs = parse_qs(url_str.split("?", 1)[1]) if "?" in url_str else {}
        code = qs.get("code", [""])[0]
        state = qs.get("state", [""])[0]

        if not code:
            return Response("Missing authorization code", status=400)

        client_id = getattr(self.env, "GITHUB_CLIENT_ID", "")
        client_secret = getattr(self.env, "GITHUB_CLIENT_SECRET", "")

        # Exchange code for access token
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                },
                headers={"Accept": "application/json"},
            )

        token_data = token_response.json()
        access_token = token_data.get("access_token")

        if not access_token:
            return Response("Failed to get access token", status=400)

        # Fetch user info
        async with httpx.AsyncClient() as client:
            user_response = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )

        user_data = user_response.json()
        github_username = user_data.get("login")
        github_id = user_data.get("id")

        # Verify user is an admin
        admin = (
            await self.env.DB.prepare(
                "SELECT * FROM admins WHERE github_username = ? AND is_active = 1"
            )
            .bind(github_username)
            .first()
        )

        if not admin:
            return Response("Unauthorized: Not an admin", status=403)

        # Update admin's github_id and last_login_at
        await (
            self.env.DB.prepare("""
            UPDATE admins SET github_id = ?, last_login_at = CURRENT_TIMESTAMP
            WHERE github_username = ?
        """)
            .bind(github_id, github_username)
            .run()
        )

        # Create signed session cookie (stateless, no KV)
        session_cookie = self._create_signed_cookie(
            {
                "github_username": github_username,
                "github_id": github_id,
                "avatar_url": user_data.get("avatar_url"),
                "exp": int(time.time()) + SESSION_TTL_SECONDS,
            }
        )

        return Response(
            "",
            status=302,
            headers={
                "Location": "/admin",
                "Set-Cookie": f"session={session_cookie}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age={SESSION_TTL_SECONDS}",
            },
        )

    def _create_signed_cookie(self, payload):
        """Create an HMAC-signed cookie. Format: base64(json_payload).signature"""

        payload_json = json.dumps(payload)
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode()

        signature = hmac.new(
            self.env.SESSION_SECRET.encode(), payload_b64.encode(), hashlib.sha256
        ).hexdigest()

        return f"{payload_b64}.{signature}"

    def _logout(self, request):
        """Log out by clearing the session cookie (stateless - nothing to delete)."""

        return Response(
            "",
            status=302,
            headers={
                "Location": "/",
                "Set-Cookie": "session=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0",
            },
        )
