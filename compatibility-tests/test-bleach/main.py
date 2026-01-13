# Minimal test: bleach compatibility with Cloudflare Python Workers
#
# Expected behavior when working:
#   GET / returns: {"status": "ok", "sanitized": "safe content"}
#
# Current failure:
#   "Requested Python package(s) that are not supported: bleach"
#
# Root cause:
#   bleach is not in Cloudflare's required_packages.txt
#   However, bleach DOES work in Pyodide (tested via micropip.install)
#
# To fix:
#   Add bleach to required_packages.txt in pyodide-build-scripts
#   bleach and its dependency (webencodings) are both pure Python

from workers import Response, WorkerEntrypoint
import bleach

# Malicious HTML for testing sanitization
TEST_HTML = '<script>alert("xss")</script><p>safe content</p>'


class BleachTest(WorkerEntrypoint):
    async def fetch(self, request):
        # Sanitize the HTML (should strip script tag)
        clean = bleach.clean(TEST_HTML, tags=['p'], strip=True)

        # Return success with sanitized content
        return Response(
            f'{{"status": "ok", "sanitized": "{clean}"}}',
            headers={"Content-Type": "application/json"}
        )
