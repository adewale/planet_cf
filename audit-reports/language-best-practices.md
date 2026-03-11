# Language Best Practices Audit

**Date:** 2026-03-11
**Scope:** `src/` (Python), `assets/static/` (JavaScript), `scripts/` (Shell)

---

## Overall Assessment

The codebase is well-structured and follows most modern best practices. The Python source uses dataclasses, type hints, structured logging, and proper separation of concerns. The identified issues below are prioritized by impact.

---

## Actionable Findings (genuine anti-patterns or maintenance risks)

### Python

#### P1. `admin_context.py` calls `Timer.__enter__` / `__exit__` directly instead of using `with`

**File:** `/Users/ade/Documents/projects/planet_cf/src/admin_context.py`, lines 208-215

```python
timer.__enter__()
try:
    yield ctx
except Exception as e:
    ...
    raise
finally:
    timer.__exit__(None, None, None)
```

**Problem:** Calling dunder methods directly is fragile and un-idiomatic. If `__enter__` raises, `__exit__` is still called in the `finally` block with incorrect state. The `with` statement handles this correctly by only calling `__exit__` if `__enter__` succeeded.

**Fix:** Since this is inside an `@asynccontextmanager` (which also needs `try`/`yield`/`finally`), the simplest approach is to call `timer.start_time = time.perf_counter()` directly and compute elapsed in `finally`, or restructure to avoid nesting the context manager call inside another generator. The `Timer` class is simple enough that direct attribute access (`timer.start_time = time.perf_counter()`) in the outer generator would be clearer than faking a `with` block.

---

#### P2. `D1Result` class defined inside a method body (re-created on every call)

**File:** `/Users/ade/Documents/projects/planet_cf/src/wrappers.py`, lines 289-292

```python
async def all(self) -> Any:
    ...
    class D1Result:
        def __init__(self, results, success):
            ...
```

**Problem:** A new class object is created on every `await stmt.all()` call. This is unnecessary overhead and makes the type invisible to external code. It also makes `isinstance()` checks unreliable across calls.

**Fix:** Move `D1Result` to module level (or make it a `dataclass`/`NamedTuple`).

---

#### P3. Bare `dict` without type parameters in public API signatures

**Files:**
- `/Users/ade/Documents/projects/planet_cf/src/utils.py`, line 217: `def json_response(data: dict, ...)`
- `/Users/ade/Documents/projects/planet_cf/src/models.py`, line 47: `def to_dict(self) -> dict:`
- `/Users/ade/Documents/projects/planet_cf/src/models.py`, line 52: `def from_dict(cls, data: dict)`
- `/Users/ade/Documents/projects/planet_cf/src/wrappers.py`, line 393: `def json(self) -> dict:`

**Problem:** Bare `dict` without type parameters loses information that `dict[str, Any]` would provide. Tools like mypy/pyright/ty treat `dict` as `dict[Unknown, Unknown]`, which can mask type errors.

**Fix:** Change to `dict[str, Any]` (or more specific types where possible).

---

#### P4. `HttpResponse` is a plain class; should be a dataclass or frozen dataclass

**File:** `/Users/ade/Documents/projects/planet_cf/src/wrappers.py`, lines 373-397

The rest of the codebase consistently uses `@dataclass` for data-carrying classes (`OAuthError`, `TokenExchangeResult`, `ProcessedEntry`, etc.), but `HttpResponse` uses a manual `__init__`. This inconsistency makes it harder to serialize/compare and breaks the pattern.

**Fix:** Convert to `@dataclass(slots=True)` (or `frozen=True` if immutability is desired).

---

#### P5. Broad `except Exception:` without logging in `wrappers.py`

**File:** `/Users/ade/Documents/projects/planet_cf/src/wrappers.py`, lines 156, 195, 223

Three `except Exception:` blocks silently swallow errors:
- `_to_py_safe` line 156: returns `None`
- `_extract_form_value` line 195: returns `None`
- `_to_py_list` line 223: falls through to `list(js_array)`

