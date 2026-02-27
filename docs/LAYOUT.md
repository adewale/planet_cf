# Planet CF Layout Documentation

This document describes the visual structure of the Planet CF homepage using annotated ASCII diagrams.

## Overall Page Structure

```
+================================================================================+
|                                   HEADER                                        |
|  +--------------------------------------------------------------------------+  |
|  |  | Planet CF                           <- h1 with subtle accent bar      |  |
|  |  Aggregated posts from Cloudflare...   <- p.description (from env var)   |  |
|  +--------------------------------------------------------------------------+  |
+================================================================================+

+==========================================================+====================+
|                        MAIN                              |      SIDEBAR       |
|                    (grid: 1fr)                           |   (grid: 300px)    |
|                                                          |                    |
|  +----------------------------------------------------+  |  +==============+  |
|  | <section class="day">                              |  |  | SEARCH FORM  |  |
|  |                                                    |  |  | [Search...]  |  |
|  |   JANUARY 15, 2026    <- h2.date (absolute date)  |  |  | [Search]     |  |
|  |   ------------------                               |  |  +==============+  |
|  |                                                    |  |  --------------- |  |
|  |  +----------------------------------------------+  |  |                  |  |
|  |  | <article>                                    |  |  |  SUBSCRIPTIONS   |  |
|  |  |   Entry Title        <- h3 > a (linked)     |  |  |  --------------- |  |
|  |  |   Author · Jan 2026  <- p.meta              |  |  |  * Boris Tane    |  |
|  |  |   +----------------------------------------+|  |  |  * Ade Oshineye  |  |
|  |  |   | <div class="content">                  ||  |  |  * Sunil Pai     |  |
|  |  |   | Full sanitized HTML content...         ||  |  |                  |  |
|  |  |   +----------------------------------------+|  |  |                  |  |
|  |  +----------------------------------------------+  |  |                  |  |
|  |                                                    |  |                  |  |
|  |  +----------------------------------------------+  |  |                  |  |
|  |  | <article> (another entry same day)          |  |  |                  |  |
|  |  +----------------------------------------------+  |  |                  |  |
|  +----------------------------------------------------+  |                  |  |
|                                                          |                  |  |
|  +----------------------------------------------------+  |                  |  |
|  | <section class="day">  (next day)                  |  |                  |  |
|  |   NOVEMBER 24, 2025                                |  |                  |  |
|  |   ...                                              |  |                  |  |
|  +----------------------------------------------------+  |                  |  |
|                                                          |                  |  |
+==========================================================+====================+

+================================================================================+
|                                   FOOTER                                        |
|                         Atom | RSS | OPML | Admin                               |
|                      Last updated: 2026-01-15 02:00 UTC                         |
+================================================================================+
```

## Day Section Structure

Each day is a `<section class="day">` containing entries from that publication date:

```
+------------------------------------------------------------------------+
| <section class="day">                                                   |
|                                                                         |
|   JANUARY 15, 2026                                                      |
|   ================                                                      |
|   ^                                                                     |
|   |                                                                     |
|   +-- <h2 class="date">                                                 |
|       Absolute date format: "Month DD, YYYY"                            |
|       Grouped by published_at (actual publication date from feed)       |
|       Falls back to first_seen if published_at missing                  |
|                                                                         |
|  +------------------------------------------------------------------+   |
|  | <article>                                                        |   |
|  |                                                                  |   |
|  |  Open always wins?                                               |   |
|  |  ^                                                               |   |
|  |  +-- <h3><a href="...">                                          |   |
|  |      Title links to original blog post                           |   |
|  |                                                                  |   |
|  |  Ade Oshineye · Jan 2026                                         |   |
|  |  ^              ^                                                |   |
|  |  |              +-- <time> published_at_display                  |   |
|  |  +-- <span class="author">                                       |   |
|  |      Shows entry.author or feed.title as fallback                |   |
|  |                                                                  |   |
|  |  +------------------------------------------------------------+  |   |
|  |  | <div class="content">                                      |  |   |
|  |  |                                                            |  |   |
|  |  | The full sanitized HTML content from the feed.             |  |   |
|  |  | - Scripts/styles removed                                   |  |   |
|  |  | - External links open in new tab with rel="noopener"       |  |   |
|  |  | - Images have loading="lazy"                               |  |   |
|  |  | - Relative URLs converted to absolute                      |  |   |
|  |  |                                                            |  |   |
|  |  +------------------------------------------------------------+  |   |
|  +------------------------------------------------------------------+   |
|                                                                         |
|  +------------------------------------------------------------------+   |
|  | <article>  (max 5 entries per feed per day)                      |   |
|  |   ...                                                            |   |
|  +------------------------------------------------------------------+   |
|                                                                         |
+------------------------------------------------------------------------+
```

