# Test Suite Quality Audit

**Date:** 2026-03-11
**Scope:** 1263 tests (unit + integration), all passing in 3.66s
**Files audited:** 47 test files across `tests/unit/`, `tests/integration/`, `tests/e2e/`, plus `tests/conftest.py` and `tests/fixtures/factories.py`

---

## Executive Summary

The test suite is in good shape overall. Property-based testing is well-adopted, security-critical paths (XSS, SSRF, HMAC signing, SQL injection) have thorough coverage, and the shared mock infrastructure is clean. The issues found are mostly *weak* tests rather than *wrong* ones. No tests that give outright false confidence were identified.

**Key findings (priority-ordered):**

1. **WRONG: Overly permissive status assertions** -- 12 tests accept multiple status codes, masking bugs
2. **WRONG: Negation-only assertions in OAuth callback tests** -- 5 tests only assert `status != 302`
3. **WEAK: Source-code-inspection tests are fragile** -- 8+ tests grep Python source for keywords instead of exercising behavior
4. **FLAKY RISK: `time.sleep()` in Timer tests and un-frozen `time.time()` calls**
5. **WEAK: "Never crashes" tests without meaningful output checks**

---

## 1. Assertion Quality

### WRONG: Overly Permissive Status Code Assertions

**Severity: High** -- These tests accept multiple possible statuses, which means a regression that changes the behavior (e.g., from 200 to 400) would pass silently.

| File | Line | Assertion | Problem |
|------|------|-----------|---------|
| `test_admin_routing.py` | 93 | `status in (200, 400)` | POST /admin/feeds -- should this be 200 or 400? Pick one. |
| `test_admin_routing.py` | 111 | `status in (200, 302)` | DELETE /admin/feeds/{id} -- fundamentally different behaviors |
| `test_admin_routing.py` | 127 | `status in (200, 400)` | POST /admin/import-opml with no file |
| `test_admin_routing.py` | 662 | `status in (200, 404)` | Retry nonexistent feed |
| `test_admin_routing.py` | 691 | `status in (200, 302, 400, 500)` | Accepts *any* non-404 status |
| `test_validate_and_add_feed.py` | 305, 318, 331, 351 | Multiple `status in (...)` | Same pattern |
| `test_import_opml.py` | 151, 221 | `status in (200, 400)` | Same pattern |

**Recommendation:** Each test should assert one expected status code. If the code legitimately returns different codes depending on context, write separate tests for each path.

### WRONG: Negation-Only Assertions in OAuth Callback Tests

**Severity: High** -- `test_github_callback.py` has 5 tests that only assert `response.status != 302`. This means any non-redirect (200, 400, 401, 403, 500, etc.) would pass, even if it's the wrong error handling.

```
tests/unit/test_github_callback.py:178:  assert response.status != 302  # missing_state
tests/unit/test_github_callback.py:209:  assert response.status != 302  # replay_attack
tests/unit/test_github_callback.py:239:  assert response.status != 302  # github_api_error
tests/unit/test_github_callback.py:271:  assert response.status != 302  # non_admin_user
tests/unit/test_github_callback.py:294:  assert response.status != 302  # exception_500
```

**Recommendation:** Assert specific status codes. For example, `test_non_admin_user_returns_access_denied` should assert `response.status == 403`. The test for missing state should assert 400. The test for exceptions should assert 500.

### WEAK: Tests That Only Check "No Exception Thrown"

Several tests verify a function "doesn't crash" but don't assert anything about correctness:

- `test_observability.py::TestTimer::test_measures_elapsed_time` -- uses `time.sleep(0.01)` and asserts `elapsed_ms >= 10`, which is weak (see Flaky section)
- `test_admin_routing.py::test_response_with_string_body_tracks_size` -- calls `worker.fetch(request)` and only asserts `status == 200`, no verification of size tracking
- `test_queue_processing.py::test_empty_batch_is_noop` -- calls `await worker.queue(batch)` with no assertions at all
- Property tests like `test_feed_row_from_js_never_crashes` and `test_arbitrary_strings_never_crash` are intentionally "no exception" tests. These are fine as a safety net but should be complemented with tests that check output correctness (which they are, in other test classes).

### WEAK: Assertion on Malformed XML Test

`test_feed_parsing.py::test_malformed_xml_still_extracts_title` (line 234):
```python
assert title == "Lenient Parser Blog" or title is None
```
This accepts either outcome, making it useless as a regression test. It documents behavior rather than verifying it.

---

## 2. Test Isolation

### Good: Factory Counters Reset Per Test

The `reset_factories` autouse fixture in `conftest.py` (line 637) resets `FeedFactory`, `EntryFactory`, and `FeedJobFactory` counters before each test. This prevents test ordering from affecting auto-generated IDs.

### Good: No Shared Mutable State Between Test Classes

Each test creates its own worker, env, and DB instances. The mock classes (`MockD1`, `MockQueue`, `MockVectorize`) are instantiated per test, not at module level.

### Good: MockRequest Isolation

`MockRequest` in `conftest.py` is well-designed -- it creates a fresh `MagicMock` for headers in each `__init__`, avoiding shared mock state.

