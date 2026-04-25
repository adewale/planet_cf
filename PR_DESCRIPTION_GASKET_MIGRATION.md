# Prepare Planet CF for generic gasket migration

## Summary

This PR keeps Planet CF's product-specific wrapper code in Planet CF and prepares it for migration to the generic `gasket` library.

The key migration lesson is that Planet CF's `src/wrappers.py` combines reusable FFI boundary mechanics with application semantics. Only generic mechanics should move to gasket. Row factories, feed helpers, model coercion, cache purge policy, template/theme checks, and deployment topology should remain in Planet CF.

## Changes in this workspace

- `gasket` now contains only generic Cloudflare Worker abstractions.
- Planet CF's app-specific `src/wrappers.py` remains local instead of being moved into gasket wholesale.
- `gasket` now documents the app-adapter migration pattern and compatibility test matrix.
- `gasket` provides generic pieces Planet CF can adopt incrementally:
  - `gasket.ffi.SafeEnv`
  - D1/R2/KV/Queue/AI/Vectorize wrappers
  - generic service, Durable Object, Analytics Engine, Cache, Fetcher, and Assets wrappers
  - `gasket.deploy.validate_ready`
  - `gasket.testing.smoke.SmokeBase`
  - `gasket.compat.probes`

## Follow-up migration plan

1. Replace generic conversion helpers in `src/wrappers.py` with imports from `gasket.ffi`.
2. Keep row factories and feed/model coercion in Planet CF modules.
3. Compose `scripts/validate_deployment_ready.py` from `gasket.deploy.validate_ready` plus Planet-specific template/theme/example checks.
4. Compose `scripts/verify_deployment.py` from `gasket.testing.smoke.SmokeBase` plus Planet-specific feed/page assertions.
5. Run the full Planet CF suite after every increment.
6. Delete generic duplicate code from `src/wrappers.py` only after direct imports are in place and tests are green.

## Validation

- Full local Planet CF test suite passes with the app-local wrapper retained:
  - `1426 passed, 107 skipped`
- No GitHub operations were performed.
