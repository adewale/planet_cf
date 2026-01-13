# Minimal test: feedparser compatibility with Cloudflare Python Workers
#
# Expected behavior when working:
#   GET / returns: {"status": "ok", "entries": 1, "title": "Example"}
#
# Current failure:
#   "Requested Python package(s) that are not supported: feedparser"
#
# Root cause:
#   feedparser depends on sgmllib3k, which has no wheel on PyPI (only .tar.gz)
#   Pyodide/micropip requires wheel files to install packages
#
# To fix:
#   1. Build sgmllib3k as a wheel and include in Pyodide
#   2. Add feedparser to required_packages.txt

from workers import Response, WorkerEntrypoint
import feedparser

# Minimal valid RSS feed for testing
TEST_RSS = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Example</title>
    <item><title>Test Entry</title></item>
  </channel>
</rss>"""


class FeedparserTest(WorkerEntrypoint):
    async def fetch(self, request):
        # Parse the test feed
        feed = feedparser.parse(TEST_RSS)

        # Return success with parsed data
        return Response(
            f'{{"status": "ok", "entries": {len(feed.entries)}, "title": "{feed.feed.title}"}}',
            headers={"Content-Type": "application/json"}
        )