### Potential Concern: Module-Level `_sanitizer`

`test_properties.py` line 454 creates a module-level `BleachSanitizer` instance:
```python
_sanitizer = BleachSanitizer()
```
This is shared across all `TestSanitizationProperties` tests. Since `BleachSanitizer.clean()` is a pure function with no mutable state, this is safe in practice. But it departs from the isolation pattern used elsewhere.

---

## 3. Flaky Patterns

### FLAKY RISK: `time.sleep()` in Timer Tests

`test_observability.py` lines 429-445:
```python
def test_measures_elapsed_time(self):
    with Timer() as t:
        time.sleep(0.01)  # 10ms
    assert t.elapsed_ms >= 10
    assert t.elapsed_ms < 100  # Should not take 100ms
```

This test uses real `time.sleep()` and asserts on real elapsed time. On a heavily loaded CI machine, `sleep(0.01)` could take longer than 100ms. The upper bound of `< 100` provides some slack, but this is inherently environment-dependent.

**Recommendation:** Increase the upper bound to 500ms, or mock `time.perf_counter` to test the Timer logic deterministically.

### FLAKY RISK: Un-Frozen `time.time()` in Session/Auth Tests

Many tests in `test_auth.py` and `test_session.py` use `int(time.time()) + 3600` without `freeze_time`. Most are safe because they set expiry far in the future (1 hour). However:

- `test_auth.py::test_custom_ttl` (line 182-186) asserts:
  ```python
  assert payload["exp"] <= int(time.time()) + 61
  assert payload["exp"] >= int(time.time()) + 59
  ```
  This could fail if the two `time.time()` calls span a second boundary. The window is 2 seconds, so failure is unlikely but theoretically possible.

- `test_auth.py::test_expiry_is_in_the_future` (line 172) asserts `payload["exp"] > time.time()` without freezing time -- safe with 1h TTL but inconsistent with the `@freeze_time` pattern used elsewhere.

- `test_session.py` lines 62-68 and 76-81 -- create expired payloads with `time.time() + 3600` but don't freeze time. These work because 3600s of headroom is ample.

**Recommendation:** Consistently use `@freeze_time` for all time-dependent tests, as already done in `test_models.py`. This eliminates any theoretical race.

### FLAKY RISK: Probabilistic Sampling Tests

`test_observability.py::test_samples_fast_successful_operations` (line 326-332):
```python
results = [should_sample(event, sample_rate=0.5) for _ in range(1000)]
hit_rate = sum(results) / len(results)
assert 0.4 < hit_rate < 0.6
```

With 1000 samples at p=0.5, the probability of the hit rate falling outside [0.4, 0.6] is astronomically small (~3.1e-10 by normal approximation). This is acceptable -- it won't be flaky in practice.

---

## 4. Property-Based Testing

### Already Excellent Coverage

The `test_properties.py` file (971 lines) is one of the strongest parts of this test suite. It covers:

- **Serialization roundtrips:** FeedJob, Session (JSON roundtrip)
- **Auth cookie security:** create/verify roundtrip, tampered payloads, wrong secrets, expired sessions
- **SSRF validation:** All RFC 1918 ranges, cloud metadata, internal domains, arbitrary input never crashes
- **XSS sanitization:** script tags, event handlers, javascript URLs, dangerous tags, idempotency
- **SQL injection prevention:** SearchQueryBuilder with special chars, placeholder/param count invariants
- **Route dispatching:** Arbitrary paths, method filtering, param extraction
- **Cookie parsing:** Arbitrary headers, embedded semicolons, whitespace handling
- **FFI boundary:** `_to_py_safe` idempotency, `feed_row_from_js` never crashes

### Opportunities for Additional Property Tests

1. **`xml_escape` roundtrip:** The function escapes `&`, `<`, `>`. A property test could verify that `xml_escape(text)` never contains unescaped `<` or `>` characters, and that decoding the escape produces the original text.

2. **`normalize_entry_content` preservation:** Property: for any content and title where the title does not appear in an h1 tag, `normalize_entry_content(content, title) == content`.

3. **`validate_feed_id` domain:** Property: for any string, `validate_feed_id(s)` is either `None` or a positive `int`.

4. **`truncate_error` length invariant:** Property: `len(truncate_error(msg, max_length=n)) <= n` for all `msg` and `n > 3`.

5. **`EntryContentProcessor.generate_guid` determinism:** Already tested deterministically, but a property test over random entry dicts would strengthen it.

These are low priority -- the existing property tests cover the highest-risk areas.

---

## 5. Missing Negative Tests

### Good Coverage Already Present

- **Auth:** Tampered payload, tampered signature, wrong secret, expired session, missing cookie, empty cookie, None cookie -- all tested
- **SSRF:** Comprehensive parametrized tests for localhost, private IPs, cloud metadata, non-HTTP schemes, malformed URLs, IPv6 private addresses
- **XSS:** 12+ parametrized attack vectors, null bytes, CSS expressions, nested scripts, SVG payloads
- **SQL injection:** SQL comments, UNION SELECT, stacked queries, backtick identifiers, null bytes, OR 1=1
- **OPML parsing:** Malformed XML, XXE attack, empty OPML, feeds exceeding limit

