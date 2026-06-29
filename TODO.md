# TODO

Deferred issues from the deep-dive audit (2026-03-11).

## P1 — N+1 query pattern in feed processing (High) — PARTIALLY MITIGATED

The feed processing pipeline issues per-entry database queries instead of
batching.

**Already addressed (H1, see audit-reports/2026-06-13-re-audit.md):** the worst
offenders are gone — `feeds.last_entry_at` is now updated **once** per fetch
(was once per entry), and search re-embedding now fires only on a genuine
insert or content change (was every entry on every fetch). This removes the
bulk of the per-cycle query/Workers-AI load.

**Remaining:** the per-entry `INSERT ... ON CONFLICT` upsert still runs one
statement per entry.

**Location:** `src/main.py` — `_upsert_entry` in the queue-consumer path.

**Fix:** Batch the entry upserts via D1's `db.batch([...])` where the
insert/update branching allows. **Profile first** — Cloudflare D1 may pipeline
small statements efficiently enough that the overhead is negligible at current
feed/entry counts, and the H1 rewrite depends on per-statement `RETURNING id`
to distinguish inserts, which a naive batch would lose.

## BP8 — Inactive feeds included in OPML export (Low) — RESOLVED

The OPML export route is `/feeds.opml` (not `GET /opml`). Its query (`_export_opml`
in `src/main.py`) historically exported all feeds, including those with
`is_active = 0`, so importers would re-subscribe to feeds the admin had disabled.

**Resolution:** A `WHERE is_active = 1` filter is being added to the `/feeds.opml`
export query so it exports only active feeds (matching its docstring). Note the
sibling `/foafroll.xml` route (`_serve_foaf`) had the same gap and should be
filtered the same way.

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