**Problem:** These are boundary-layer functions where unexpected errors during JsProxy conversion could indicate data corruption or API changes. Silently swallowing them makes debugging production issues very difficult.

**Mitigating factor:** These are in the Pyodide boundary layer where the exception types are genuinely unpredictable (JsProxy can throw JavaScript errors). However, at minimum a `_log_op("conversion_error", ...)` would aid debugging.

**Fix:** Add structured logging (`_log_op`) in each catch block, even if the return value stays the same.

---

#### P6. Repeated `admin: dict[str, Any]` parameter across many methods instead of a typed model

**File:** `/Users/ade/Documents/projects/planet_cf/src/main.py` (lines 2682, 2797, 2899, 3006, 3124, 3149, 3227, 3375)

Over 8 methods accept `admin: dict[str, Any]` and access `.get("github_username")`, `.get("id")`, etc. This is a classic case where a `TypedDict` or `dataclass` would catch key typos at type-check time.

**Problem:** A typo like `admin["github_user"]` would silently return `None` at runtime. The `AdminRow` TypedDict exists in `models.py` but is not used for these parameters.

**Fix:** Use `AdminRow` from `models.py` (or a new dataclass) as the parameter type for these methods.

---

#### P7. `_get_deployment_context` returns `dict` instead of a typed structure

**File:** `/Users/ade/Documents/projects/planet_cf/src/main.py`, line 329

Returns `dict` with `worker_version` and `deployment_environment` keys. Used heavily (passed to `admin_action_context`, `create_admin_event`, and all event dataclasses). A `TypedDict` or `NamedTuple` would make the contract explicit.

---

### JavaScript

#### J1. All `var` declarations in `admin.js` should be `const` or `let`

**File:** `/Users/ade/Documents/projects/planet_cf/assets/static/admin.js`

20 instances of `var` across the file. `var` has function scope (not block scope) and is hoisted, which can cause subtle bugs with closures in loops.

**Problem:** Inside `forEach` callbacks, `var` declarations leak to the enclosing function scope. For example, multiple `var titleDiv` declarations in the click handler (lines 166, 171, 176) would share the same variable if they were in the same function (they happen to be in separate `if` blocks, so it works here, but it is still a maintenance trap).

**Fix:** Replace all `var` with `const` (or `let` where reassignment is needed). This is a safe mechanical transformation since all uses are within function bodies.

---

#### J2. Missing error handling on most `fetch()` promise chains

**File:** `/Users/ade/Documents/projects/planet_cf/assets/static/admin.js`

`saveFeedTitle()` (line 14), `loadDLQ()` (line 49), `loadAuditLog()` (line 70), and the feed toggle handler (line 152) all have `.then()` chains with no `.catch()`. Only `rebuildSearchIndex()` has error handling.

**Problem:** If any fetch fails (network error, 500, etc.), the error is silently swallowed and the UI gives no feedback. This is a real user-facing bug: toggling a feed or editing a title could fail with no visible indication.

**Fix:** Add `.catch()` handlers that show user feedback (e.g., flash message or console error).

---

#### J3. No `'use strict'` directive in `admin.js`

**File:** `/Users/ade/Documents/projects/planet_cf/assets/static/admin.js`

The file is not in strict mode. (`keyboard-nav.js` uses an IIFE which does not add strict mode either, but its use of `const`/`let` means it already behaves as if in strict mode in modern engines.)

**Problem:** Without strict mode, silent errors like assigning to undeclared variables, duplicate parameter names, and `this` coercion can occur.

**Fix:** Add `'use strict';` at the top, or convert to an IIFE/module pattern.

---

### Shell

#### S1. Scripts use `set -e` but not `set -euo pipefail`

**Files:**
- `/Users/ade/Documents/projects/planet_cf/scripts/deploy_instance.sh`, line 23
- `/Users/ade/Documents/projects/planet_cf/scripts/setup_test_planet.sh`, line 20

