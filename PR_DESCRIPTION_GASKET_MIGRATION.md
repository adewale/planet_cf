# Prepare Planet CF for generic gasket migration

## Summary

This PR keeps Planet CF's product-specific wrapper code in Planet CF and prepares it for migration to the generic `gasket` library. During the gasket audit we found that Planet CF's `src/wrappers.py` mixes two responsibilities:

1. Generic Cloudflare/Pyodide FFI boundary mechanics.
2. Planet-specific row factories, feed helpers, cache purge policy, and deployment assumptions.

Only the first category belongs in gasket.

## Changes in this workspace

- `gasket` now contains only generic Cloudflare Worker abstractions.
- Planet CF's app-specific `src/wrappers.py` remains local instead of being moved into gasket wholesale.
- The local wrapper was made importable in minimal environments by guarding the optional `httpx` import and raising a clear runtime error only when CPython HTTP helpers are used without `httpx`.
- `gasket` now provides generic pieces Planet CF can adopt incrementally:
  - `gasket.ffi.SafeEnv`
  - D1/R2/KV/Queue/AI/Vectorize wrappers
  - generic service, Durable Object, Analytics Engine, Cache, Fetcher, and Assets wrappers
  - `gasket.deploy.validate_ready`
  - `gasket.testing.smoke.SmokeBase`
  - `gasket.compat.probes`

## Follow-up migration plan

- Replace generic conversion helpers in `src/wrappers.py` with imports from `gasket.ffi`.
- Keep row factories and feed/model coercion in Planet CF modules.
- Compose `scripts/validate_deployment_ready.py` from `gasket.deploy.validate_ready` plus Planet-specific template/theme/example checks.
- Compose `scripts/verify_deployment.py` from `gasket.testing.smoke.SmokeBase` plus Planet-specific feed/page assertions.
- Delete generic duplicate code from `src/wrappers.py` once imports are direct.

## Validation

- No GitHub operations were performed.
- Gasket and both wrapper files compile with `python3 -m compileall`.
