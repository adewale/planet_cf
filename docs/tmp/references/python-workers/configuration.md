# Python Workers — Configuration

Complete reference for wrangler.jsonc, pyproject.toml, compatibility flags, all binding configurations, secrets, deployment, and test setup.

---

## Table of Contents

- [wrangler.jsonc — Full Reference](#wranglerJsonc--full-reference)
- [Compatibility Flags](#compatibility-flags)
- [pyproject.toml](#pyprojecttoml)
- [Package Management](#package-management)
- [Binding Configuration](#binding-configuration) — D1, KV, R2, Queues, Vectorize, AI, DOs, Assets, Workflows
- [Secrets Management](#secrets-management)
- [CPU Limits](#cpu-limits)
- [Observability](#observability)
- [Cron Triggers](#cron-triggers)
- [Local Development](#local-development)
- [Deployment](#deployment)
- [Test Setup](#test-setup)
- [Multi-Instance Deployment](#multi-instance-deployment)

---

## wrangler.jsonc — Full Reference

```jsonc
{
  // IDE autocompletion for all wrangler config keys
  "$schema": "node_modules/wrangler/config-schema.json",

  "name": "my-python-worker",
  "main": "src/main.py",
  "compatibility_date": "2026-01-01",
  "compatibility_flags": ["python_workers", "python_dedicated_snapshot"],

  // CPU time limit (default 30s paid, 10ms free)
  "limits": {
    "cpu_ms": 60000
  },

  // Environment variables (non-secret, committed to repo)
  "vars": {
    "APP_NAME": "My App",
    "RETENTION_DAYS": "90",
    "DEPLOYMENT_ENVIRONMENT": "production"
  },

  // Observability (structured logs + traces)
  "observability": {
    "enabled": true,
    "head_sampling_rate": 1.0,
    "traces": {
      "enabled": true,
      "head_sampling_rate": 1
    }
  },

  // D1 Database
  "d1_databases": [
    {
      "binding": "DB",
      "database_name": "my-db",
      "database_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
      "remote": true       // Use remote DB in local dev
    }
  ],

  // Vectorize (vector embeddings search)
  "vectorize": [
    {
      "binding": "SEARCH_INDEX",
      "index_name": "my-entries-index",
      "remote": true       // Required — no local simulation
    }
  ],

  // Workers AI (inference)
  "ai": {
    "binding": "AI",
    "remote": true         // Use remote AI in local dev
  },

  // Version metadata (deployment tracking)
  "version_metadata": {
    "binding": "VERSION_METADATA"
  },

  // KV Namespaces
  "kv_namespaces": [
    {
      "binding": "MY_KV",
      "id": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    }
  ],

  // R2 Buckets
  "r2_buckets": [
    {
      "binding": "MY_BUCKET",
      "bucket_name": "my-bucket"
    }
  ],

  // Queues
  "queues": {
    "producers": [
      { "binding": "FEED_QUEUE", "queue": "my-feed-queue" },
      { "binding": "DEAD_LETTER_QUEUE", "queue": "my-feed-dlq" }
    ],
    "consumers": [
      {
        "queue": "my-feed-queue",
        "max_batch_size": 5,        // Messages per batch (max 100)
        "max_batch_timeout": 30,    // Seconds to wait for full batch
        "max_retries": 3,           // Retries before dead-letter
        "dead_letter_queue": "my-feed-dlq",
        "retry_delay": 300          // Seconds between retries
      }
    ]
  },

  // Static Assets
  "assets": {
    "directory": "./assets/",
    "binding": "ASSETS"
  },

  // Durable Objects
  "durable_objects": {
    "bindings": [
      { "name": "MY_COUNTER", "class_name": "MyCounter" }
    ]
  },
  "migrations": [
    { "tag": "v1", "new_sqlite_classes": ["MyCounter"] }
  ],

  // Workflows
  "workflows": [
    {
      "name": "my-workflow",
      "binding": "MY_WORKFLOW",
      "class_name": "MyWorkflow"
    }
  ],

  // Cron triggers
  "triggers": {
    "crons": ["0 * * * *"]    // Hourly
  }
}
```

---

## Compatibility Flags

| Flag | Required | Purpose |
|------|----------|---------|
| `python_workers` | **Yes** | Enables Python Worker runtime |
| `python_dedicated_snapshot` | Recommended | Worker-specific Wasm memory snapshot (faster cold starts) |
| `python_workflows` | For Workflows | Enables Python Workflow support |
| `experimental` | Sometimes | Required alongside `python_workflows` |
| `disable_python_no_global_handlers` | Legacy only | Keeps deprecated `on_fetch`/`on_scheduled` pattern |

**Compatibility date**: Use `2026-01-01` or later for new projects.

---

## pyproject.toml

```toml
[project]
name = "my-python-worker"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "feedparser>=6.0.0",
    "httpx>=0.27.0",
    "jinja2>=3.1.0",
    "bleach>=6.0.0",
    "markupsafe>=2.0.0",
]

[dependency-groups]
workers = [
    "workers-py",              # pywrangler CLI
    "workers-runtime-sdk",     # Type hints + IDE autocompletion
]
test = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "respx>=0.22",             # httpx mocking
    "freezegun>=1.4",          # Time mocking
]
dev = [
    "ruff>=0.8",               # Linting + formatting
]
```

**Key points**:
- `workers-py` provides the `pywrangler` CLI
- `workers-runtime-sdk` provides type stubs (run `uv run pywrangler types` to generate Env types)
- `webtypy>=0.1.7` provides web API type stubs (optional, useful for IDE completion)
- Only list packages in `dependencies` that will be deployed — dev/test deps go in dependency groups

---

## Package Management

### Adding packages

```bash
uv add httpx jinja2 bleach        # Add to [project].dependencies
uv add --group test pytest         # Add to [dependency-groups].test
uv add --group dev ruff            # Add to [dependency-groups].dev
```

### Supported packages

- **Pure Python** from PyPI (most packages)
- **Pyodide packages** (compiled to WebAssembly): numpy, pandas, pillow, etc.
- Full Pyodide list: https://pyodide.org/en/stable/usage/packages-in-pyodide.html

### HTTP clients

Only **async** HTTP libraries work:

| Library | Status | Notes |
|---------|--------|-------|
| `httpx` (async) | Works | Recommended |
| `aiohttp` | Works | Alternative |
| `requests` | **Fails** | Sync — blocks event loop |
| `urllib3` | **Fails** | Sync — blocks event loop |
| `js.fetch` via FFI | Works | Direct JS fetch access |

### Requesting new packages

Open a discussion at: https://github.com/cloudflare/workerd/discussions/categories/python-packages

---

## Binding Configuration

### D1 Database

```bash
# Create
npx wrangler d1 create my-db

# Run migrations
npx wrangler d1 execute my-db --remote --file migrations/001_initial.sql

# List databases
npx wrangler d1 list
```

```jsonc
"d1_databases": [{
  "binding": "DB",
  "database_name": "my-db",
  "database_id": "from-d1-create-output"
}]
```

### Vectorize

```bash
# Create index (768-dim for bge-small-en-v1.5 embeddings)
npx wrangler vectorize create my-index --dimensions=768 --metric=cosine
```

```jsonc
"vectorize": [{
  "binding": "SEARCH_INDEX",
  "index_name": "my-index",
  "remote": true            // Required — no local simulation
}]
```

### Queues

```bash
# Create queues
npx wrangler queues create my-feed-queue
npx wrangler queues create my-feed-dlq

# List queues
npx wrangler queues list
```

Queue consumer config options:

| Option | Default | Description |
|--------|---------|-------------|
| `max_batch_size` | 10 | Messages per batch (max 100) |
| `max_batch_timeout` | 5 | Seconds to wait for full batch |
| `max_retries` | 3 | Retries before dead-letter |
| `dead_letter_queue` | none | Queue name for failed messages |
| `retry_delay` | 0 | Seconds between retries |

### KV Namespaces

```bash
npx wrangler kv namespace create MY_KV
```

```jsonc
"kv_namespaces": [{
  "binding": "MY_KV",
  "id": "from-kv-create-output"
}]
```

### R2 Buckets

```bash
npx wrangler r2 bucket create my-bucket
```

```jsonc
"r2_buckets": [{
  "binding": "MY_BUCKET",
  "bucket_name": "my-bucket"
}]
```

### Durable Objects

```jsonc
"durable_objects": {
  "bindings": [
    { "name": "MY_DO", "class_name": "MyDurableObject" }
  ]
},
"migrations": [
  { "tag": "v1", "new_sqlite_classes": ["MyDurableObject"] }
]
```

### Static Assets

```jsonc
"assets": {
  "directory": "./assets/",     // Directory to serve
  "binding": "ASSETS"           // Binding name for programmatic access
}
```

Assets are cached at the edge automatically. No additional CDN configuration needed.

### Workflows

```jsonc
"compatibility_flags": ["python_workers", "python_workflows"],
"workflows": [{
  "name": "my-workflow",
  "binding": "MY_WORKFLOW",
  "class_name": "MyWorkflow"
}]
```

---

## Secrets Management

```bash
# Set secrets (interactive prompt — never passed as CLI args)
npx wrangler secret put GITHUB_CLIENT_ID
npx wrangler secret put GITHUB_CLIENT_SECRET
npx wrangler secret put SESSION_SECRET

# Generate a strong secret
openssl rand -hex 32

# List secrets (names only, not values)
npx wrangler secret list
```

Access in code via `self.env.SECRET_NAME`. Secrets are encrypted at rest and never appear in logs.

**Never put secrets in**:
- `wrangler.jsonc` `"vars"` section
- Source code
- `.env` files committed to git

---

## CPU Limits

| Plan | Default CPU | Max CPU |
|------|-------------|---------|
| Free | 10ms | 10ms |
| Paid | 30ms | 900,000ms (15 min) |

```jsonc
"limits": {
  "cpu_ms": 60000    // 60 seconds
}
```

**CPU time** counts only computation, not I/O wait. Awaiting `fetch()`, D1 queries, or queue sends does NOT count against CPU time. Heavy Python parsing (feedparser, JSON, bleach sanitization) does.

---

## Observability

```jsonc
"observability": {
  "enabled": true,
  "head_sampling_rate": 1.0,    // 0.0-1.0, percentage of requests to log
  "traces": {
    "enabled": true,
    "head_sampling_rate": 1     // Trace sampling rate
  }
}
```

### Version metadata

Track which deployment is serving requests:

```jsonc
"version_metadata": {
  "binding": "VERSION_METADATA"
}
```

```python
version = self.env.VERSION_METADATA.id  # Deployment version ID
```

---

## Cron Triggers

```jsonc
"triggers": {
  "crons": [
    "0 * * * *",       // Every hour
    "*/5 * * * *",     // Every 5 minutes
    "0 0 * * *",       // Daily at midnight
    "0 0 * * 1"        // Every Monday at midnight
  ]
}
```

Handled by the `scheduled` method on `WorkerEntrypoint`.

---

## Local Development

```bash
# Start local dev server
uv run pywrangler dev

# With remote bindings (connect to real D1/Vectorize/AI)
# Set "remote": true on bindings in wrangler.jsonc
```

**Vectorize** has no local simulation — you **must** use `"remote": true` during development.

**D1** can run locally (in-memory) or remotely. Use `"remote": true` to develop against production data.

---

## Deployment

```bash
# Deploy to Cloudflare
uv run pywrangler deploy

# Or with npx (if not using pywrangler)
npx wrangler deploy

# Deploy specific instance config
npx wrangler deploy --config examples/my-instance/wrangler.jsonc
```

### Pre-deployment checklist

1. All tests pass (`make test` or `pytest`)
2. Lint passes (`ruff check .`)
3. Secrets are set (`npx wrangler secret list`)
4. Database migrations are run
5. Required resources exist (D1, Queues, Vectorize index)

### Database migrations

```bash
# Run a migration
npx wrangler d1 execute my-db --remote --file migrations/001_initial.sql

# Run all migrations in order
for f in migrations/*.sql; do
  npx wrangler d1 execute my-db --remote --file "$f"
done
```

---

## Test Setup

### pytest configuration (pyproject.toml)

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
python_files = "test_*.py"
python_classes = "Test*"
python_functions = "test_*"
```

### Makefile targets

```makefile
test:
	uv run pytest tests/unit tests/integration -x -q

test-unit:
	uv run pytest tests/unit -x -q

test-integration:
	uv run pytest tests/integration -x -q

test-cov:
	uv run pytest tests/unit tests/integration --cov=src --cov-report=term-missing

lint:
	uv run ruff check .
	uv run ruff format --check .

fmt:
	uv run ruff format .
	uv run ruff check --fix .

check:
	$(MAKE) lint
	$(MAKE) test
```

See `patterns.md` (Testing section) for mock binding implementations.

---

## Multi-Instance Deployment

Share one codebase across multiple deployments:

```
project-root/
├── src/                          # Shared source code
├── examples/
│   ├── default/
│   │   └── wrangler.jsonc        # Minimal lite-mode config
│   ├── instance-a/
│   │   ├── wrangler.jsonc        # Full config with own DB, keys
│   │   └── templates/            # Custom theme (optional)
│   └── instance-b/
│       └── wrangler.jsonc
└── wrangler.jsonc                # Dev/default config
```

Each instance has its own:
- `wrangler.jsonc` with unique `name`, `database_id`, secrets
- D1 database, Vectorize index, Queue names
- Environment variables (branding, feature flags)

Deploy a specific instance:

```bash
npx wrangler deploy --config examples/instance-a/wrangler.jsonc
```