### Gaps

1. **`parse_opml` with extremely large input:** No test for a multi-megabyte OPML file. The code has a `MAX_OPML_FEEDS` limit but no size limit on the raw XML. This is a DoS vector.

2. **`create_session_cookie` with negative TTL:** What happens if `ttl_seconds` is negative? Currently untested.

3. **Queue processing with malformed message body:** `test_invalid_message_body_acked` tests `body=None` but not `body="not a dict"` or `body={"missing": "required_fields"}`. The test for missing `feed_id`/`url` would verify that partial messages are handled.

4. **Admin operations with revoked session (race condition):** No test for the scenario where a session is valid but the admin has been deactivated between the session check and the admin lookup. This is a real-world edge case.

5. **Content processor with adversarial input:** `EntryContentProcessor` is tested with normal feedparser output but not with deeply nested HTML, million-character content strings, or entries with contradictory fields.

---

## 6. Test Naming and Organization

### Strengths

- **Consistent docstrings:** Nearly every test has a descriptive docstring explaining what is being verified
- **Logical grouping:** Tests are organized into well-named classes (`TestParseOpml`, `TestVerifySignedCookie`, `TestBleachSanitizer`)
- **Clear naming convention:** `test_<what>_<behavior>` pattern is used consistently (e.g., `test_rejects_tampered_payload`, `test_blocks_localhost`)

### Weaknesses

1. **`test_remaining_mitigations.py` -- misleading name and fragile approach:** This file contains 8+ test classes that inspect Python source code using `inspect.getsource()` and regex matching:
   ```python
   source = inspect.getsource(__import__("main").Default._record_feed_error)
   assert "-> bool" in source
   assert "return True" in source
   ```
   These tests verify that strings exist in source code, not that behavior is correct. They will break on any refactoring (rename a variable, reformat a line) while providing no confidence that the actual logic works. Source-code-inspection is the weakest form of testing.

   **Recommendation:** Replace all source-inspection tests with behavioral tests. For example, instead of checking that `_record_feed_error` source contains "return True", call the function with a feed that exceeds the deactivation threshold and assert it returns `True`.

2. **`test_main_helpers.py` duplicates `test_utils.py`:** Both files test `truncate_error`, `log_op`, `_is_js_undefined`, `_safe_str`, etc. The `test_main_helpers.py` file imports from `src.main` (private re-exports) while `test_utils.py` imports from `src.utils` and `src.wrappers` directly. This creates confusion about which is canonical.

   **Recommendation:** Delete the duplicated tests in `test_main_helpers.py` and keep only `test_utils.py` and `test_safe_wrappers.py` as the canonical sources.

3. **`test_feed_parsing.py` tests feedparser, not project code:** These tests parse RSS/Atom XML through `feedparser` and assert on feedparser's output. They don't test any `src/` code -- they test a third-party library's behavior. While useful as documentation of feedparser's behavior, they inflate the test count without testing the project.

---

## 7. Mock Infrastructure Quality

The shared mocks in `tests/conftest.py` are well-designed:

- **`MockD1`** with `_filter_results()` for `is_active` filtering -- simulates real D1 WHERE clause behavior
- **`MockD1` strict mode** -- validates SQL column names against a schema, catching column-name bugs at test time
- **`TrackingD1` / `TrackingD1Statement`** -- enables assertions on SQL queries and bound parameters
- **`MockRequest`** -- supports both simple and full modes (cookies, form data, JSON)
- **`make_authenticated_worker()`** -- clean factory for creating authenticated test workers
- **`create_signed_session()`** -- generates valid session cookies matching production auth code

### One Concern: Duplicate Mocks

`test_safe_wrappers.py`, `test_github_callback.py`, `test_queue_processing.py`, and `test_config.py` each define their own `MockD1`, `MockD1Statement`, `MockEnv` classes instead of using the shared ones from `conftest.py`. This is documented in MEMORY.md as intentional (specialized local mocks), but it means changes to the real D1 interface could be caught by conftest mocks but missed by local mocks (or vice versa).

---

## Summary of Recommendations

### Priority 1 (Wrong tests -- fix these first)
1. Replace all `status in (200, 302, 400, 500)` assertions with specific expected status codes
2. Replace `status != 302` assertions in OAuth callback tests with specific error codes (400, 403, 500)

### Priority 2 (Fragile tests -- fix before next refactor)
3. Replace source-code-inspection tests in `test_remaining_mitigations.py` with behavioral tests
4. Deduplicate `test_main_helpers.py` overlap with `test_utils.py`

### Priority 3 (Flaky risks -- fix for CI reliability)
5. Use `@freeze_time` consistently for all time-dependent tests (especially `test_auth.py::test_custom_ttl`)
6. Increase Timer test upper bound or mock `time.perf_counter`

### Priority 4 (Coverage gaps -- add when convenient)
7. Add negative tests for queue processing with malformed message bodies
8. Add DoS-relevant test for `parse_opml` with large input
9. Add property tests for `xml_escape`, `validate_feed_id`, `truncate_error`
