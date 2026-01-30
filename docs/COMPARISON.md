# Feed Aggregator Comparison: Planet CF vs Planet Venus vs Rogue Planet

This document provides a comprehensive feature comparison between three planet feed aggregators:

- **Planet CF** - Modern Cloudflare Workers-based aggregator (this project)
- **Planet Venus** - Classic Python feed aggregator by Sam Ruby
- **Rogue Planet** - Modern Go-based static site generator

---

## 1. Core Features

| Feature | Planet CF | Planet Venus | Rogue Planet |
|---------|-----------|--------------|--------------|
| Feed aggregation | ✅ RSS/Atom | ✅ RSS/Atom/CDF/RDF | ✅ RSS 1.0/2.0, Atom 1.0, JSON Feed |
| Content display | ✅ Full posts + excerpts | ✅ Full posts + excerpts | ✅ Full posts |
| Date grouping | ✅ Configurable | ✅ Via templates | ✅ Built-in |
| Pagination | ⚠️ Recent entries fallback | ✅ items_per_page | ⚠️ Static single page |
| Search | ✅ Semantic + keyword hybrid | ❌ None | ❌ None |
| Multi-instance support | ✅ First-class CLI tooling | ⚠️ Separate config files | ⚠️ Separate installations |
| Responsive design | ✅ Mobile-first | ⚠️ Theme dependent | ✅ Mobile-friendly |
| Feed caching | ✅ ETag/Last-Modified | ✅ ETag/Last-Modified | ✅ ETag/Last-Modified |
| Content sanitization | ✅ Bleach-based HTML | ✅ BeautifulSoup | ✅ XSS prevention |
| SSRF protection | ✅ IP blocking | ❌ None | ✅ Private IP blocking |

---

## 2. Configuration

| Aspect | Planet CF | Planet Venus | Rogue Planet |
|--------|-----------|--------------|--------------|
| Config format | YAML + env vars | INI (ConfigParser) | INI |
| Config file | `instance.yaml` | `planet.conf` | `config.ini` |
| Ease of adding feeds | ✅ Admin UI or YAML | ⚠️ Edit config file | ✅ CLI command |
| Feed list location | Database (D1) | Config file sections | SQLite database |
| Theme selection | `THEME` env var or YAML | `theme` config option | CLI flag or config |
| Environment variables | ✅ Full support | ⚠️ Limited | ⚠️ Limited |
| Secrets management | ✅ Cloudflare Secrets | ⚠️ In config file | ⚠️ In config file |
| Hot reload | ✅ Via deploy | ❌ Re-run generator | ❌ Re-run generator |
| Config validation | ✅ At build time | ❌ Runtime errors | ✅ At startup |

### Configuration Examples

**Planet CF** (`config/instance.yaml`):
```yaml
planet:
  id: planet-python
  name: Planet Python
  url: https://planetpython.org

branding:
  theme: default

content:
  days: 7
  group_by_date: true

search:
  enabled: true
```

**Planet Venus** (`planet.conf`):
```ini
[Planet]
name = Planet Python
link = https://planetpython.org
owner_name = Python Community
owner_email = planet@python.org

[http://blog.example.com/feed]
name = Example Blog
```

**Rogue Planet** (`config.ini`):
```ini
[planet]
name = Planet Python
link = https://planetpython.org
owner_name = Python Community
days = 7
```

---

## 3. Deployment & Operations

| Aspect | Planet CF | Planet Venus | Rogue Planet |
|--------|-----------|--------------|--------------|
| Architecture | Serverless (Workers) | Static site generator | Static site generator |
| Runtime | Cloudflare Workers | Python 2.7 | Go (single binary) |
| Hosting | Cloudflare only | Any web server | Any web server |
| Serverless support | ✅ Native | ❌ No | ❌ No |
| Database | D1 (managed SQLite) | None (file-based) | SQLite (local file) |
| Database migrations | ✅ SQL migrations | N/A | N/A |
| Cron/scheduling | ✅ Cloudflare Cron | ⚠️ System cron | ⚠️ System cron |
| Queue processing | ✅ Cloudflare Queues | ❌ Synchronous | ❌ Synchronous |
| Dead letter queue | ✅ Built-in | ❌ No | ❌ No |
| Feed timeout handling | ✅ Per-feed timeout | ⚠️ Global timeout | ✅ Configurable |
| Rate limiting | ✅ Per-feed | ❌ No | ✅ Per-domain |
| Self-hosted option | ❌ Cloudflare required | ✅ Any server | ✅ Any server |
| Cost | Free tier available | Free (self-hosted) | Free (self-hosted) |

### Deployment Commands

**Planet CF**:
```bash
# One-command deployment
python scripts/create_instance.py --id planet-python --name "Planet Python" --deploy

# Or manual
npx wrangler deploy
```

**Planet Venus**:
```bash
# Generate static files
python planet.py planet.conf

# Set up cron
crontab -e
# 0 * * * * cd /path/to/planet && python planet.py planet.conf
```

**Rogue Planet**:
```bash
# Initialize and run
rp init
rp add-feed https://blog.example.com/feed
rp update

# Set up cron
crontab -e
# */30 * * * * cd /path/to/planet && rp update
```

