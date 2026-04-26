# Incrementally migrate Planet CF wrappers to CFBoundary

## Summary

This PR starts the safe migration from Planet CF's local Cloudflare/Pyodide boundary helpers to [`cfboundary`](https://github.com/adewale/cfboundary), while preserving the existing `src/wrappers.py` public API.

Planet CF still owns app-specific behavior such as:

- feed/article row conversion
- auth/session semantics
- search and Vectorize application contracts
- observability and logging
- local `HttpResponse` compatibility
- app-specific binding names and deployment topology

CFBoundary owns reusable Cloudflare Python Workers boundary mechanics.

## Changes

- Adds `cfboundary @ git+https://github.com/adewale/cfboundary@v0.1.0` as a dependency.
- Delegates generic real-runtime/fallback conversion helpers through CFBoundary where safe:
  - Python → JavaScript value conversion
  - JavaScript/Pyodide → Python value conversion
  - D1 `None` → JavaScript `null` conversion when running in real CFBoundary/Pyodide mode
- Keeps Planet CF's wrapper API unchanged.
- Keeps existing Pyodide fake tests working by retaining Planet CF's monkeypatchable local runtime globals.

## Why this shape

A thin replacement would be too risky because Planet CF's wrapper layer includes application-specific compatibility, data-shaping, and observability. This PR migrates generic internals first behind the stable local `wrappers.py` interface.

## Validation

```bash
uv lock
uv run --all-extras pytest tests/unit/test_wrappers_ffi.py tests/unit/test_safe_wrappers.py -q
```

Full-suite validation should also be run before merge:

```bash
uv run --all-extras pytest -q
```