## Sidebar Structure

The sidebar contains the search form and feed subscriptions:

```
+======================================+
| <aside class="sidebar">              |
|                                      |
|  +--------------------------------+  |
|  | <form class="search-form">     |  |
|  |                                |  |
|  | +----------------------------+ |  |
|  | | <input type="search">      | |  |
|  | | placeholder="Search..."    | |  |
|  | +----------------------------+ |  |
|  |                                |  |
|  | +----------------------------+ |  |
|  | |        [Search]            | |  |
|  | |    <button type="submit">  | |  |
|  | +----------------------------+ |  |
|  |                                |  |
|  +--------------------------------+  |
|  ----------------------------------- |
|  ^                                   |
|  +-- border-bottom separator         |
|                                      |
|  SUBSCRIPTIONS                       |
|  ==============                      |
|  ^                                   |
|  +-- <h2> section heading            |
|                                      |
|  +--------------------------------+  |
|  | <ul class="feeds">             |  |
|  |                                |  |
|  | * Boris Tane           [OK]   |  |
|  |   ^                     ^     |  |
|  |   |                     |     |  |
|  |   +-- <li><a href=".."> |     |  |
|  |       Links to feed's   |     |  |
|  |       site_url          |     |  |
|  |                         |     |  |
|  |       class="healthy" --+     |  |
|  |       or "unhealthy"          |  |
|  |       (based on failures)     |  |
|  |                                |  |
|  | * Ade Oshineye         [OK]   |  |
|  |                                |  |
|  | * Sunil Pai            [OK]   |  |
|  |                                |  |
|  +--------------------------------+  |
|                                      |
+======================================+

Health Status Logic:
- "healthy" (green): consecutive_failures < 3
- "unhealthy" (red): consecutive_failures >= 3
- Auto-deactivated after 10 consecutive failures
```

## Entry Grouping Logic

Entries are grouped and sorted as follows:

```
1. SQL Query Orders by:
   COALESCE(published_at, first_seen) DESC

2. Python Groups by:
   date_str = (entry.published_at or entry.first_seen)[:10]

3. Date Label Format:
   "January 15, 2026" (absolute, not "Today" or "Yesterday")

4. Limits Applied:
   - Max 5 entries per feed per day (prevents firehose)
   - Max 100 entries total per feed (configurable via MAX_ENTRIES_PER_FEED)
   - Retention: 90 days (configurable via RETENTION_DAYS env var)
```

## Responsive Behavior

```
Desktop (> 768px):                    Mobile (<= 768px):
+====================+=======+        +====================+
|                    |       |        |                    |
|       MAIN         | SIDE  |        |      SIDEBAR       |
|                    | BAR   |        |      (search)      |
|                    |       |        |                    |
+====================+=======+        +====================+
                                      |                    |
grid-template-columns:                |       MAIN         |
  1fr 300px                           |      (entries)     |
                                      |                    |
                                      +====================+

                                      grid-template-columns:
                                        1fr
```
