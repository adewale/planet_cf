#!/bin/bash
# One-command test for bleach compatibility
# Usage: ./test.sh
#
# SUCCESS: Returns {"status": "ok", "sanitized": "safe content"}
# FAILURE: "Requested Python package(s) that are not supported: bleach"

set -e
cd "$(dirname "$0")"

PORT=8788
TIMEOUT=20

echo "🧪 Testing bleach compatibility with Python Workers"
echo "   Port: $PORT"
echo ""

# Clean up any existing process
pkill -f "wrangler.*$PORT" 2>/dev/null || true
sleep 1

# Start wrangler in background, capture output
LOGFILE=$(mktemp)
npx wrangler dev --port $PORT > "$LOGFILE" 2>&1 &
PID=$!

# Wait for server to start or fail
echo "⏳ Starting wrangler dev..."
for i in $(seq 1 $TIMEOUT); do
    sleep 1

    # Check if process died (failure)
    if ! kill -0 $PID 2>/dev/null; then
        echo ""
        echo "❌ FAILED: bleach is not supported"
        echo ""
        echo "Error output:"
        grep -E "(not supported|Error)" "$LOGFILE" | head -5
        rm -f "$LOGFILE"
        exit 1
    fi

    # Check if server is ready (success)
    if curl -s "http://localhost:$PORT/" > /dev/null 2>&1; then
        RESPONSE=$(curl -s "http://localhost:$PORT/")
        kill $PID 2>/dev/null || true
        rm -f "$LOGFILE"

        echo ""
        echo "✅ PASSED: bleach works!"
        echo ""
        echo "Response: $RESPONSE"
        exit 0
    fi

    printf "."
done

# Timeout
kill $PID 2>/dev/null || true
rm -f "$LOGFILE"
echo ""
echo "❌ FAILED: Timeout after ${TIMEOUT}s"
exit 1