---

## 4. Templates & Theming

| Aspect | Planet CF | Planet Venus | Rogue Planet |
|--------|-----------|--------------|--------------|
| Built-in themes | 6 (default, classic, dark, minimal, planet-python, planet-mozilla) | 0 (examples only) | 5 (Default, Classic, Elegant, Dark, Flexoki) |
| Template language | Jinja2 | Django, htmltmpl, XSLT | Go templates |
| Template inheritance | ✅ Jinja2 extends | ✅ Django extends | ⚠️ Go template actions |
| Custom theme support | ✅ themes/ directory | ✅ theme directories | ✅ Custom templates |
| CSS customization | ✅ Per-theme CSS | ✅ Any CSS | ✅ Per-theme CSS |
| JavaScript support | ✅ Keyboard nav, admin | ✅ Any JS | ⚠️ Minimal |
| Theme fallback | ✅ Falls back to default | ❌ Errors on missing | ❌ Errors on missing |
| Live preview | ✅ `wrangler dev` | ⚠️ Regenerate files | ⚠️ Regenerate files |

### Theme Comparison

| Theme | Planet CF | Planet Venus | Rogue Planet |
|-------|-----------|--------------|--------------|
| Modern/Clean | default | - | Default |
| Classic sidebar | classic | asf (example) | Classic |
| Dark mode | dark | - | Dark |
| Minimal | minimal | - | - |
| Typography-focused | - | - | Flexoki |
| Elegant | - | - | Elegant |

---

## 5. Authentication & Admin

| Feature | Planet CF | Planet Venus | Rogue Planet |
|---------|-----------|--------------|--------------|
| Admin interface | ✅ Web dashboard | ❌ None | ❌ None |
| Feed management UI | ✅ Add/edit/delete feeds | ❌ Edit config | ❌ CLI only |
| User authentication | ✅ OAuth (GitHub, Google, OIDC) | ❌ None | ❌ None |
| Multi-user support | ✅ Admin table | ❌ N/A | ❌ N/A |
| Access control | ✅ Admin whitelist | ❌ None | ❌ None |
| Session management | ✅ Signed cookies (7 days) | ❌ N/A | ❌ N/A |
| Audit logging | ✅ All admin actions | ❌ None | ❌ None |
| Feed health dashboard | ✅ Error counts, DLQ | ❌ None | ⚠️ CLI status |
| Lite mode (no auth) | ✅ Configurable | N/A (no auth by default) | N/A |

---

## 6. Advanced Features

| Feature | Planet CF | Planet Venus | Rogue Planet |
|---------|-----------|--------------|--------------|
| Semantic search | ✅ Vectorize + Workers AI | ❌ No | ❌ No |
| Keyword search | ✅ SQL LIKE | ❌ No | ❌ No |
| Hybrid search | ✅ Keyword + semantic ranked | ❌ No | ❌ No |
| Feed health monitoring | ✅ Consecutive failures tracking | ❌ No | ⚠️ Basic error logging |
| Auto-deactivate bad feeds | ✅ Configurable threshold | ❌ No | ❌ No |
| Dead letter queue | ✅ Failed feeds isolated | ❌ No | ❌ No |
| OPML import | ✅ Via admin UI | ⚠️ Manual conversion | ✅ CLI command |
| OPML export | ✅ /feeds.opml endpoint | ✅ Template-based | ✅ CLI command |
| RSS output | ✅ /feed.rss | ✅ Configurable | ⚠️ Via templates |
| Atom output | ✅ /feed.atom | ✅ Configurable | ⚠️ Via templates |
| JSON Feed output | ❌ No | ❌ No | ❌ No |
| API endpoints | ✅ REST-like admin API | ❌ No | ❌ No |
| Observability | ✅ Structured JSON logging | ⚠️ Basic logging | ⚠️ Basic logging |
| Plugins/filters | ⚠️ Via code | ✅ Input/output filters | ❌ No |
| Feed autodiscovery | ❌ No | ❌ No | ⚠️ Planned for v1.0 |

---

## 7. Developer Experience

| Aspect | Planet CF | Planet Venus | Rogue Planet |
|--------|-----------|--------------|--------------|
| Language | Python 3.12+ | Python 2.7 | Go 1.21+ |
| Documentation | ✅ Comprehensive README + docs/ | ⚠️ Inline docs | ✅ README + THEMES.md |
| Setup complexity | 6/10 (Cloudflare resources) | 4/10 (Python deps) | 3/10 (single binary) |
| Time to first deploy | ~15 minutes | ~10 minutes | ~5 minutes |
| Local development | ✅ `wrangler dev` | ✅ Direct run | ✅ Direct run |
| Test suite | ✅ pytest | ⚠️ Limited | ✅ >75% coverage |
| Type hints | ✅ Full typing | ❌ Python 2 | N/A (Go typed) |
| Linting | ✅ Ruff | ⚠️ Optional | ✅ golangci-lint |
| CI/CD ready | ✅ Wrangler CLI | ⚠️ Custom scripts | ✅ Make targets |
| Extensibility | ⚠️ Fork/modify | ✅ Plugin system | ⚠️ Fork/modify |
| Active maintenance | ✅ Active | ❌ Legacy (Python 2) | ✅ Active |
| Dependencies | Cloudflare platform | feedparser, BeautifulSoup | None (single binary) |

