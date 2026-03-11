# TODO

Deferred issues from the deep-dive audit (2026-03-11).

## P1 — N+1 query pattern in feed processing (High)

The feed processing pipeline issues one database query per feed instead of
batching. Under load with many feeds, this creates unnecessary round-trips.

**Location:** `src/main.py` — feed fetch/update cycle in the queue consumer and
cron-triggered processing paths.

**Fix:** Batch `SELECT`/`INSERT`/`UPDATE` operations where D1 supports it.
Profile first — Cloudflare D1 may pipeline small queries efficiently enough that
the overhead is negligible at current feed counts.

## BP8 — Inactive feeds included in OPML export (Low)

`GET /opml` exports all feeds including those with `is_active = 0`. Users
importing the OPML into another reader will subscribe to feeds the admin
intentionally disabled.

**Location:** `src/main.py` — OPML generation query.

**Fix:** Add `WHERE is_active = 1` to the OPML export query, or add an optional
`?include_inactive=1` query parameter for admins who want the full list.
