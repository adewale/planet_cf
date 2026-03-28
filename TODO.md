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

## Ops — Set up real mailboxes for planetcloudflare.dev (Low)

Two email addresses are referenced but have no mailbox behind them:

- `contact@planetcloudflare.dev` — used in the User-Agent string (`src/config.py`)
- `planet@planetcloudflare.dev` — used as the author email (`pyproject.toml`)

**Fix:** Set up mailboxes or forwarding via Cloudflare Email Routing.

## Pyodide 0.29 — Revisit `_to_js_value` when Workers upgrades (Medium)

Cloudflare Workers currently ships Pyodide **0.28.2**. Pyodide **0.29.0** changed
`to_js()` to convert dicts to JS `Object` by default (instead of `LiteralMap`).
When Workers upgrades to 0.29+, our `dict_converter=js.Object.fromEntries` in
`_to_js_value()` becomes redundant (but harmless).

**When to act:** Check `workerd/build/python_metadata.bzl` periodically for new
Pyodide versions. When a 0.29+ entry appears and our `compatibility_date` enables
it, verify:

1. `dict_converter` is still harmless (it should be — Object.fromEntries on an
   Object is a no-op)
2. Remove the `dict_converter` parameter if desired (simplification, not required)
3. Run the `6-vectorize-map-vs-object` reproduction in `python-workers-issues` —
   the `/bug` endpoint should start succeeding (no more LiteralMap), confirming
   the runtime change
4. Update lesson 29 in `docs/LESSONS_LEARNED.md`

**Location:** `src/wrappers.py` — `_to_js_value()`

**Tracking:** [workerd python_metadata.bzl](https://github.com/cloudflare/workerd/blob/main/build/python_metadata.bzl)