---

## 8. Performance & Scalability

| Aspect | Planet CF | Planet Venus | Rogue Planet |
|--------|-----------|--------------|--------------|
| Edge caching | ✅ 1-hour TTL | ⚠️ Web server config | ⚠️ Web server config |
| Global distribution | ✅ Cloudflare edge | ⚠️ CDN optional | ⚠️ CDN optional |
| Concurrent fetches | ✅ Queue-based parallelism | ⚠️ Sequential | ✅ Configurable (1-50) |
| Connection pooling | ✅ Workers runtime | ❌ No | ✅ HTTP/1.1 keep-alive |
| Memory usage | Low (serverless) | Medium | Low (Go) |
| Bandwidth optimization | ✅ Conditional requests | ✅ Conditional requests | ✅ Conditional requests |
| Large feed handling | ✅ Chunked + timeout | ⚠️ May timeout | ✅ Timeout protection |

---

## Summary

### What Planet CF Does Better

1. **Modern serverless architecture** - No servers to maintain, automatic scaling, global edge distribution
2. **Semantic search** - AI-powered search using Vectorize and Workers AI embeddings
3. **Admin dashboard** - Full web UI for feed management, health monitoring, and audit logs
4. **OAuth authentication** - Secure admin access with GitHub, Google, or custom OIDC
5. **Feed health monitoring** - Automatic tracking of failures, dead letter queue, auto-deactivation
6. **Multi-instance deployment** - First-class CLI tooling for managing multiple planets
7. **Observability** - Structured JSON logging with detailed metrics
8. **Active maintenance** - Modern Python 3.12+ with full type hints

### What Planet Venus Does Better

1. **Self-hosted flexibility** - Run on any server without vendor lock-in
2. **Multiple template engines** - Django templates, htmltmpl, and XSLT options
3. **Plugin architecture** - Input/output filters for custom processing
4. **Simpler setup** - No cloud accounts or API keys required
5. **Full control** - Direct access to all configuration and output files
6. **Legacy compatibility** - Works with very old systems (Python 2.7)

### What Rogue Planet Does Better

1. **Zero dependencies** - Single compiled Go binary, no runtime required
2. **Fastest setup** - 5 minutes to first deployment
3. **Self-hosted simplicity** - Just cron + any web server
4. **Production HTTP handling** - Rate limiting, retries, connection pooling built-in
5. **Strong security defaults** - SSRF protection, XSS prevention, CSP headers
6. **Modern Go codebase** - Fast, memory-efficient, easy to understand
7. **Excellent test coverage** - >75% coverage with real-world feed tests

---

## Recommended Use Cases

### Choose Planet CF when:

- You want a **managed, serverless** solution with minimal operations
- You need **semantic search** capabilities for your aggregated content
- You require **multi-user admin access** with authentication
- You're aggregating feeds for an **organization or community**
- You want **real-time feed health monitoring** and automatic recovery
- You're already using **Cloudflare** for other services
- You need **global edge distribution** for low latency

### Choose Planet Venus when:

- You need to **self-host** without cloud dependencies
- You want **maximum template flexibility** (Django, XSLT, htmltmpl)
- You have **existing Python infrastructure** to integrate with
- You need **plugin-based filtering** of feed content
- You're maintaining a **legacy planet** already using Venus
- You need to run on **very old systems** (Python 2.7 support)

### Choose Rogue Planet when:

- You want the **simplest possible deployment** (single binary + cron)
- You're running on **resource-constrained** systems
- You need **zero external dependencies**
- You want **static HTML** that works anywhere
- You prefer **Go** for its simplicity and performance
- You need **excellent rate limiting** for polite crawling
- You're building a **personal planet** with minimal complexity

---

## Migration Paths

### Venus to Planet CF

1. Export feeds from Venus config to YAML format
2. Create Planet CF instance with `create_instance.py`
3. Import feeds via admin dashboard or SQL
4. Configure theme to match Venus appearance (classic theme)

### Venus to Rogue Planet

1. Create OPML from Venus config feed sections
2. Initialize Rogue Planet: `rp init`
3. Import OPML: `rp import-opml feeds.opml`
4. Set up cron for updates

### Rogue Planet to Planet CF

1. Export OPML: `rp export-opml > feeds.opml`
2. Create Planet CF instance
3. Import OPML via admin dashboard
4. Configure search and authentication

---

## References

- [Planet CF Repository](https://github.com/adewale/planet_cf)
- [Planet Venus Repository](https://github.com/rubys/venus)
- [Rogue Planet Repository](https://github.com/adewale/rogue_planet)
- [Venus Configuration Docs](https://intertwingly.net/code/venus/docs/config.html)
- [Venus Templates Docs](https://www.intertwingly.net/code/venus/docs/templates.html)
