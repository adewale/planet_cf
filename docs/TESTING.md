# Testing Guide

PlanetCF has three test tiers: unit, integration, and end-to-end (E2E).

## Quick Start

```bash
# Run unit tests (fast, no dependencies)
uv run pytest tests/unit -v

# Run integration tests (requires no external services)
uv run pytest tests/integration -v

# Run all non-E2E tests
uv run pytest tests/unit tests/integration -v
```

## Test Tiers

### Unit Tests (tests/unit/)

Pure unit tests using mock Cloudflare bindings. No server needed.

- **739 tests**, runs in ~1 second
- Uses `MockD1`, `MockVectorize`, `MockAI`, `MockQueue` from `tests/conftest.py`
- Simulates JsProxy behavior to catch conversion issues
- Covers: rendering, search, config, auth, feeds, entries, observability

### Integration Tests (tests/integration/)

Tests that verify end-to-end flows using mock bindings. No external services needed.

- **85+ tests**, runs in ~2 seconds
- Covers: HTTP endpoints, feed processing, search, admin UI, scheduler
- Uses factory fixtures (`FeedFactory`, `EntryFactory`, `SessionFactory`)

### E2E Tests (tests/e2e/)

Tests against real Cloudflare infrastructure (D1, Vectorize, Workers AI).

- **34 tests**, requires a running test-planet instance
- Catches: JsProxy bugs, real SQL issues, Vectorize integration, network timing

## Why E2E Tests Exist

Unit and integration tests use mock Cloudflare bindings (`MockD1`, `MockVectorize`, etc.) which simulate the real services in Python. These mocks are fast and reliable, but they cannot catch several classes of bugs that only appear with real infrastructure:

- **JsProxy conversion**: Cloudflare Python Workers run on Pyodide, where JavaScript objects are returned as `JsProxy` wrappers. Mock tests return plain Python objects, so they miss cases where code fails to convert a JsProxy to a native type (e.g., calling `.to_py()` on query results).
- **Real D1 SQL behavior**: Mock D1 uses Python's sqlite3 module, which has subtle differences from D1's actual SQLite dialect. `LIKE` queries, type coercion, and `ON CONFLICT` behavior can differ.
- **Vectorize similarity filtering**: Mock Vectorize returns all stored vectors for any query. Real Vectorize applies cosine similarity thresholds and returns only genuinely similar results, so search ranking bugs only surface with real embeddings.
- **Workers AI embeddings**: Mock AI returns fixed-dimension zero vectors. Real Workers AI generates meaningful embeddings that affect search quality. A search test passing with mocks tells you nothing about whether the right results appear for a given query.
- **Network timing and error handling**: Real feed fetching, queue processing, and HTTP timeouts behave differently from instant mock responses.

The Test Planet instance exists to run these tests against real Cloudflare services (D1, Vectorize, Workers AI, Queues) in an isolated environment with deterministic seed data.

## Setting Up E2E Tests

Each developer creates their own isolated test-planet instance in their own Cloudflare account. There is no shared test instance -- this ensures test isolation and avoids credential sharing.

### Create Your Own Test Planet

```bash
# 1. Create instance config
python scripts/create_instance.py \
  --id my-test-planet \
  --name "My Test Planet" \
  --mode full

# 2. Deploy infrastructure (creates D1, Vectorize, queues in your account)
./scripts/deploy_instance.sh my-test-planet --skip-secrets

# 3. Set a session secret (remember this for step 5)
echo "my-test-secret-here" | \
  npx wrangler secret put SESSION_SECRET \
  --config examples/my-test-planet/wrangler.jsonc

# 4. Seed test data
uv run python scripts/seed_test_data.py \
  --db-name my-test-planet-db \
  --config examples/my-test-planet/wrangler.jsonc

# 5. Run E2E tests
E2E_BASE_URL=https://my-test-planet.your-account.workers.dev \
E2E_SESSION_SECRET=my-test-secret-here \
uv run pytest tests/e2e/ -v
```

### One-Command Setup

If you want to automate all of the above:

```bash
./scripts/setup_test_planet.sh
```

This script creates infrastructure, sets secrets, seeds data, and deploys the worker.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `E2E_BASE_URL` | `http://localhost:8787` | URL of the test server |
| `E2E_SESSION_SECRET` | `test-session-secret-for-e2e-testing-only` | Session secret matching the worker |
| `E2E_ADMIN_USERNAME` | `testadmin` | Admin username seeded in the database |
| `RUN_E2E_TESTS` | (unset) | Set to `1` to enable search accuracy tests |

## CI Integration

### Unit + Integration (automatic)

Runs on every push and PR via `.github/workflows/check.yml`:
- Type checking, linting, formatting
- Unit tests + integration tests
- 60% minimum coverage

### E2E (manual + main branch)

Runs via `.github/workflows/e2e.yml`:
- Triggered manually via `workflow_dispatch` or on push to `main`
- Requires `CLOUDFLARE_API_TOKEN` and `TEST_PLANET_URL` secrets
- Seeds test data then runs E2E suite

## Test Data

Test data comes from `tests/fixtures/blog_posts.json`:
- 3 feeds (Cloudflare Blog, Workers Team Blog, Engineering at Scale)
- 10 entries with realistic content
- 14 test queries with expected results

Seed this data with:
```bash
uv run python scripts/seed_test_data.py --local   # Local D1
uv run python scripts/seed_test_data.py            # Remote D1
```

## Troubleshooting

**Tests skip with "server not running"**: Start wrangler dev first.

**Admin tests return 403**: Seed the test admin: `uv run python scripts/seed_test_data.py --local`

**Search returns no results**: Trigger a reindex: `uv run python scripts/seed_test_data.py --reindex --base-url http://localhost:8787`

**Session cookie rejected**: Ensure `E2E_SESSION_SECRET` matches the worker's `SESSION_SECRET`.