**Problem:**
- Missing `-u` (nounset): Unset variable references silently expand to empty strings instead of failing. Example: if `$INSTANCE_ID` were accidentally unset, the script would proceed with empty paths.
- Missing `-o pipefail`: In pipelines like `npx wrangler d1 info "$DB_NAME" 2>&1 | extract_uuid`, if `wrangler` fails but `extract_uuid` succeeds, the pipeline exits 0 and the error is hidden.

**Fix:** Change to `set -euo pipefail` at the top of each script.

---

#### S2. Unquoted variable in `grep -oP` pattern

**File:** `/Users/ade/Documents/projects/planet_cf/scripts/setup_test_planet.sh`, line 138

```bash
WORKER_URL=$(npx wrangler deployments list --config "$CONFIG_FILE" 2>&1 | grep -oP 'https://[^\s]+\.workers\.dev' | head -1 || true)
```

**Problem:** `grep -oP` uses Perl regex which is not available on macOS (which ships BSD grep). This command will fail silently (due to `|| true`) on macOS, leaving `WORKER_URL` empty and skipping the reindex step with no clear error.

**Fix:** Use `grep -oE 'https://[^ ]+\.workers\.dev'` (extended regex, portable) -- this is already done correctly in `deploy_instance.sh` line 369 for the same pattern.

---

## Informational (style preferences, not bugs)

These are noted for awareness but do not require action.

### Python

- **`import json` inside method body** (`wrappers.py:395`): Deferred import in `HttpResponse.json()`. This is intentional to avoid import overhead when `json()` is not called, though the savings are negligible for a stdlib module.

- **Aliased imports with underscore prefix** (`main.py` lines 91-135): Functions like `_html_response`, `_log_op` etc. are imported with underscore prefixes from `utils`. This is unconventional but serves to distinguish Worker method names from imported utility functions, preventing name collisions with the `Default` class methods.

- **`LogKwargs = Any` type alias** (`utils.py:21`): Using `Any` as a type alias defeats the purpose of type checking. A more precise type like `str | int | float | bool | None` would be better, but since `log_op` ultimately passes through `json.dumps`, `Any` is pragmatically correct.

- **`f"PRAGMA table_info({table_name})"` with `# noqa: S608`** (`main.py:540`): The f-string in SQL is flagged as a potential injection risk. The suppression is justified because `table_name` comes from the hardcoded `_EXPECTED_COLUMNS` dict, not user input.

### JavaScript

- **`.then()` chains instead of `async/await`** in `admin.js`: All fetch calls use `.then()` chains. `async/await` would be more readable, but since the file targets broad browser compatibility (no transpilation), `.then()` is a reasonable choice.

- **`escapeHtml()` using DOM** (`admin.js:88-92`): Creating a `div` element to escape HTML is an accepted browser pattern, though it is slightly slower than a regex-based approach.

### Shell

- **`echo -e` for colored output**: This is bash-specific and not POSIX, but since the shebang is `#!/bin/bash` this is fine.

---

## Summary of Required Actions

| ID | Severity | Language | Description |
|----|----------|----------|-------------|
| P1 | Medium | Python | Direct `__enter__`/`__exit__` calls in `admin_context.py` |
| P2 | Low | Python | `D1Result` class defined inside method body |
| P3 | Low | Python | Bare `dict` type hints in public APIs |
| P4 | Low | Python | `HttpResponse` not a dataclass (inconsistency) |
| P5 | Medium | Python | Silent `except Exception:` in boundary layer |
| P6 | Medium | Python | Untyped `admin: dict[str, Any]` across 8+ methods |
| P7 | Low | Python | `_get_deployment_context` returns untyped dict |
| J1 | Medium | JS | `var` instead of `const`/`let` throughout `admin.js` |
| J2 | High | JS | Missing `.catch()` on fetch calls (silent failures) |
| J3 | Low | JS | No `'use strict'` in `admin.js` |
| S1 | Medium | Shell | Missing `-uo pipefail` in shell scripts |
| S2 | Medium | Shell | Non-portable `grep -oP` on macOS |
