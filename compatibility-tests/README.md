# Python Workers Package Compatibility Tests

Minimal reproducible tests for package compatibility issues with Cloudflare Python Workers.

## Quick Test

```bash
# Test feedparser (currently fails)
cd test-feedparser && npx wrangler dev --port 8787

# Test bleach (currently fails)
cd test-bleach && npx wrangler dev --port 8788
```

## Expected Results

### When Fixed

```bash
$ curl http://localhost:8787/
{"status": "ok", "entries": 1, "title": "Example"}

$ curl http://localhost:8788/
{"status": "ok", "sanitized": "safe content"}
```

### Current Failures

#### feedparser
```
Requested Python package(s) that are not supported: feedparser
```

**Root Cause**: feedparser depends on `sgmllib3k`, which only has a source tarball on PyPI (no wheel). Pyodide requires wheel files.

**Fix Required**:
1. Build `sgmllib3k` as a wheel for Pyodide
2. Add `feedparser` to `required_packages.txt`

#### bleach
```
Requested Python package(s) that are not supported: bleach
```

**Root Cause**: bleach is not in Cloudflare's `required_packages.txt`, but it **does work in Pyodide** (verified via `micropip.install('bleach')`).

**Fix Required**:
1. Add `bleach` to `required_packages.txt` (bleach and webencodings are pure Python)

## Verification Script

```bash
#!/bin/bash
# Run from compatibility-tests directory

echo "=== Testing feedparser ==="
cd test-feedparser
npx wrangler dev --port 8787 &
PID1=$!
sleep 10
RESULT1=$(curl -s http://localhost:8787/ 2>&1)
kill $PID1 2>/dev/null

if echo "$RESULT1" | grep -q '"status": "ok"'; then
    echo "✅ feedparser: PASS"
else
    echo "❌ feedparser: FAIL"
    echo "   $RESULT1"
fi

echo ""
echo "=== Testing bleach ==="
cd ../test-bleach
npx wrangler dev --port 8788 &
PID2=$!
sleep 10
RESULT2=$(curl -s http://localhost:8788/ 2>&1)
kill $PID2 2>/dev/null

if echo "$RESULT2" | grep -q '"status": "ok"'; then
    echo "✅ bleach: PASS"
else
    echo "❌ bleach: FAIL"
    echo "   $RESULT2"
fi
```

## Package Analysis

| Package | Wheel Type | Dependencies | Pyodide Status | CF Status |
|---------|-----------|--------------|----------------|-----------|
| feedparser | `py3-none-any` | sgmllib3k | ❌ sgmllib3k has no wheel | ❌ Not in list |
| sgmllib3k | **No wheel** | None | ❌ No wheel available | ❌ Not in list |
| bleach | `py3-none-any` | webencodings | ✅ Works via micropip | ❌ Not in list |
| webencodings | `py2.py3-none-any` | None | ✅ Works | ✅ In Pyodide |

## Environment

- wrangler: 4.58.0+
- Python Workers compatibility flag: `python_workers`
- Tested: 2026-01-13
