# Planet CF Specification

**Version:** 1.0 Draft  
**Date:** January 2026  
**Status:** Proposal  
**Domain:** https://planetcf.com

## 1. Overview

Planet CF is a feed aggregator that collects blog posts from Cloudflare employees and community members, aggregating them into a single reverse-chronological HTML page and RSS/Atom feed. Built entirely on Cloudflare's Python Workers platform.

### 1.1 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                    CLOUDFLARE EDGE                                       │
│                                   https://planetcf.com                                   │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│   INGESTION PIPELINE                              STORAGE                                │
│   ──────────────────                              ───────                                │
│                                                                                          │
│   ┌──────────────┐                               ┌──────────────────────────────────┐   │
│   │ Cron Trigger │                               │              D1                  │   │
│   │  (hourly)    │                               │  ┌─────────┬─────────┬────────┐  │   │
│   └──────┬───────┘                               │  │  feeds  │ entries │ admins │  │   │
│          │                                       │  └─────────┴─────────┴────────┘  │   │
│          ▼                                       └──────────────────────────────────┘   │
│   ┌──────────────┐      ┌──────────────────┐                     │                      │
│   │  Scheduler   │─────▶│    Feed Queue    │                     │                      │
│   │   Worker     │      │  (one msg/feed)  │                     │                      │
│   └──────────────┘      └────────┬─────────┘                     │                      │
│                                  │                               │                      │
│                    ┌─────────────┼─────────────┐                 │                      │
│                    ▼             ▼             ▼                 │                      │
│             ┌───────────┐ ┌───────────┐ ┌───────────┐           │                      │
│             │ Consumer  │ │ Consumer  │ │ Consumer  │           │                      │
│             │  (fetch,  │ │  (fetch,  │ │  (fetch,  │───────────┤                      │
│             │  parse,   │ │  parse,   │ │  parse,   │           │                      │
│             │  embed)   │ │  embed)   │ │  embed)   │           │                      │
│             └─────┬─────┘ └─────┬─────┘ └─────┬─────┘           │                      │
│                   │             │             │                  │                      │
│                   └─────────────┼─────────────┘                  │                      │
│                                 ▼                                │                      │
│                         ┌──────────────┐                        │                      │
│                         │  Dead Letter │  (failed after 3)      │                      │
│                         │    Queue     │                        │                      │
│                         └──────────────┘                        │                      │
│                                                                  │                      │
│   SERVING (On-Demand Generation)                                │                      │
│   ──────────────────────────────                                │                      │
│                                                                  │                      │
│   ┌──────────────┐      ┌──────────────────────────────────┐    │                      │
│   │    HTTP      │      │         Edge Cache               │    │                      │
│   │   Worker     │─────▶│  (built-in, per-PoP)            │    │                      │
│   │              │      │                                  │    │                      │
│   │  Generates:  │      │  Cache-Control: max-age=3600     │    │                      │
│   │  - HTML      │      │  = 1 hour cache at each PoP      │    │                      │
│   │  - RSS/Atom  │      │                                  │    │                      │
│   │  - OPML      │      │  No KV needed! Edge cache is     │    │                      │
│   │  (on demand) │      │  sufficient for this traffic.    │    │                      │
│   │              │      └──────────────────────────────────┘    │                      │
│   │  /          │                      │                        │                      │
│   │  /feed.*    │      ┌───────────────┴────────────────────┐   │                      │
│   │  /search    │◄────▶│           Vectorize               │◄──┘                      │
│   │  /admin/*   │      │  (semantic search embeddings)      │                          │
│   │  /feeds.opml│      └───────────────┬────────────────────┘                          │
│   └──────────────┘                     │                                               │
│          ▲              ┌──────────────┴────────────────────┐                          │
│          │              │           Workers AI               │                          │
│          │              │  @cf/baai/bge-base-en-v1.5        │                          │
│          │              │  (768-dim text embeddings)        │                          │
│          │              └───────────────────────────────────┘                          │
│          │                                                                              │
│       Internet                                                                          │
│    (Public Users,                                                                       │
│     Admin OAuth)                                                                        │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Design Principles

Inspired by [rogue_planet](https://github.com/adewale/rogue_planet):

- **Security First**: XSS prevention, HTML sanitization, SSRF protection
- **Good Netizen Behavior**: Conditional requests (ETag/Last-Modified), rate limiting, respect for Retry-After
- **Static Output**: Generate fast-loading HTML that can be cached at the edge
- **Reliability**: Handle feed failures gracefully without blocking other feeds

### 1.3 Key Requirements

| Requirement | Value |
|-------------|-------|
| Domain | https://planetcf.com |
| Update frequency | Hourly |
| Retention policy | Last 30 days OR last 100 posts (whichever is smaller) |
| Content storage | Full post content |
| Output format | Single aggregated HTML page + RSS/Atom feed + OPML |
| Feed count | Dozens (50-100+) |
| Templating | Jinja2 |
| Feed parsing | Python `feedparser` |
| Admin interface | GitHub OAuth |
| Search | Semantic search via Vectorize + Workers AI |

---

## 2. Component Overview

See the architecture diagram in Section 1.1 for the visual overview.

| Component | Purpose | Cloudflare Service |
|-----------|---------|-------------------|
| Scheduler Worker | Triggered hourly, enqueues feed fetch jobs | Cron Trigger + Worker |
| Feed Queue | Holds pending feed fetch jobs (one message per feed) | Queues |
| Feed Fetcher Worker | Consumes queue, fetches, parses, embeds | Worker (Queue Consumer) |
| Dead Letter Queue | Captures feeds that fail 3+ times | Queues |
| HTTP Worker | Serves HTML, RSS, OPML, search, admin (generates on-demand) | Worker |
| D1 Database | Stores feeds, entries, admins, audit log | D1 |
| Edge Cache | Caches generated HTML/RSS/Atom/OPML responses | Built-in |
| Vectorize | Semantic search index (768-dim embeddings) | Vectorize |
| Workers AI | Text embeddings for semantic search | Workers AI |

**Why Workers AI?** Vectorize stores vectors but doesn't generate them. Workers AI's `@cf/baai/bge-base-en-v1.5` model converts entry text into 768-dimensional embeddings that capture semantic meaning. This enables searching by concept (e.g., "performance optimization") rather than just keyword matching.

### 2.1 Storage Architecture: D1 + Edge Cache Only

This design uses the minimum infrastructure: **D1 for storage, edge cache for performance**.

| Data | Storage | Why |
|------|---------|-----|
| feeds, entries, admins, audit_log | **D1** | Relational data requiring SQL |
| HTML, RSS, Atom, OPML | **On-demand + Edge Cache** | Generated when requested, cached at edge |
| Admin sessions | **Signed cookies** | Stateless, no storage needed |

**No KV. No R2. Just D1 and Cloudflare's built-in edge cache.**

**Why not pre-generate with KV?**

You might think the HTML page (300-500ms to generate) should be pre-cached. But consider:

| Metric | Value |
|--------|-------|
| Cache TTL | 1 hour |
| Active PoPs | ~10-20 for a niche site |
| Cache misses | ~10-20 per hour globally |
| Miss latency | 300-500ms |

For a planet aggregator, 10-20 users/hour paying 300-500ms is acceptable. The complexity savings from eliminating KV, the generator cron, and pre-generation logic outweigh the latency cost.

**The idiomatic pattern:**
```
User request
     ↓
Edge cache (per-PoP)
     ├─ HIT: 0ms (most requests)
     └─ MISS: Worker generates from D1 (300-500ms, rare)
            ↓
       Response + Cache-Control: max-age=3600
            ↓
       Edge caches for 1 hour
```

**What about the generator cron?**

With on-demand generation, the generator cron (`15 * * * *`) is eliminated. The scheduler cron (`0 * * * *`) still runs to enqueue feed fetches. Content is generated fresh when users request it.

---

## 3. Worker Time Limits

### 3.1 Understanding CPU Time vs Wall Time

Cloudflare Workers have two distinct time limits that are often confused:

| Limit Type | Definition |
|------------|------------|
| **Wall Time** | Total elapsed time from start to end of invocation (clock on the wall) |
| **CPU Time** | Time the CPU is actively executing code (excludes I/O wait) |

**Critical insight**: Network I/O (fetching feeds) counts as wall time but NOT CPU time. A feed that takes 10 seconds to respond consumes ~10 seconds of wall time but only milliseconds of CPU time.

### 3.2 Time Limits by Worker Type

| Worker Type | Wall Time Limit | CPU Time Limit | Configurable? |
|-------------|-----------------|----------------|---------------|
| **HTTP Request** | Unlimited* | 30s (default), up to 5 min | Yes (`cpu_ms`) |
| **Cron Trigger (≥1hr)** | 15 minutes | 30s (default), up to 5 min | Yes (`cpu_ms`) |
| **Cron Trigger (<1hr)** | 30 seconds | 30s (default), up to 5 min | Yes (`cpu_ms`) |
| **Queue Consumer** | 15 minutes | 30s (default), up to 5 min | Yes (`cpu_ms`) |
| **Durable Object Alarm** | 15 minutes | 30s (default), up to 5 min | Yes (`cpu_ms`) |
| **Workflows (per step)** | 5 min (default) | Configurable | Yes |

*HTTP requests run until the client disconnects, plus 30 seconds via `waitUntil()`.

### 3.3 The Problem

With dozens of feeds to fetch hourly:
- Sequential fetching in a single Worker risks hitting the 15-minute wall time limit
- A single slow or unresponsive feed could block all others
- Network errors or timeouts in one feed shouldn't affect others
- We need retry logic for transient failures

### 3.4 Solution: Queue-Based Fan-Out Pattern

Each feed is enqueued as a **separate message**. This provides complete isolation — one feed per message, one message per fetch attempt.

```
┌─────────────────┐
│  Cron Trigger   │
│  (hourly)       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────────────────────────────────┐
│  Scheduler      │     │              Feed Queue                     │
│  Worker         │────▶│                                             │
│                 │     │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐   │
│  Enqueues each  │     │  │ F1  │ │ F2  │ │ F3  │ │ F4  │ │... │   │
│  feed as a      │     │  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘   │
│  separate msg   │     │  (each feed = one message)                  │
└─────────────────┘     └──────────────────┬──────────────────────────┘
                                           │
                        ┌──────────────────┼──────────────────┐
                        │                  │                  │
                        ▼                  ▼                  ▼
              ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
              │  Consumer 1  │   │  Consumer 2  │   │  Consumer N  │
              │  (batch of   │   │  (batch of   │   │  (batch of   │
              │   feeds)     │   │   feeds)     │   │   feeds)     │
              └──────────────┘   └──────────────┘   └──────────────┘
                        │                  │                  │
                        └──────────────────┼──────────────────┘
                                           │
                                           ▼
                               ┌───────────────────────┐
                               │   D1 Database         │
                               │   (entries, feeds)    │
                               └───────────────────────┘
```

**Why one feed per message:**
1. **Complete isolation**: A feed that times out only affects that one message
2. **Granular retries**: Only the failed feed is retried, not the entire batch
3. **Accurate dead-lettering**: DLQ contains exactly the feeds that persistently fail
4. **Automatic parallelism**: Queues can spin up multiple consumers concurrently
5. **Fair scheduling**: No feed can starve others by being slow

### 3.5 Time Budget Analysis

For the **Scheduler Worker** (Cron Trigger):
- Wall time limit: 15 minutes
- Task: Query D1 for active feeds, enqueue each as separate message
- Expected duration: < 5 seconds for 100 feeds
- CPU time: Minimal (just D1 query + queue sends)

For the **Feed Fetcher Worker** (Queue Consumer):
- Wall time limit: 15 minutes
- Task: Fetch feed via HTTP, parse with feedparser, write to D1
- Per-feed breakdown:
  - HTTP fetch: 1-30 seconds wall time, ~0 CPU time (I/O wait)
  - feedparser parsing: ~100ms CPU time
  - D1 writes: ~50ms CPU time per entry
- With `max_batch_size = 5`: Even worst-case (5 × 30s feeds) = 2.5 min wall time

### 3.6 Queue Configuration

```jsonc
// wrangler.jsonc (excerpt)
{
  "limits": {
    "cpu_ms": 60000  // 60 seconds CPU time (generous buffer)
  },

  "queues": {
    "producers": [
      { "binding": "FEED_QUEUE", "queue": "planetcf-feed-queue" },
      { "binding": "DEAD_LETTER_QUEUE", "queue": "planetcf-feed-dlq" }
    ],
    "consumers": [
      {
        "queue": "planetcf-feed-queue",
        "max_batch_size": 5,        // Process up to 5 feeds per invocation
        "max_batch_timeout": 30,    // Wait up to 30s to fill batch
        "max_retries": 3,           // Retry failed feeds 3 times
        "dead_letter_queue": "planetcf-feed-dlq",
        "retry_delay": 300          // Wait 5 minutes before retry
      }
    ]
  }
}
```

**Configuration rationale:**
- `max_batch_size = 5`: Conservative batch size ensures we stay well under 15-min wall time even with slow feeds
- `max_retries = 3`: Transient failures get 3 chances before going to DLQ
- `retry_delay = 300`: 5-minute delay between retries allows transient issues to resolve
- `cpu_ms = 60000`: 60 seconds of CPU time handles parsing many entries

### 3.7 Consumer Timeout Strategy

Even with small batches, implement a per-feed timeout to prevent one feed from consuming the entire wall time budget:

```python
import asyncio

FEED_TIMEOUT_SECONDS = 60  # Max 60 seconds per feed (wall time)

# Inside the queue handler method (see Section 5.2 for full implementation)
async def process_feed_batch(self, batch):
    """Process a batch of feed messages from the queue."""

    for message in batch.messages:
        feed_job = message.body

        try:
            # Wrap fetch in timeout - if one feed is slow, fail it individually
            await asyncio.wait_for(
                self._fetch_and_process_feed(feed_job),
                timeout=FEED_TIMEOUT_SECONDS
            )
            message.ack()

        except asyncio.TimeoutError:
            print(f"Feed {feed_job['url']} timed out after {FEED_TIMEOUT_SECONDS}s")
            message.retry()  # Will be retried, eventually DLQ'd

        except Exception as e:
            print(f"Error processing feed {feed_job['url']}: {e}")
            message.retry()
```

### 3.8 Failure Scenarios

| Scenario | Behavior |
|----------|----------|
| Feed server returns 5xx | Message retried after `retry_delay` |
| Feed server timeout | Message retried (asyncio timeout) |
| Feed parsing error | Message retried (may eventually DLQ if feed is malformed) |
| D1 write failure | Message retried |
| 3 consecutive failures | Message moved to Dead Letter Queue |
| Queue consumer crashes | Unacked messages automatically redelivered |

### 3.9 Monitoring Time Usage

Add observability to track actual time consumption:

```python
import time

async def fetch_and_process_feed(job, env):
    start = time.time()
    
    try:
        # ... fetch and process ...
        
    finally:
        elapsed = time.time() - start
        print(f"Feed {job['url']} processed in {elapsed:.2f}s wall time")
        
        # Track in analytics (optional)
        await env.ANALYTICS.writeDataPoint({
            "index": "feed_processing",
            "blobs": [job["url"]],
            "doubles": [elapsed]
        })
```

---

## 4. Data Model

### 4.1 D1 Schema

```sql
-- Feeds table
CREATE TABLE feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    title TEXT,
    site_url TEXT,
    author_name TEXT,
    author_email TEXT,
    
    -- HTTP caching
    etag TEXT,
    last_modified TEXT,
    
    -- Health tracking
    last_fetch_at TEXT,
    last_success_at TEXT,
    fetch_error TEXT,
    fetch_error_count INTEGER DEFAULT 0,
    consecutive_failures INTEGER DEFAULT 0,
    
    -- Status
    is_active INTEGER DEFAULT 1,
    
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_feeds_active ON feeds(is_active);
CREATE INDEX idx_feeds_url ON feeds(url);

-- Entries table  
CREATE TABLE entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_id INTEGER NOT NULL,
    guid TEXT NOT NULL,
    url TEXT,
    title TEXT,
    author TEXT,
    content TEXT,           -- Full sanitized HTML content
    summary TEXT,           -- Short summary/excerpt
    published_at TEXT,
    updated_at TEXT,
    
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (feed_id) REFERENCES feeds(id) ON DELETE CASCADE,
    UNIQUE(feed_id, guid)
);

CREATE INDEX idx_entries_published ON entries(published_at DESC);
CREATE INDEX idx_entries_feed ON entries(feed_id);
CREATE INDEX idx_entries_guid ON entries(feed_id, guid);

-- Admin users table
CREATE TABLE admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    github_username TEXT UNIQUE NOT NULL,
    github_id INTEGER,  -- Populated on first login
    display_name TEXT,
    avatar_url TEXT,
    
    is_active INTEGER DEFAULT 1,
    
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_login_at TEXT
);

CREATE INDEX idx_admins_github ON admins(github_username);

-- Note: Admins are seeded from config/admins.json (see Section 9.3)

-- Audit log for admin actions
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER,
    action TEXT NOT NULL,       -- 'add_feed', 'remove_feed', 'update_feed', etc.
    target_type TEXT,           -- 'feed', 'admin', etc.
    target_id INTEGER,
    details TEXT,               -- JSON blob with action details
    
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (admin_id) REFERENCES admins(id)
);

CREATE INDEX idx_audit_created ON audit_log(created_at DESC);
```

### 4.2 Retention Policy Implementation

```sql
-- Delete entries older than 30 days, keeping at most 100 per feed
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
entries_to_keep AS (
    SELECT id FROM ranked_entries
    WHERE rn <= 100
    AND published_at >= datetime('now', '-30 days')
)
DELETE FROM entries
WHERE id NOT IN (SELECT id FROM entries_to_keep);
```

---

## 5. Workers Specification

### 5.1 Scheduler Worker (Cron Trigger)

**Trigger:** `0 * * * *` (hourly, at minute 0)

**Responsibilities:**
1. Query D1 for all active feeds
2. Enqueue **each feed as a separate message** (critical for isolation)
3. Log enqueue statistics

**Design principle:** One feed = one message. This ensures complete isolation between feeds for retries, timeouts, and dead-lettering.

```python
# src/main.py
from workers import WorkerEntrypoint
from datetime import datetime


class PlanetCF(WorkerEntrypoint):
    """
    Main Worker entrypoint handling all triggers:
    - scheduled(): Hourly cron to enqueue feed fetches
    - queue(): Queue consumer for feed fetching
    - fetch(): HTTP request handling (generates content on-demand)
    """

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
                "etag": feed["etag"],
                "last_modified": feed["last_modified"],
                "scheduled_at": datetime.utcnow().isoformat()
            }

            await self.env.FEED_QUEUE.send(message)
            enqueue_count += 1

        print(f"Scheduler: Enqueued {enqueue_count} feeds as separate messages")

        return {"enqueued": enqueue_count}
```

**Why not use `sendBatch()`?**

While `sendBatch()` is more efficient for sending many messages, we explicitly send each feed individually to emphasize the one-feed-per-message design. For 100 feeds, the overhead is negligible (< 1 second total).

If performance becomes critical at scale (500+ feeds), you can batch the sends while keeping one feed per message:

```python
# Optional: Batch the send operation (not the message content)
# Inside the _run_scheduler method
messages = [
    {
        "body": {
            "feed_id": feed["id"],
            "url": feed["url"],
            "etag": feed["etag"],
            "last_modified": feed["last_modified"],
            "scheduled_at": datetime.utcnow().isoformat()
        }
    }
    for feed in feeds
]

# Send in chunks of 100 (API limit)
for i in range(0, len(messages), 100):
    chunk = messages[i:i+100]
    await self.env.FEED_QUEUE.sendBatch(chunk)
```

### 5.2 Feed Fetcher Worker (Queue Consumer)

**Trigger:** Queue consumer for `planetcf-feed-queue`

**Responsibilities:**
1. Receive batch of feed messages (each message = one feed)
2. Fetch each feed with per-feed timeout and conditional HTTP headers
3. Parse with `feedparser`
4. Sanitize HTML content (XSS prevention)
5. Upsert entries to D1
6. Generate embeddings and index in Vectorize
7. Update feed metadata (etag, last_modified, error state)
8. Ack successful messages, retry failed ones

```python
# src/main.py (continued from Section 5.1)
import asyncio
import time
import ipaddress
import feedparser
import httpx
from bleach import clean
from datetime import datetime
from urllib.parse import urlparse

# Configuration
FEED_TIMEOUT_SECONDS = 60      # Max wall time per feed
HTTP_TIMEOUT_SECONDS = 30      # HTTP request timeout
USER_AGENT = "PlanetCF/1.0 (+https://planetcf.com)"

# HTML sanitization settings (XSS prevention - CVE-2009-2937)
ALLOWED_TAGS = [
    'a', 'abbr', 'acronym', 'b', 'blockquote', 'code', 'em',
    'i', 'li', 'ol', 'strong', 'ul', 'p', 'br', 'pre',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'img', 'figure',
    'figcaption', 'table', 'thead', 'tbody', 'tr', 'th', 'td'
]

ALLOWED_ATTRIBUTES = {
    'a': ['href', 'title', 'rel'],
    'img': ['src', 'alt', 'title', 'width', 'height'],
    'abbr': ['title'],
    'acronym': ['title'],
}

# Cloud metadata endpoints to block (SSRF protection)
BLOCKED_METADATA_IPS = {
    '169.254.169.254',  # AWS/GCP/Azure metadata
    '100.100.100.200',  # Alibaba Cloud metadata
    '192.0.0.192',      # Oracle Cloud metadata
}


class PlanetCF(WorkerEntrypoint):
    # ... (scheduled method from Section 5.1)

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
            start_time = time.time()

            try:
                # Wrap entire feed processing in a timeout
                # This is WALL TIME, not CPU time - network I/O counts here
                await asyncio.wait_for(
                    self._process_single_feed(feed_job),
                    timeout=FEED_TIMEOUT_SECONDS
                )

                elapsed = time.time() - start_time
                print(f"Feed OK: {feed_url} ({elapsed:.2f}s)")
                message.ack()

            except asyncio.TimeoutError:
                elapsed = time.time() - start_time
                print(f"Feed TIMEOUT: {feed_url} after {elapsed:.2f}s")
                await self._record_feed_error(feed_job["feed_id"], "Timeout")
                message.retry()

            except Exception as e:
                elapsed = time.time() - start_time
                print(f"Feed ERROR: {feed_url} ({elapsed:.2f}s): {e}")
                await self._record_feed_error(feed_job["feed_id"], str(e))
                message.retry()

    async def _process_single_feed(self, job):
        """
        Fetch, parse, and store a single feed.

        This function should complete within FEED_TIMEOUT_SECONDS.
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

        # Fetch with timeout
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            response = await client.get(url, headers=headers, follow_redirects=True)

        # Re-validate final URL after redirects (SSRF protection)
        final_url = str(response.url)
        if final_url != url and not self._is_safe_url(final_url):
            raise ValueError(f"Redirect target failed SSRF validation: {final_url}")

        # Handle 304 Not Modified - feed hasn't changed
        if response.status_code == 304:
            await self._update_feed_success(feed_id, etag, last_modified)
            return

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
        for entry in feed_data.entries:
            entry_id = await self._upsert_entry(feed_id, entry)
            if entry_id:
                entries_added += 1

        # Mark fetch as successful
        await self._update_feed_success(feed_id, new_etag, new_last_modified)

        print(f"Feed processed: {url}, {entries_added} new/updated entries")

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
        result = await self.env.DB.prepare("""
            INSERT INTO entries (feed_id, guid, url, title, author, content, summary, published_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(feed_id, guid) DO UPDATE SET
                title = excluded.title,
                content = excluded.content,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
        """).bind(
            feed_id,
            guid,
            entry.get("link"),
            title,
            entry.get("author"),
            sanitized_content,
            (entry.get("summary") or "")[:500],  # Truncate summary
            published_at
        ).first()

        entry_id = result["id"] if result else None

        # Index for semantic search (see Section 12.2)
        if entry_id and title:
            await self._index_entry_for_search(entry_id, title, sanitized_content)

        return entry_id

    async def _index_entry_for_search(self, entry_id, title, content):
        """Generate embedding and store in Vectorize for semantic search."""

        # Combine title and content for embedding (truncate to model limit)
        text = f"{title}\n\n{content[:2000]}"

        # Generate embedding using Workers AI with cls pooling for accuracy
        embedding_result = await self.env.AI.run(
            "@cf/baai/bge-base-en-v1.5",
            {"text": [text], "pooling": "cls"}
        )

        vector = embedding_result["data"][0]

        # Upsert to Vectorize with entry_id as the vector ID
        await self.env.SEARCH_INDEX.upsert([
            {
                "id": str(entry_id),
                "values": vector,
                "metadata": {
                    "title": title[:200],
                    "entry_id": entry_id
                }
            }
        ])

    def _sanitize_html(self, html_content):
        """Sanitize HTML to prevent XSS attacks (CVE-2009-2937 mitigation)."""
        return clean(
            html_content,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            protocols=['http', 'https', 'mailto'],
            strip=True
        )

    def _is_safe_url(self, url):
        """SSRF protection - reject internal/private URLs."""

        parsed = urlparse(url)

        # Only allow http/https
        if parsed.scheme not in ('http', 'https'):
            return False

        hostname = parsed.hostname.lower() if parsed.hostname else ""

        # Block localhost variants
        if hostname in ('localhost', '127.0.0.1', '::1', '0.0.0.0'):
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
            if ip.version == 6 and ip.packed[0] == 0xfd:
                return False
        except ValueError:
            pass  # Not an IP address

        # Block internal domain patterns
        if hostname.endswith('.internal') or hostname.endswith('.local'):
            return False

        return True

    async def _update_feed_success(self, feed_id, etag, last_modified):
        """Mark feed fetch as successful."""
        await self.env.DB.prepare("""
            UPDATE feeds SET
                last_fetch_at = CURRENT_TIMESTAMP,
                last_success_at = CURRENT_TIMESTAMP,
                etag = ?,
                last_modified = ?,
                fetch_error = NULL,
                consecutive_failures = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """).bind(etag, last_modified, feed_id).run()

    async def _record_feed_error(self, feed_id, error_message):
        """Record a feed fetch error."""
        await self.env.DB.prepare("""
            UPDATE feeds SET
                last_fetch_at = CURRENT_TIMESTAMP,
                fetch_error = ?,
                fetch_error_count = fetch_error_count + 1,
                consecutive_failures = consecutive_failures + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """).bind(error_message[:500], feed_id).run()

    async def _update_feed_url(self, feed_id, new_url):
        """Update feed URL after permanent redirect."""
        await self.env.DB.prepare("""
            UPDATE feeds SET
                url = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """).bind(new_url, feed_id).run()

    async def _update_feed_metadata(self, feed_id, feed_info, etag, last_modified):
        """Update feed title and other metadata from feed content."""
        title = feed_info.get("title")
        site_url = feed_info.get("link")

        await self.env.DB.prepare("""
            UPDATE feeds SET
                title = COALESCE(?, title),
                site_url = COALESCE(?, site_url),
                etag = ?,
                last_modified = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """).bind(title, site_url, etag, last_modified, feed_id).run()
```

### 5.3 HTML Generation (On-Demand)

**Trigger:** HTTP request to `/` (no separate cron — generated when requested)

**Why on-demand instead of pre-generation?**
- Eliminates KV storage, generator cron, pre-generation complexity
- Edge cache handles repeat requests (1-hour TTL)
- ~10-20 cache misses/hour globally is acceptable latency cost
- Content is never more stale than with hourly pre-generation

**Responsibilities:**
1. Query entries from D1 (with retention filtering)
2. Render HTML using Jinja2
3. Return with `Cache-Control: max-age=3600` for edge caching

#### Webpage Layout (Planet-style)

```
┌─────────────────────────────────────────────────────────────────────┐
│                              HEADER                                  │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Planet CF                                                     │  │
│  │  Aggregated posts from Cloudflare employees and community      │  │
│  │  ┌────────────────────────────────────────────────────────┐   │  │
│  │  │ 🔍 Search entries...                        [Search]   │   │  │
│  │  └────────────────────────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌───────────────────────────────────────┐  ┌────────────────────┐  │
│  │              MAIN CONTENT             │  │      SIDEBAR       │  │
│  │                                       │  │                    │  │
│  │  ═══════ January 10, 2026 ═══════    │  │   Subscriptions    │  │
│  │                                       │  │   ─────────────    │  │
│  │  ┌─────────────────────────────────┐ │  │                    │  │
│  │  │ How We Scaled Workers AI        │ │  │   • Cloudflare     │  │
│  │  │ ─────────────────────────────── │ │  │     Blog           │  │
│  │  │ Rita Kozlov · 3:42 PM           │ │  │     (2 hours ago)  │  │
│  │  │                                 │ │  │                    │  │
│  │  │ Today we're announcing...       │ │  │   • Julia Evans    │  │
│  │  │ [full post content here]        │ │  │     (1 day ago)    │  │
│  │  │                                 │ │  │                    │  │
│  │  └─────────────────────────────────┘ │  │   • Rachel by      │  │
│  │                                       │  │     the Bay        │  │
│  │  ┌─────────────────────────────────┐ │  │     (3 days ago)   │  │
│  │  │ Debugging Python in Production  │ │  │                    │  │
│  │  │ ─────────────────────────────── │ │  │   ⚠ Broken Feed   │  │
│  │  │ Celso Martinho · 11:15 AM       │ │  │     (failing)      │  │
│  │  │                                 │ │  │                    │  │
│  │  │ When debugging Workers...       │ │  │                    │  │
│  │  │ [full post content here]        │ │  │                    │  │
│  │  │                                 │ │  │                    │  │
│  │  └─────────────────────────────────┘ │  │                    │  │
│  │                                       │  │                    │  │
│  │  ═══════ January 9, 2026 ════════    │  │                    │  │
│  │                                       │  │                    │  │
│  │  ┌─────────────────────────────────┐ │  │                    │  │
│  │  │ Things I Learned This Week      │ │  │                    │  │
│  │  │ ─────────────────────────────── │ │  │                    │  │
│  │  │ Julia Evans · 9:00 AM           │ │  │                    │  │
│  │  │ ...                             │ │  │                    │  │
│  │  └─────────────────────────────────┘ │  │                    │  │
│  │                                       │  │                    │  │
│  └───────────────────────────────────────┘  └────────────────────┘  │
│                                                                      │
├─────────────────────────────────────────────────────────────────────┤
│                              FOOTER                                  │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │           Atom · RSS · OPML                                    │  │
│  │           Powered by Planet CF                                 │  │
│  │           Last updated: 2026-01-10 16:00 UTC                   │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘

Layout Notes:
- Two-column layout: main content (70%) + sidebar (30%)
- Main content: entries grouped by date, newest first
- Each entry shows: title (linked), author, time, full content
- Sidebar: list of subscribed feeds with health status
- Footer: feed links (Atom, RSS, OPML) and last update time
- Search bar in header (semantic search via Vectorize)
- Responsive: collapses to single column on mobile
```

```python
# src/main.py (continued - _generate_html method)
from jinja2 import Environment, BaseLoader
from datetime import datetime, timedelta

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ planet.name }}</title>
    <link rel="stylesheet" href="/static/style.css">
    <link rel="alternate" type="application/atom+xml" title="{{ planet.name }} Atom Feed" href="/feed.atom">
    <link rel="alternate" type="application/rss+xml" title="{{ planet.name }} RSS Feed" href="/feed.rss">
    <meta http-equiv="Content-Security-Policy" content="default-src 'self'; img-src 'self' https:; style-src 'self' 'unsafe-inline';">
</head>
<body>
    <header>
        <h1>{{ planet.name }}</h1>
        <p>{{ planet.description }}</p>
        <form action="/search" method="GET" class="search-form">
            <input type="search" name="q" placeholder="Search entries..." 
                   aria-label="Search entries">
            <button type="submit">Search</button>
        </form>
    </header>
    
    <div class="container">
        <main>
            {% for date, day_entries in entries_by_date.items() %}
            <section class="day">
                <h2 class="date">{{ date }}</h2>
                {% for entry in day_entries %}
                <article>
                    <header>
                        <h3><a href="{{ entry.url }}">{{ entry.title }}</a></h3>
                        <p class="meta">
                            <span class="author">{{ entry.author or entry.feed_title }}</span>
                            <time datetime="{{ entry.published_at }}">{{ entry.published_at_formatted }}</time>
                        </p>
                    </header>
                    <div class="content">
                        {{ entry.content | safe }}
                    </div>
                </article>
                {% endfor %}
            </section>
            {% endfor %}
        </main>
        
        <aside class="sidebar">
            <h2>Subscriptions</h2>
            <ul class="feeds">
                {% for feed in feeds %}
                <li class="{{ 'healthy' if feed.is_healthy else 'unhealthy' }}">
                    <a href="{{ feed.site_url }}">{{ feed.title }}</a>
                    <span class="last-updated">{{ feed.last_success_at_relative }}</span>
                </li>
                {% endfor %}
            </ul>
        </aside>
    </div>
    
    <footer>
        <p>
            <a href="/feed.atom">Atom</a> · 
            <a href="/feed.rss">RSS</a> · 
            <a href="/feeds.opml">OPML</a>
        </p>
        <p>Powered by <a href="https://github.com/cloudflare/planetcf">Planet CF</a></p>
        <p>Last updated: {{ generated_at }}</p>
    </footer>
</body>
</html>
"""


class PlanetCF(WorkerEntrypoint):
    # ... (other methods from Sections 5.1 and 5.2)

    async def _generate_html(self):
        """
        Generate the aggregated HTML page on-demand.
        Called by fetch() for / requests. Edge cache handles caching.
        """

        # Get planet config from environment
        planet = {
            "name": self.env.PLANET_NAME or "Planet CF",
            "description": self.env.PLANET_DESCRIPTION or "Aggregated posts from Cloudflare employees and community",
            "link": self.env.PLANET_URL or "https://planetcf.com"
        }

        # Apply retention policy first (delete old entries and their vectors)
        await self._apply_retention_policy()

        # Query entries (last 30 days, max 100 per feed)
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

        entries = entries_result.results

        # Group entries by date
        entries_by_date = {}
        for entry in entries:
            date_str = entry["published_at"][:10]  # YYYY-MM-DD
            if date_str not in entries_by_date:
                entries_by_date[date_str] = []

            entry["published_at_formatted"] = self._format_datetime(entry["published_at"])
            entries_by_date[date_str].append(entry)

        # Get feeds for sidebar
        feeds_result = await self.env.DB.prepare("""
            SELECT
                id, title, site_url, last_success_at,
                CASE WHEN consecutive_failures < 3 THEN 1 ELSE 0 END as is_healthy
            FROM feeds
            WHERE is_active = 1
            ORDER BY title
        """).all()

        feeds = feeds_result.results
        for feed in feeds:
            feed["last_success_at_relative"] = self._relative_time(feed["last_success_at"])

        # Render template
        jinja_env = Environment(loader=BaseLoader())
        template = jinja_env.from_string(HTML_TEMPLATE)

        html = template.render(
            planet=planet,
            entries_by_date=entries_by_date,
            feeds=feeds,
            generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        )

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
                batch = deleted_ids[i:i+50]
                placeholders = ",".join("?" * len(batch))
                await self.env.DB.prepare(f"""
                    DELETE FROM entries WHERE id IN ({placeholders})
                """).bind(*batch).run()

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

    def _generate_atom_feed(self, planet, entries):
        """Generate Atom 1.0 feed XML."""
        from xml.sax.saxutils import escape

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
        feed_xml += '</feed>'
        return feed_xml

    def _generate_rss_feed(self, planet, entries):
        """Generate RSS 2.0 feed XML."""
        from xml.sax.saxutils import escape

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
            feed_xml += f'''    <item>
      <title>{escape(entry.get("title", ""))}</title>
      <link>{escape(entry.get("url", ""))}</link>
      <guid>{escape(entry.get("guid", entry.get("url", "")))}</guid>
      <pubDate>{entry.get("published_at", "")}</pubDate>
      <author>{escape(entry.get("author", ""))}</author>
      <description><![CDATA[{entry.get("content", "")}]]></description>
    </item>
'''
        feed_xml += '''  </channel>
</rss>'''
        return feed_xml
```

### 5.4 HTTP Worker

**Trigger:** HTTP requests to the domain

**Responsibilities:**
1. Generate and serve HTML on-demand (edge cached)
2. Generate and serve RSS/Atom feeds on-demand (edge cached)
3. Handle semantic search queries
4. Serve admin interface (protected by GitHub OAuth)
5. Handle admin API endpoints

```python
# src/main.py (continued - fetch method and HTTP helpers)
from workers import Response
from urllib.parse import parse_qs
import hashlib
import secrets
import json
import time

# Session configuration
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days


class PlanetCF(WorkerEntrypoint):
    # ... (other methods from Sections 5.1, 5.2, 5.3)

    async def fetch(self, request):
        """Handle HTTP requests."""

        url = request.url
        path = url.pathname if hasattr(url, 'pathname') else url.split('?')[0].split('://', 1)[-1].split('/', 1)[-1]
        if not path.startswith('/'):
            path = '/' + path

        # Public routes
        if path == "/" or path == "/index.html":
            return await self._serve_html()

        if path == "/feed.atom":
            return await self._serve_atom()

        if path == "/feed.rss":
            return await self._serve_rss()

        if path == "/feeds.opml":
            return await self._export_opml()

        if path == "/search":
            return await self._search_entries(request)

        # OAuth callback
        if path == "/auth/github/callback":
            return await self._handle_github_callback(request)

        # Admin routes (require authentication)
        if path.startswith("/admin"):
            return await self._handle_admin(request, path)

        return Response("Not Found", status=404)

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

        return Response(html, headers={
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "public, max-age=3600, stale-while-revalidate=60",
        })

    async def _serve_atom(self):
        """Generate and serve Atom feed on-demand."""

        entries = await self._get_recent_entries(50)
        planet = self._get_planet_config()
        atom = self._generate_atom_feed(planet, entries)

        return Response(atom, headers={
            "Content-Type": "application/atom+xml; charset=utf-8",
            "Cache-Control": "public, max-age=3600, stale-while-revalidate=60",
        })

    async def _serve_rss(self):
        """Generate and serve RSS feed on-demand."""

        entries = await self._get_recent_entries(50)
        planet = self._get_planet_config()
        rss = self._generate_rss_feed(planet, entries)

        return Response(rss, headers={
            "Content-Type": "application/rss+xml; charset=utf-8",
            "Cache-Control": "public, max-age=3600, stale-while-revalidate=60",
        })

    async def _get_recent_entries(self, limit):
        """Query recent entries for feeds."""

        result = await self.env.DB.prepare("""
            SELECT e.*, f.title as feed_title, f.site_url as feed_site_url
            FROM entries e
            JOIN feeds f ON e.feed_id = f.id
            WHERE f.is_active = 1
            ORDER BY e.published_at DESC
            LIMIT ?
        """).bind(limit).all()

        return result.results

    def _get_planet_config(self):
        """Get planet configuration from environment."""
        return {
            "name": getattr(self.env, 'PLANET_NAME', None) or "Planet CF",
            "description": getattr(self.env, 'PLANET_DESCRIPTION', None) or "Aggregated posts",
            "link": getattr(self.env, 'PLANET_URL', None) or "https://planetcf.com"
        }

    async def _search_entries(self, request):
        """Search entries by semantic similarity."""

        # Parse query string
        url_str = str(request.url)
        query = ""
        if "?" in url_str:
            qs = parse_qs(url_str.split("?", 1)[1])
            query = qs.get("q", [""])[0]

        if not query or len(query) < 2:
            return Response(
                json.dumps({"error": "Query too short"}),
                status=400,
                headers={"Content-Type": "application/json"}
            )

        # Generate embedding for search query
        embedding_result = await self.env.AI.run(
            "@cf/baai/bge-base-en-v1.5",
            {"text": [query], "pooling": "cls"}
        )
        query_vector = embedding_result["data"][0]

        # Search Vectorize
        results = await self.env.SEARCH_INDEX.query(query_vector, {
            "topK": 20,
            "returnMetadata": True
        })

        # Fetch full entries from D1
        if not results.matches:
            return Response(
                json.dumps({"results": []}),
                headers={"Content-Type": "application/json"}
            )

        entry_ids = [int(m.id) for m in results.matches]
        placeholders = ",".join("?" * len(entry_ids))

        entries = await self.env.DB.prepare(f"""
            SELECT e.*, f.title as feed_title, f.site_url as feed_site_url
            FROM entries e
            JOIN feeds f ON e.feed_id = f.id
            WHERE e.id IN ({placeholders})
        """).bind(*entry_ids).all()

        # Sort by Vectorize score
        entry_map = {e["id"]: e for e in entries.results}
        sorted_results = [
            {**entry_map[int(m.id)], "score": m.score}
            for m in results.matches
            if int(m.id) in entry_map
        ]

        return Response(
            json.dumps({"results": sorted_results}),
            headers={
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",  # CORS for API
            }
        )

    async def _handle_admin(self, request, path):
        """Handle admin routes with GitHub OAuth."""

        # Verify signed session cookie (stateless, no KV)
        session = self._verify_signed_cookie(request)
        if not session:
            return self._redirect_to_github_oauth()

        # Verify user is still an authorized admin (may have been revoked)
        admin = await self.env.DB.prepare(
            "SELECT * FROM admins WHERE github_username = ? AND is_active = 1"
        ).bind(session["github_username"]).first()

        if not admin:
            return Response("Unauthorized: Not an admin", status=403)

        # Route admin requests
        if path == "/admin" or path == "/admin/":
            return await self._serve_admin_dashboard(admin)

        if path == "/admin/feeds" and request.method == "GET":
            return await self._list_feeds()

        if path == "/admin/feeds" and request.method == "POST":
            return await self._add_feed(request, admin)

        if path.startswith("/admin/feeds/") and request.method == "DELETE":
            feed_id = path.split("/")[-1]
            return await self._remove_feed(feed_id, admin)

        if path.startswith("/admin/feeds/") and request.method == "PUT":
            feed_id = path.split("/")[-1]
            return await self._update_feed(request, feed_id, admin)

        if path == "/admin/import-opml" and request.method == "POST":
            return await self._import_opml(request, admin)

        if path == "/admin/regenerate" and request.method == "POST":
            return await self._trigger_regenerate(admin)

        if path == "/admin/dlq" and request.method == "GET":
            return await self._view_dlq()

        if path == "/admin/audit" and request.method == "GET":
            return await self._view_audit_log()

        if path == "/admin/logout" and request.method == "POST":
            return self._logout(request)

        return Response("Not Found", status=404)

    def _verify_signed_cookie(self, request):
        """
        Verify the signed session cookie (stateless, no KV).
        Cookie format: base64(json_payload).signature
        """
        import hmac
        import hashlib
        import base64
        import time

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
                self.env.SESSION_SECRET.encode(),
                payload_b64.encode(),
                hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(signature, expected_sig):
                return None

            # Decode payload
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))

            # Check expiration
            if payload.get("exp", 0) < time.time():
                return None

            return payload
        except Exception:
            return None

    def _redirect_to_github_oauth(self):
        """Redirect to GitHub OAuth authorization."""

        state = secrets.token_urlsafe(32)
        auth_url = (
            f"https://github.com/login/oauth/authorize"
            f"?client_id={self.env.GITHUB_CLIENT_ID}"
            f"&redirect_uri={self.env.PLANET_URL}/auth/github/callback"
            f"&scope=read:user"
            f"&state={state}"
        )

        return Response("", status=302, headers={
            "Location": auth_url,
            "Set-Cookie": f"oauth_state={state}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=600"
        })

    async def _handle_github_callback(self, request):
        """Handle GitHub OAuth callback."""

        url_str = str(request.url)
        qs = parse_qs(url_str.split("?", 1)[1]) if "?" in url_str else {}
        code = qs.get("code", [""])[0]
        state = qs.get("state", [""])[0]

        if not code:
            return Response("Missing authorization code", status=400)

        # Exchange code for access token
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": self.env.GITHUB_CLIENT_ID,
                    "client_secret": self.env.GITHUB_CLIENT_SECRET,
                    "code": code,
                },
                headers={"Accept": "application/json"}
            )

        token_data = token_response.json()
        access_token = token_data.get("access_token")

        if not access_token:
            return Response("Failed to get access token", status=400)

        # Fetch user info
        async with httpx.AsyncClient() as client:
            user_response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json"
                }
            )

        user_data = user_response.json()
        github_username = user_data.get("login")
        github_id = user_data.get("id")

        # Verify user is an admin
        admin = await self.env.DB.prepare(
            "SELECT * FROM admins WHERE github_username = ? AND is_active = 1"
        ).bind(github_username).first()

        if not admin:
            return Response("Unauthorized: Not an admin", status=403)

        # Update admin's github_id and last_login_at
        await self.env.DB.prepare("""
            UPDATE admins SET github_id = ?, last_login_at = CURRENT_TIMESTAMP
            WHERE github_username = ?
        """).bind(github_id, github_username).run()

        # Create signed session cookie (stateless, no KV)
        session_cookie = self._create_signed_cookie({
            "github_username": github_username,
            "github_id": github_id,
            "avatar_url": user_data.get("avatar_url"),
            "exp": int(time.time()) + SESSION_TTL_SECONDS,
        })

        return Response("", status=302, headers={
            "Location": "/admin",
            "Set-Cookie": f"session={session_cookie}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age={SESSION_TTL_SECONDS}"
        })

    def _create_signed_cookie(self, payload):
        """Create an HMAC-signed cookie. Format: base64(json_payload).signature"""
        import hmac
        import hashlib
        import base64

        payload_json = json.dumps(payload)
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode()

        signature = hmac.new(
            self.env.SESSION_SECRET.encode(),
            payload_b64.encode(),
            hashlib.sha256
        ).hexdigest()

        return f"{payload_b64}.{signature}"

    def _logout(self, request):
        """Log out by clearing the session cookie (stateless - nothing to delete)."""

        return Response("", status=302, headers={
            "Location": "/",
            "Set-Cookie": "session=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0"
        })
```

---

## 6. Admin Interface

### 6.1 Authentication

Use GitHub OAuth for admin authentication with **signed cookies** (stateless):

1. Admin visits `/admin`
2. Redirect to GitHub OAuth authorization
3. GitHub redirects back with authorization code
4. Exchange code for access token
5. Fetch user info from GitHub API
6. Check if `github_username` exists in `admins` table
7. Create signed cookie: `base64(json_payload).hmac_signature`

**Why signed cookies (not KV)?**

Signed cookies are simpler for this use case:
- **Stateless**: No storage reads/writes on every request
- **Edge-native**: Cookie travels with request, verified locally with HMAC
- **Self-expiring**: `exp` claim in payload, checked on every verification
- **Tamper-proof**: HMAC-SHA256 signature prevents modification

Trade-off: Sessions can't be revoked server-side. For a small admin interface where admins are trusted and can be deactivated in D1, this is acceptable.

**Session format:**
```
Cookie: session=<base64_payload>.<hmac_signature>

Payload (JSON, base64-encoded):
{
  "github_username": "...",
  "github_id": ...,
  "avatar_url": "...",
  "exp": 1234567890  // Unix timestamp, 7 days from creation
}

Signature: HMAC-SHA256(SESSION_SECRET, base64_payload)
```

### 6.2 Admin Configuration

Admins are seeded from a configuration file on first deploy. The only default admin is the project maintainer:

**admins.json** (checked into repository):
```json
{
  "admins": [
    {
      "github_username": "adewale",
      "display_name": "Adewale Oshineye"
    }
  ]
}
```

The seed migration reads this file:

```sql
-- migrations/002_seed_admins.sql
-- Generated from admins.json during deployment

INSERT INTO admins (github_username, github_id, display_name, is_active)
VALUES ('adewale', 0, 'Adewale Oshineye', 1)
ON CONFLICT(github_username) DO NOTHING;
```

**Note:** The `github_id` is populated on first login via OAuth. Additional admins can be added through the admin interface by existing admins.

### 6.3 Admin API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin` | Admin dashboard HTML |
| GET | `/admin/feeds` | List all feeds (JSON) |
| POST | `/admin/feeds` | Add new feed |
| DELETE | `/admin/feeds/:id` | Remove feed |
| PUT | `/admin/feeds/:id` | Update feed (enable/disable) |
| POST | `/admin/import-opml` | Import feeds from OPML file |
| POST | `/admin/regenerate` | Force HTML regeneration |
| GET | `/admin/dlq` | View dead letter queue |
| POST | `/admin/dlq/:id/retry` | Retry failed feed |
| GET | `/admin/audit` | View audit log |

### 6.4 Admin Dashboard Features

- **Feed Management**: Add, remove, enable/disable feeds
- **OPML Import**: Bulk import feeds from OPML files
- **Health Overview**: See feed fetch status, error counts
- **Dead Letter Queue**: View and retry persistently failing feeds
- **Manual Regeneration**: Force HTML rebuild
- **Audit Log**: Track all admin actions

---

## 7. Security

### 7.1 XSS Prevention (CVE-2009-2937 Mitigation)

All HTML content from feeds is sanitized using `bleach`:

- Strip `<script>`, `<iframe>`, `<object>`, `<embed>` tags
- Remove all event handlers (`onclick`, `onerror`, etc.)
- Block `javascript:` and `data:` URIs
- Only allow `http://` and `https://` URL schemes
- Content Security Policy headers in generated HTML

### 7.2 SSRF Prevention

Validate feed URLs before fetching (see `_is_safe_url` in Section 5.2 for full implementation):

```python
# Inside PlanetCF class

# Cloud metadata endpoints to block (SSRF protection)
BLOCKED_METADATA_IPS = {
    '169.254.169.254',  # AWS/GCP/Azure metadata
    '100.100.100.200',  # Alibaba Cloud metadata
    '192.0.0.192',      # Oracle Cloud metadata
}

def _is_safe_url(self, url):
    """SSRF protection - reject internal/private URLs."""
    from urllib.parse import urlparse
    import ipaddress

    parsed = urlparse(url)

    # Only allow http/https
    if parsed.scheme not in ('http', 'https'):
        return False

    hostname = parsed.hostname.lower() if parsed.hostname else ""

    # Block localhost variants
    if hostname in ('localhost', '127.0.0.1', '::1', '0.0.0.0'):
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
        if ip.version == 6 and ip.packed[0] == 0xfd:
            return False
    except ValueError:
        pass  # Not an IP address

    # Block internal domain patterns
    if hostname.endswith('.internal') or hostname.endswith('.local'):
        return False

    return True
```

**Important:** URLs must be re-validated after redirects to prevent redirect-based SSRF attacks. See `_process_single_feed` in Section 5.2 which calls `_is_safe_url` on the final URL after following redirects.

### 7.3 Good Netizen Behavior

Following [rogue_planet](https://github.com/adewale/rogue_planet)'s HTTP best practices to minimize server load and avoid being blocked:

#### 7.3.1 Conditional Requests

Store and use HTTP cache headers exactly as received:

```python
# Always include conditional headers when available
headers = {"User-Agent": USER_AGENT}
if etag:
    headers["If-None-Match"] = etag
if last_modified:
    headers["If-Modified-Since"] = last_modified

response = await client.get(url, headers=headers)

# Handle 304 Not Modified - feed hasn't changed
if response.status_code == 304:
    await update_feed_success(env, feed_id, etag, last_modified)
    return  # No new content to process
```

#### 7.3.2 Rate Limiting and Retry-After

Respect HTTP 429 (Too Many Requests) and honor Retry-After headers:

```python
async def fetch_with_rate_limit_respect(url: str, headers: dict) -> httpx.Response:
    """Fetch URL while respecting rate limits."""
    
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        response = await client.get(url, headers=headers, follow_redirects=True)
        
        if response.status_code == 429:
            # Extract Retry-After (could be seconds or HTTP date)
            retry_after = response.headers.get("Retry-After")
            
            if retry_after:
                try:
                    # Try parsing as seconds
                    wait_seconds = int(retry_after)
                except ValueError:
                    # Parse as HTTP date
                    from email.utils import parsedate_to_datetime
                    retry_date = parsedate_to_datetime(retry_after)
                    wait_seconds = (retry_date - datetime.utcnow()).total_seconds()
                
                # Store retry-after for this feed, don't process until then
                raise RateLimitedError(f"Rate limited, retry after {wait_seconds}s", wait_seconds)
            
            raise RateLimitedError("Rate limited, no Retry-After header", 300)  # Default 5 min
        
        return response
```

#### 7.3.3 Exponential Backoff with Jitter

For transient failures, use exponential backoff with ±10% jitter to prevent thundering herd:

```python
import random

def calculate_backoff(attempt: int, base_seconds: float = 1.0, max_seconds: float = 300.0) -> float:
    """
    Calculate backoff delay with exponential growth and jitter.
    
    Attempt 1: ~1s
    Attempt 2: ~2s  
    Attempt 3: ~4s
    Attempt 4: ~8s
    ...capped at max_seconds
    
    Jitter adds ±10% randomization to prevent synchronized retries.
    """
    # Exponential: 2^(attempt-1) * base
    delay = min(base_seconds * (2 ** (attempt - 1)), max_seconds)
    
    # Add ±10% jitter
    jitter = delay * 0.1 * (2 * random.random() - 1)
    
    return delay + jitter
```

The queue's retry mechanism handles this automatically with `retry_delay`, but we also apply it within the worker for transient HTTP errors.

#### 7.3.4 Permanent Redirect Handling

Automatically update stored URLs on 301/308 permanent redirects (per RFC 7538):

```python
# After successful fetch
if response.history:
    for resp in response.history:
        if resp.status_code in (301, 308):
            new_url = str(response.url)
            await update_feed_url(env, feed_id, new_url)
            print(f"Feed URL permanently redirected: {old_url} -> {new_url}")
            break
```

#### 7.3.5 User-Agent Identification

Always identify with a descriptive User-Agent including contact information:

```python
USER_AGENT = "PlanetCF/1.0 (+https://planetcf.com; planet@cloudflare.com)"
```

#### 7.3.6 Request Staggering

Queue-based fan-out naturally staggers requests across time. With `max_batch_size = 5` and feeds distributed across multiple consumer invocations, we avoid hammering any single server.

---

## 8. Configuration

### 8.1 Wrangler Configuration

As of Wrangler v3.91.0 (late 2024), Cloudflare recommends **JSONC** (`wrangler.jsonc`) over TOML. New features are JSONC-first, and `npm create cloudflare@latest` now generates JSONC by default.

```jsonc
// wrangler.jsonc (Wrangler v4.58.0+, January 2026)
{
  "$schema": "node_modules/wrangler/config-schema.json",
  "name": "planetcf",
  "main": "src/main.py",
  "compatibility_date": "2026-01-01",
  "compatibility_flags": ["python_workers"],

  // CPU time limit - increase from 30s default for feed parsing
  "limits": {
    "cpu_ms": 60000
  },

  "vars": {
    "PLANET_NAME": "Planet CF",
    "PLANET_DESCRIPTION": "Aggregated posts from Cloudflare employees and community",
    "PLANET_URL": "https://planetcf.com",
    "PLANET_OWNER_NAME": "Cloudflare",
    "PLANET_OWNER_EMAIL": "planet@planetcf.com",
    "RETENTION_DAYS": "30",
    "RETENTION_MAX_ENTRIES_PER_FEED": "100",
    "FEED_TIMEOUT_SECONDS": "60",
    "HTTP_TIMEOUT_SECONDS": "30",
    "GITHUB_CLIENT_ID": "your_github_client_id"
    // Secrets (set via wrangler secret put):
    // - GITHUB_CLIENT_SECRET: OAuth client secret
    // - SESSION_SECRET: HMAC key for signed cookies (generate with: openssl rand -hex 32)
  },

  // Workers Observability
  "observability": {
    "enabled": true,
    "head_sampling_rate": 1.0
  },

  // D1 Database
  "d1_databases": [
    {
      "binding": "DB",
      "database_name": "planetcf",
      "database_id": "xxxxx"
    }
  ],

  // No KV needed:
  // - HTML/RSS/Atom/OPML: Generated on-demand, cached at edge via Cache-Control
  // - Sessions: Stateless signed cookies (HMAC), no server-side storage

  // Vectorize (for semantic search)
  "vectorize": [
    {
      "binding": "SEARCH_INDEX",
      "index_name": "planetcf-entries"
    }
  ],

  // Workers AI (for generating embeddings)
  "ai": {
    "binding": "AI"
  },

  // Queues: Scheduler -> Fetcher
  "queues": {
    "producers": [
      { "binding": "FEED_QUEUE", "queue": "planetcf-feed-queue" },
      { "binding": "DEAD_LETTER_QUEUE", "queue": "planetcf-feed-dlq" }
    ],
    "consumers": [
      {
        "queue": "planetcf-feed-queue",
        "max_batch_size": 5,
        "max_batch_timeout": 30,
        "max_retries": 3,
        "dead_letter_queue": "planetcf-feed-dlq",
        "retry_delay": 300
      }
    ]
  },

  // Cron trigger: Hourly feed fetch (content generated on-demand)
  "triggers": {
    "crons": ["0 * * * *"]
  }
}
```

**Why JSONC?**
- **Schema validation**: `$schema` enables IDE autocomplete and error checking
- **New features first**: Some Wrangler features only available in JSON config
- **Comments supported**: JSONC allows `//` comments (unlike standard JSON)
- **Consistent tooling**: Better integration with TypeScript/JavaScript ecosystems

### 8.2 Python Dependencies & Tooling

Use the **Astral toolchain** for a modern Python development experience:

| Tool | Purpose | Speed vs Traditional |
|------|---------|---------------------|
| [uv](https://docs.astral.sh/uv/) | Package management | 10-100x faster than pip |
| [ruff](https://docs.astral.sh/ruff/) | Linting + formatting | 10-100x faster than flake8+black |
| [ty](https://docs.astral.sh/ty/) | Type checking | 10-100x faster than mypy |

All three are written in Rust, configured via `pyproject.toml`, and designed to work together.

```bash
# Install dependencies (creates uv.lock)
uv sync

# Run scripts
uv run python scripts/seed_admins.py

# Development workflow
uvx ty check src/           # Type check (~2s for entire project)
uvx ruff check src/         # Lint
uvx ruff format src/        # Format
uvx ruff check --fix src/   # Auto-fix lint issues
```

```toml
# pyproject.toml

[project]
name = "planetcf"
version = "1.0.0"
requires-python = ">=3.12"

dependencies = [
    "feedparser>=6.0.0",
    "httpx>=0.27.0",
    "jinja2>=3.1.0",
    "bleach>=6.0.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

# =============================================================================
# Astral Toolchain Configuration
# =============================================================================

[tool.ty]
python-version = "3.12"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = [
    "E",      # pycodestyle errors
    "F",      # pyflakes
    "I",      # isort (import sorting)
    "UP",     # pyupgrade (modern Python syntax)
    "B",      # flake8-bugbear (common bugs)
    "SIM",    # flake8-simplify
    "ASYNC",  # flake8-async (async best practices)
    "S",      # flake8-bandit (security)
]
ignore = [
    "S104",   # Possible binding to all interfaces (intentional for Workers)
]

[tool.ruff.lint.per-file-ignores]
"scripts/*" = ["S"]  # Security checks less relevant for admin scripts

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

### 8.3 Editor Integration

ty provides a **language server** (LSP) for real-time feedback:

```bash
# VS Code: Install the ty extension, or:
# 1. Install ty globally
uv tool install ty@latest

# 2. Configure VS Code settings.json
{
  "ty.path": "ty",
  "editor.formatOnSave": true,
  "editor.defaultFormatter": "charliermarsh.ruff"
}
```

**Language server features:**
- **Inlay hints**: Show inferred types inline (no annotations needed)
- **Go to definition**: Navigate to function/class definitions
- **Auto-import**: Automatically add missing imports
- **Instant diagnostics**: <5ms feedback after edits (vs 300ms+ for pyright)

### 8.4 Continuous Integration

```yaml
# .github/workflows/check.yml
name: Check

on:
  push:
    branches: [main]
  pull_request:

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5

      - name: Install dependencies
        run: uv sync

      - name: Type check
        run: uvx ty check src/

      - name: Lint
        run: uvx ruff check src/

      - name: Format check
        run: uvx ruff format --check src/

      - name: Deploy (on main)
        if: github.ref == 'refs/heads/main'
        run: wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
```

**Why this CI is fast:**
- `uv sync`: ~1s (cached dependencies)
- `ty check`: ~2s (entire codebase)
- `ruff check + format`: <1s
- Total lint/type time: **<5 seconds** (vs 30-60s with pip + mypy + black + flake8)

---

## 9. Deployment

### 9.1 Initial Setup (Wrangler v4.58+)

```bash
# 1. Ensure modern Wrangler (v4.58.0 or later, January 2026)
npm install -g wrangler@latest

# 2. Create project directory and initialize
mkdir planetcf && cd planetcf
wrangler init --yes

# 3. Install Python dependencies with uv
uv sync

# 4. Create D1 database
wrangler d1 create planetcf

# 5. Create Vectorize index (768 dimensions for bge-base-en-v1.5)
wrangler vectorize create planetcf-entries --dimensions=768 --metric=cosine

# 6. Create queues
wrangler queues create planetcf-feed-queue
wrangler queues create planetcf-feed-dlq

# 7. Set secrets
wrangler secret put GITHUB_CLIENT_SECRET
wrangler secret put SESSION_SECRET  # Generate with: openssl rand -hex 32

# 8. Apply D1 schema
wrangler d1 execute planetcf --file=./migrations/001_initial.sql

# 9. Seed admins from config (see Section 9.3)
uv run python scripts/seed_admins.py

# 10. Deploy
wrangler deploy
```

### 9.2 Adding Initial Feeds

Via admin interface at `https://planetcf.com/admin` or D1 directly:

```sql
INSERT INTO feeds (url, title, is_active) VALUES
    ('https://blog.cloudflare.com/rss/', 'Cloudflare Blog', 1),
    ('https://jvns.ca/atom.xml', 'Julia Evans', 1),
    ('https://rachelbythebay.com/w/atom.xml', 'Rachel by the Bay', 1);
```

### 9.3 Admin Seeding from Config

Admins are seeded from `config/admins.json`, not hardcoded in migrations:

```json
{
  "admins": [
    {
      "github_username": "adewale",
      "display_name": "Adewale Oshineye"
    }
  ]
}
```

Seeding script (`scripts/seed_admins.py`):

```python
#!/usr/bin/env python3
"""Seed admin users from config/admins.json into D1."""

import json
import subprocess
import sys

def seed_admins():
    with open("config/admins.json") as f:
        config = json.load(f)
    
    for admin in config["admins"]:
        username = admin["github_username"]
        display_name = admin.get("display_name", username)
        
        sql = f"""
            INSERT INTO admins (github_username, display_name, is_active)
            VALUES ('{username}', '{display_name}', 1)
            ON CONFLICT(github_username) DO UPDATE SET
                display_name = excluded.display_name,
                is_active = 1;
        """
        
        result = subprocess.run(
            ["wrangler", "d1", "execute", "planetcf", "--command", sql],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print(f"✓ Seeded admin: {username}")
        else:
            print(f"✗ Failed to seed {username}: {result.stderr}", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    seed_admins()
```

This approach:
- Keeps admin list in version control (config file, not migrations)
- Supports idempotent re-seeding (uses `ON CONFLICT`)
- `github_id` is populated on first OAuth login
- Easy to add/remove admins by editing JSON and re-running script

---

## 10. Cost Analysis

**TL;DR: ~$5/month** — the Workers Paid plan's $5 base subscription covers everything at typical scales.

| Scale | Feeds | Monthly Views | Estimated Total |
|-------|-------|---------------|-----------------|
| Small | 50 | 10K | $5.00 |
| Medium | 100 | 100K | $5.00 |
| Large | 500 | 1M | ~$5.50 |

**Why so cheap?** Workers Paid includes 10M requests, 1M queue ops, 25B D1 reads, and 50M Vectorize queried dimensions per month. Edge caching is free. Conditional requests (304s) minimize actual fetching. Only at 500+ feeds do costs exceed the base subscription.

---

## 11. Observability 2.0

Following the principles from [Workers Observability](https://blog.cloudflare.com/introducing-workers-observability-logs-metrics-and-queries-all-in-one-place/) and the ["Logging Sucks"](https://loggingsucks.com/) philosophy of wide events.

### 11.1 Enable Workers Logs

Configure Workers Logs for all Planet CF workers:

```jsonc
// wrangler.jsonc (excerpt)
{
  "observability": {
    "enabled": true,
    "head_sampling_rate": 1.0  // Keep 100% for now (adjust for high traffic)
  }
}
```

Workers Logs provides:
- Automatic CPU time and wall time per invocation
- Queryable structured logs across all workers
- Invocation-grouped log views
- 7-day retention on paid plan

### 11.2 Wide Events (Canonical Log Lines)

Instead of scattered log statements, emit **one wide event per operation** containing all context needed for debugging. This enables queries like:

- "Show me all feed fetches that failed with timeout for feeds added this month"
- "What's the p90 wall time for feeds that return 304 vs 200?"
- "Which feeds have the highest error rate when the new queue config is enabled?"

#### Design Principles

1. **One event per operation**: One log per feed fetch, one per HTML generation, one per page serve
2. **High dimensionality**: 30+ fields capturing all relevant context
3. **High cardinality**: Include feed_id, user_id, request_id - values with millions of unique possibilities
4. **Business context**: Not just "what happened" but "who was affected and why it matters"
5. **Tail sampling**: Keep 100% of errors, sample successes

### 11.3 Wide Event Schemas

#### Feed Fetch Event

Emitted once per feed fetch attempt (by Feed Fetcher Worker):

```python
def emit_feed_fetch_event(ctx, feed, response, entries_added, error=None):
    """Emit canonical log line for a feed fetch operation."""
    
    event = {
        # Identifiers (high cardinality)
        "event_type": "feed_fetch",
        "feed_id": feed["id"],
        "feed_url": feed["url"],
        "request_id": ctx.request_id,
        "queue_message_id": ctx.message_id,
        
        # Timing
        "timestamp": datetime.utcnow().isoformat(),
        "wall_time_ms": ctx.wall_time_ms,
        "cpu_time_ms": ctx.cpu_time_ms,
        "http_latency_ms": ctx.http_latency_ms,
        
        # Feed metadata
        "feed_title": feed.get("title"),
        "feed_domain": urlparse(feed["url"]).netloc,
        "feed_age_days": days_since(feed["created_at"]),
        "feed_consecutive_failures": feed["consecutive_failures"],
        
        # HTTP details
        "http_status": response.status_code if response else None,
        "http_cached": response.status_code == 304 if response else False,
        "http_redirected": bool(response.history) if response else False,
        "response_size_bytes": len(response.content) if response else 0,
        "etag_present": bool(response.headers.get("etag")) if response else False,
        "last_modified_present": bool(response.headers.get("last-modified")) if response else False,
        
        # Parsing results
        "entries_found": ctx.entries_found,
        "entries_added": entries_added,
        "parse_errors": ctx.parse_errors,
        
        # Outcome
        "outcome": "success" if not error else "error",
        "error_type": type(error).__name__ if error else None,
        "error_message": str(error)[:500] if error else None,
        "error_retriable": getattr(error, "retriable", True) if error else None,
        
        # Context
        "worker_version": env.WORKER_VERSION,
        "queue_attempt": ctx.attempt_number,
        "scheduled_at": ctx.scheduled_at,
    }
    
    # Emit as structured log (Workers Logs captures this)
    print(json.dumps(event))
```

#### HTML Generation Event

Emitted once per HTML regeneration:

```python
def emit_generation_event(ctx, feeds_count, entries_count, error=None):
    """Emit canonical log line for HTML generation."""
    
    event = {
        "event_type": "html_generation",
        "request_id": ctx.request_id,
        
        # Timing
        "timestamp": datetime.utcnow().isoformat(),
        "wall_time_ms": ctx.wall_time_ms,
        "cpu_time_ms": ctx.cpu_time_ms,
        "d1_query_time_ms": ctx.d1_query_time_ms,
        "template_render_time_ms": ctx.template_render_time_ms,
        "kv_write_time_ms": ctx.kv_write_time_ms,
        "r2_write_time_ms": ctx.r2_write_time_ms,
        
        # Content stats
        "feeds_active": feeds_count,
        "feeds_healthy": ctx.healthy_feeds_count,
        "feeds_unhealthy": ctx.unhealthy_feeds_count,
        "entries_total": entries_count,
        "entries_by_date_count": len(ctx.entries_by_date),
        "html_size_bytes": ctx.html_size_bytes,
        "atom_size_bytes": ctx.atom_size_bytes,
        "rss_size_bytes": ctx.rss_size_bytes,
        
        # Outcome
        "outcome": "success" if not error else "error",
        "error_type": type(error).__name__ if error else None,
        "error_message": str(error)[:500] if error else None,
        
        # Trigger
        "trigger": ctx.trigger,  # "cron" | "admin_manual" | "api"
        "triggered_by": ctx.admin_username if ctx.trigger == "admin_manual" else None,
    }
    
    print(json.dumps(event))
```

#### Page Serve Event

Emitted for each HTTP request:

```python
def emit_page_serve_event(request, response, ctx):
    """Emit canonical log line for page serving."""
    
    event = {
        "event_type": "page_serve",
        "request_id": ctx.request_id,
        
        # Request
        "method": request.method,
        "path": request.url.pathname,
        "user_agent": request.headers.get("user-agent", "")[:200],
        "referer": request.headers.get("referer", "")[:200],
        "country": request.cf.country if hasattr(request, "cf") else None,
        "colo": request.cf.colo if hasattr(request, "cf") else None,
        
        # Response
        "status_code": response.status,
        "response_size_bytes": ctx.response_size_bytes,
        "cache_status": ctx.cache_status,  # "hit" | "miss" | "bypass"
        
        # Timing
        "wall_time_ms": ctx.wall_time_ms,
        "kv_read_time_ms": ctx.kv_read_time_ms,
        "r2_read_time_ms": ctx.r2_read_time_ms,
        
        # Content type
        "content_type": ctx.content_type,  # "html" | "atom" | "rss" | "static"
    }
    
    print(json.dumps(event))
```

### 11.4 Query Examples (Workers Observability Query Builder)

With wide events, use the [Workers Observability Query Builder](https://dash.cloudflare.com/?to=/:account/workers-and-pages/observability) to answer debugging questions:

**Feed health by domain:**
```
event_type = "feed_fetch" 
| GROUP BY feed_domain 
| CALCULATE 
    count() as total,
    countif(outcome = "error") as errors,
    avg(wall_time_ms) as avg_latency
| ORDER BY errors DESC
```

**Slow feeds (p90 > 5s):**
```
event_type = "feed_fetch" AND outcome = "success"
| GROUP BY feed_id, feed_url
| CALCULATE p90(wall_time_ms) as p90_latency
| WHERE p90_latency > 5000
```

**Cache effectiveness:**
```
event_type = "feed_fetch" AND outcome = "success"
| CALCULATE 
    countif(http_cached = true) as cached,
    countif(http_cached = false) as fetched,
    cached / (cached + fetched) * 100 as cache_hit_rate
```

**Error breakdown by type:**
```
event_type = "feed_fetch" AND outcome = "error"
| GROUP BY error_type
| CALCULATE count() as occurrences
| ORDER BY occurrences DESC
```

**Generation performance over time:**
```
event_type = "html_generation"
| TIMESERIES 1h
| CALCULATE 
    avg(wall_time_ms) as avg_gen_time,
    avg(entries_total) as avg_entries
```

### 11.5 Tail Sampling Strategy

For high-traffic deployments, implement tail sampling to control costs while preserving debuggability:

```python
def should_sample(event: dict) -> bool:
    """
    Decide whether to emit this event.
    
    Always keep:
    - Errors (100%)
    - Slow operations (above p95 threshold)
    - Specific feeds being debugged
    
    Sample:
    - Successful, fast operations (10%)
    """
    
    # Always keep errors
    if event.get("outcome") == "error":
        return True
    
    # Always keep slow operations
    wall_time_ms = event.get("wall_time_ms", 0)
    if event["event_type"] == "feed_fetch" and wall_time_ms > 10000:  # >10s
        return True
    if event["event_type"] == "html_generation" and wall_time_ms > 30000:  # >30s
        return True
    
    # Always keep specific feeds (for debugging)
    debug_feed_ids = env.DEBUG_FEED_IDS.split(",") if env.DEBUG_FEED_IDS else []
    if event.get("feed_id") in debug_feed_ids:
        return True
    
    # Sample successful, fast operations at 10%
    return random.random() < 0.10


def emit_event(event: dict):
    """Emit event with tail sampling."""
    if should_sample(event):
        print(json.dumps(event))
```

### 11.6 Key Metrics Dashboard

Configure a Workers Observability dashboard showing:

| Metric | Query | Alert Threshold |
|--------|-------|-----------------|
| Feed success rate | `event_type="feed_fetch" \| countif(outcome="success") / count()` | < 95% |
| Avg fetch latency | `event_type="feed_fetch" \| avg(wall_time_ms)` | > 10,000 ms |
| Generation success | `event_type="html_generation" \| outcome="success" \| count()` | = 0 in 2 hours |
| DLQ depth | Queue metrics (built-in) | > 0 |
| Cache hit rate | `event_type="feed_fetch" \| countif(http_cached) / count()` | < 50% |
| Page serve p95 | `event_type="page_serve" \| p95(wall_time_ms)` | > 500 ms |

### 11.7 Alerting

Set up alerts via Workers Observability or external integration:

| Condition | Severity | Action |
|-----------|----------|--------|
| DLQ > 0 messages | Warning | Investigate failing feeds |
| No feed fetch in 2+ hours | Critical | Check cron triggers |
| Feed success rate < 90% | Warning | Check network/upstream issues |
| p95 page latency > 1s | Warning | Check D1 queries, edge cache behavior |
| Any 5xx responses | Critical | Immediate investigation |

---

## 12. Full-Text Search (Vectorize)

Semantic search across entries using Workers AI for embeddings and Vectorize for storage/retrieval.

### 12.1 Vectorize Index Setup

```bash
# Create the search index (768 dimensions for bge-base-en-v1.5)
wrangler vectorize create planetcf-entries --dimensions=768 --metric=cosine
```

### 12.2 Embedding Generation

Embeddings are generated when entries are stored (see `_index_entry_for_search` in Section 5.2). Key implementation details:

```python
# Inside PlanetCF class (see Section 5.2 for full implementation)

async def _index_entry_for_search(self, entry_id, title, content):
    """Generate embedding and store in Vectorize for semantic search."""

    # Combine title and content for embedding (truncate to model limit)
    text = f"{title}\n\n{content[:2000]}"

    # Generate embedding using Workers AI with cls pooling for accuracy
    embedding_result = await self.env.AI.run(
        "@cf/baai/bge-base-en-v1.5",
        {"text": [text], "pooling": "cls"}  # cls pooling recommended
    )

    vector = embedding_result["data"][0]

    # Upsert to Vectorize with entry_id as the vector ID
    await self.env.SEARCH_INDEX.upsert([
        {
            "id": str(entry_id),
            "values": vector,
            "metadata": {
                "title": title[:200],
                "entry_id": entry_id
            }
        }
    ])
```

**Note:** The `pooling: "cls"` parameter uses CLS token pooling which provides better accuracy than mean pooling for this use case.

### 12.3 Search Endpoint

The search endpoint is implemented in the `_search_entries` method (see Section 5.4). It handles the `/search?q=query` route:

```python
# Inside PlanetCF class (see Section 5.4 for full implementation)

async def _search_entries(self, request):
    """Search entries by semantic similarity."""

    # Parse query from URL
    query = self._get_query_param(request, "q")
    if not query or len(query) < 2:
        return Response(
            json.dumps({"error": "Query too short"}),
            status=400,
            headers={"Content-Type": "application/json"}
        )

    # Generate embedding for search query
    embedding_result = await self.env.AI.run(
        "@cf/baai/bge-base-en-v1.5",
        {"text": [query], "pooling": "cls"}
    )
    query_vector = embedding_result["data"][0]

    # Search Vectorize
    results = await self.env.SEARCH_INDEX.query(query_vector, {
        "topK": 20,
        "returnMetadata": True
    })

    # Fetch full entries from D1 and return sorted by score
    # (see Section 5.4 for complete implementation)
```

### 12.4 Search UI

The search form is included in the HTML template header (see Section 5.3). Search results are returned as JSON and can be rendered client-side or via a separate results template.

---

## 13. OPML Import/Export

### 13.1 OPML Export (Public)

Available at `/feeds.opml` - linked from the main HTML page. Implemented as `_export_opml` method in Section 5.4:

```python
# Inside PlanetCF class

async def _export_opml(self):
    """Export all active feeds as OPML."""
    import html

    feeds = await self.env.DB.prepare("""
        SELECT url, title, site_url
        FROM feeds
        WHERE is_active = 1
        ORDER BY title
    """).all()

    opml = f'''<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head>
    <title>Planet CF Subscriptions</title>
    <dateCreated>{datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")}</dateCreated>
    <ownerName>{self.env.PLANET_OWNER_NAME}</ownerName>
  </head>
  <body>
    <outline text="Planet CF Feeds" title="Planet CF Feeds">
'''

    for feed in feeds.results:
        title = html.escape(feed["title"] or feed["url"])
        xml_url = html.escape(feed["url"])
        html_url = html.escape(feed["site_url"] or "")
        opml += f'      <outline type="rss" text="{title}" title="{title}" xmlUrl="{xml_url}" htmlUrl="{html_url}"/>\n'

    opml += '''    </outline>
  </body>
</opml>'''

    return Response(opml, headers={
        "Content-Type": "application/xml; charset=utf-8",
        "Content-Disposition": 'attachment; filename="planetcf-feeds.opml"'
    })
```

Add link in HTML template footer:

```html
<footer>
    <p>
        <a href="/feed.atom">Atom</a> · 
        <a href="/feed.rss">RSS</a> · 
        <a href="/feeds.opml">OPML</a>
    </p>
</footer>
```

### 13.2 OPML Import (Admin Only)

Implemented as `_import_opml` method, called from the admin route handler in Section 5.4:

```python
# Inside PlanetCF class

async def _import_opml(self, request, admin):
    """Import feeds from uploaded OPML file. Admin only."""
    import xml.etree.ElementTree as ET

    form = await request.formData()
    opml_file = form.get("opml")

    if not opml_file:
        return Response(
            json.dumps({"error": "No file uploaded"}),
            status=400,
            headers={"Content-Type": "application/json"}
        )

    content = await opml_file.text()

    # Parse OPML
    root = ET.fromstring(content)

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
            await self.env.DB.prepare("""
                INSERT INTO feeds (url, title, site_url, is_active)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(url) DO NOTHING
            """).bind(xml_url, title, html_url).run()
            imported += 1
        except Exception as e:
            skipped += 1
            errors.append(f"Failed to import {xml_url}: {e}")

    # Audit log
    await self._log_admin_action(admin["id"], "import_opml", "feeds", None, {
        "imported": imported,
        "skipped": skipped,
        "errors": errors[:10]
    })

    return Response(
        json.dumps({
            "imported": imported,
            "skipped": skipped,
            "errors": errors[:10]
        }),
        headers={"Content-Type": "application/json"}
    )

async def _log_admin_action(self, admin_id, action, target_type, target_id, details):
    """Log an admin action to the audit log."""
    await self.env.DB.prepare("""
        INSERT INTO audit_log (admin_id, action, target_type, target_id, details)
        VALUES (?, ?, ?, ?, ?)
    """).bind(admin_id, action, target_type, target_id, json.dumps(details)).run()
```

### 13.3 Admin Import UI

```html
<form action="/admin/import-opml" method="POST" enctype="multipart/form-data">
    <label for="opml">Import feeds from OPML:</label>
    <input type="file" id="opml" name="opml" accept=".opml,.xml">
    <button type="submit">Import</button>
</form>
```

---

## 14. References

- [rogue_planet](https://github.com/adewale/rogue_planet) - Design inspiration, good netizen practices
- [Planet Venus](https://github.com/rubys/venus) - Original Planet aggregator
- [Cloudflare Python Workers docs](https://developers.cloudflare.com/workers/languages/python/)
- [Cloudflare Queues docs](https://developers.cloudflare.com/queues/)
- [Cloudflare D1 docs](https://developers.cloudflare.com/d1/)
- [Cloudflare Vectorize docs](https://developers.cloudflare.com/vectorize/)
- [Workers AI docs](https://developers.cloudflare.com/workers-ai/)
- [Workers Observability](https://blog.cloudflare.com/introducing-workers-observability-logs-metrics-and-queries-all-in-one-place/) - Workers Logs, Query Builder
- [Logging Sucks](https://loggingsucks.com/) - Wide events philosophy
- [feedparser documentation](https://feedparser.readthedocs.io/)
- [CVE-2009-2937](https://nvd.nist.gov/vuln/detail/CVE-2009-2937) - Planet Venus XSS vulnerability
