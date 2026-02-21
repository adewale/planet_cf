#!/usr/bin/env python3
"""
Verify that deployed Planet sites are working correctly.

This script performs post-deployment smoke tests to catch issues like:
- HTTP 500 errors from template rendering bugs
- Missing CSS/assets
- Broken layouts
- Missing required HTML elements
- Broken feed endpoints (RSS, Atom, OPML, RSS 1.0)
- Missing titles page or search functionality

Feed verification is discovery-based: the script parses the homepage HTML
to find which feeds/pages the instance advertises, then verifies each one.
RSS 2.0 and Atom are always checked as a fallback.

Usage:
    # Verify a single site
    python scripts/verify_deployment.py https://planetcf.adewale-883.workers.dev/

    # Verify multiple sites
    python scripts/verify_deployment.py URL1 URL2 URL3

    # Verify all configured examples (reads from wrangler configs)
    python scripts/verify_deployment.py --all

Exit codes:
    0 - All sites passed verification
    1 - One or more sites failed verification
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# Feed types and their expected content signatures
FEED_VALIDATORS: dict[str, tuple[str, str]] = {
    "atom": ("Atom", "<feed"),
    "rss": ("RSS 2.0", "<rss"),
    "rss10": ("RSS 1.0", "rdf:RDF"),
    "opml": ("OPML", "<opml"),
}


def fetch_url(url: str, timeout: int = 30) -> tuple[int, str, dict]:
    """Fetch a URL and return (status_code, body, headers)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PlanetCF-Verification/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            headers = dict(response.headers)
            return response.status, body, headers
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return e.code, body, dict(e.headers) if e.headers else {}
    except urllib.error.URLError as e:
        return 0, str(e.reason), {}
    except Exception as e:
        return 0, str(e), {}


def discover_endpoints(html: str) -> dict[str, str]:
    """Discover feed and page endpoints from homepage HTML.

    Parses <link rel="alternate"> tags, sidebar links, and page structure
    to find which feeds/pages the instance advertises.

    Returns:
        Dict mapping endpoint type to path, e.g.:
        {"atom": "/feed.atom", "rss": "/feed.rss", "opml": "/feeds.opml"}
    """
    endpoints: dict[str, str] = {}

    # Discover <link rel="alternate"> feeds (in <head>)
    # Match both orderings: rel before href, and href before rel
    for match in re.finditer(
        r"<link[^>]*(?:rel=[\"']alternate[\"'])[^>]*href=[\"']([^\"']+)[\"'][^>]*>",
        html,
        re.IGNORECASE,
    ):
        href = match.group(1)
        tag = match.group(0)
        if "atom+xml" in tag:
            endpoints["atom"] = href
        elif "rss+xml" in tag:
            endpoints["rss"] = href

    # Discover OPML link
    opml_match = re.search(r'href=["\']([^"\']*opml[^"\']*)["\']', html, re.IGNORECASE)
    if opml_match:
        endpoints["opml"] = opml_match.group(1)

    # Discover RSS 1.0 link (planet-mozilla style)
    if 'href="/feed.rss10"' in html:
        endpoints["rss10"] = "/feed.rss10"

    # Discover titles page
    if 'href="/titles"' in html or 'href="/titles.html"' in html:
        endpoints["titles"] = "/titles"

    # Discover search (present in full mode only)
    if 'action="/search"' in html or 'href="/search"' in html:
        endpoints["search"] = "/search"

    return endpoints


def verify_site(base_url: str) -> tuple[bool, list[str]]:
    """
    Verify a deployed Planet site.

    Returns:
        (passed: bool, errors: list[str])
    """
    errors = []
    base_url = base_url.rstrip("/")

    print(f"\nVerifying: {base_url}")
    print("-" * 60)

    # 1. Check homepage returns 200
    print("  Checking homepage...")
    status, body, headers = fetch_url(base_url + "/")
    if status != 200:
        errors.append(f"Homepage returned HTTP {status} (expected 200)")
        if "Error" in body or "error" in body.lower():
            error_match = re.search(r"(UndefinedError|TemplateError|Error)[^<]*", body)
            if error_match:
                errors.append(f"Error detected: {error_match.group(0)[:100]}")
        return False, errors

    # 2. Check for required HTML elements
    print("  Checking HTML structure...")
    required_elements = [
        ("<title>", "Missing <title> tag"),
        ("</html>", "HTML not properly closed"),
    ]
    for element, error_msg in required_elements:
        if element not in body:
            errors.append(error_msg)

    if 'rel="stylesheet"' not in body and "rel='stylesheet'" not in body:
        errors.append("Missing CSS stylesheet link")

    # 3. Check for template errors in the HTML
    if "UndefinedError" in body:
        errors.append("Jinja2 UndefinedError in rendered page")
    if "TemplateNotFound" in body:
        errors.append("Template not found error")

    # Check for unrendered Jinja2 tags (outside script/style blocks)
    body_no_scripts = re.sub(
        r"<script[^>]*>.*?</script>", "", body, flags=re.DOTALL | re.IGNORECASE
    )
    body_no_scripts = re.sub(
        r"<style[^>]*>.*?</style>", "", body_no_scripts, flags=re.DOTALL | re.IGNORECASE
    )
    if re.search(r"\{\{\s*\w+", body_no_scripts):
        errors.append("Possible unrendered Jinja2 template tag ({{ variable }})")
    if re.search(r"\{%\s*(if|for|block|extends|include|macro)", body_no_scripts):
        errors.append("Possible unrendered Jinja2 control tag ({% if/for/etc %})")

    # 4. Check CSS loads
    print("  Checking CSS...")
    css_status, _, _ = fetch_url(base_url + "/static/style.css")
    if css_status != 200:
        errors.append(f"CSS returned HTTP {css_status} (expected 200)")

    # 5. Extract and display page title
    title_match = re.search(r"<title>([^<]+)</title>", body)
    if title_match:
        print(f"  Page title: {title_match.group(1)}")

    # 6. Check for entries (should have some content)
    entry_indicators = ["<article", 'class="entry"', 'class="item"', "<h2"]
    has_structure = any(indicator in body for indicator in entry_indicators)
    if not has_structure:
        errors.append("No entry/article structure found - page may be empty or broken")

    # 7. Discover and verify feeds
    discovered = discover_endpoints(body)
    feed_types = [k for k in discovered if k in FEED_VALIDATORS]
    print(f"  Discovered endpoints: {', '.join(sorted(discovered.keys())) or 'none'}")

    for feed_type in feed_types:
        path = discovered[feed_type]
        label, expected_tag = FEED_VALIDATORS[feed_type]
        print(f"  Checking {label} feed ({path})...")
        feed_status, feed_body, _ = fetch_url(base_url + path)
        if feed_status != 200:
            errors.append(f"{label} feed returned HTTP {feed_status}")
        elif expected_tag.lower() not in feed_body.lower():
            errors.append(f"{label} feed missing expected <{expected_tag}> content")

    # Fallback: always verify RSS and Atom even if not discovered
    if "rss" not in discovered:
        print("  Checking RSS feed (fallback)...")
        rss_status, rss_body, _ = fetch_url(base_url + "/feed.rss")
        if rss_status != 200:
            errors.append(f"RSS feed returned HTTP {rss_status}")
        elif "<rss" not in rss_body:
            errors.append("RSS feed missing <rss> content")
    if "atom" not in discovered:
        print("  Checking Atom feed (fallback)...")
        atom_status, atom_body, _ = fetch_url(base_url + "/feed.atom")
        if atom_status != 200:
            errors.append(f"Atom feed returned HTTP {atom_status}")
        elif "<feed" not in atom_body:
            errors.append("Atom feed missing <feed> content")

    # 8. Check titles page if discovered
    if "titles" in discovered:
        print("  Checking titles page...")
        titles_status, titles_body, _ = fetch_url(base_url + discovered["titles"])
        if titles_status != 200:
            errors.append(f"Titles page returned HTTP {titles_status}")
        elif "<title>" not in titles_body:
            errors.append("Titles page missing <title> tag")

    # 9. Check search page if discovered (403/404 = lite mode, acceptable)
    if "search" in discovered:
        print("  Checking search endpoint...")
        search_status, _, _ = fetch_url(base_url + "/search?q=test")
        if search_status in (403, 404):
            print("  Search disabled (lite or admin mode)")
        elif search_status != 200:
            errors.append(f"Search returned HTTP {search_status}")

    # 10. Check /health endpoint for feed status
    print("  Checking health endpoint...")
    health_status, health_body, _ = fetch_url(base_url + "/health")
    if health_status == 200:
        try:
            import json as json_mod

            health = json_mod.loads(health_body)
            feed_status = health.get("status", "unknown")
            feeds_info = health.get("feeds", {})
            print(
                f"  Health: {feed_status} "
                f"(total={feeds_info.get('total', '?')}, "
                f"healthy={feeds_info.get('healthy', '?')}, "
                f"failing={feeds_info.get('failing', '?')}, "
                f"inactive={feeds_info.get('inactive', '?')})"
            )
            if feed_status == "unhealthy":
                errors.append("Health endpoint reports unhealthy status (no healthy feeds)")
        except (json_mod.JSONDecodeError, KeyError):
            pass  # Health endpoint returned non-JSON, skip
    else:
        print(f"  Health endpoint returned HTTP {health_status} (non-critical)")

    if errors:
        print(f"  FAILED: {len(errors)} issue(s)")
        for error in errors:
            print(f"    - {error}")
        return False, errors
    else:
        print("  PASSED")
        return True, []


def get_deployed_urls_from_examples() -> list[str]:
    """Get worker URLs from example wrangler configs."""
    urls = []
    examples_dir = PROJECT_ROOT / "examples"

    for wrangler_file in examples_dir.glob("*/wrangler.jsonc"):
        content = wrangler_file.read_text()
        # Remove comments
        content_no_comments = re.sub(r"//.*$", "", content, flags=re.MULTILINE)

        try:
            config = json.loads(content_no_comments)
            name = config.get("name", "")
            if name:
                # Construct workers.dev URL
                # Note: This is a guess - actual URL depends on account
                urls.append(f"https://{name}.workers.dev")
        except json.JSONDecodeError:
            continue

    return urls


def main():
    parser = argparse.ArgumentParser(
        description="Verify deployed Planet sites are working correctly."
    )
    parser.add_argument(
        "urls", nargs="*", help="URLs to verify (e.g., https://planetcf.workers.dev/)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Verify all examples (constructs URLs from wrangler configs)",
    )

    args = parser.parse_args()

    if not args.urls and not args.all:
        parser.print_help()
        print("\nError: Provide URLs to verify or use --all")
        sys.exit(1)

    urls = args.urls if args.urls else []

    if args.all:
        example_urls = get_deployed_urls_from_examples()
        print(f"Found {len(example_urls)} examples in wrangler configs")
        urls.extend(example_urls)

    if not urls:
        print("No URLs to verify")
        sys.exit(1)

    print(f"\nVerifying {len(urls)} site(s)...")
    print("=" * 60)

    results = []
    for url in urls:
        passed, errors = verify_site(url)
        results.append((url, passed, errors))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed_count = sum(1 for _, passed, _ in results if passed)
    failed_count = len(results) - passed_count

    for url, passed, _errors in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {url}")

    print()
    print(f"Passed: {passed_count}/{len(results)}")
    print(f"Failed: {failed_count}/{len(results)}")

    if failed_count > 0:
        print("\nVERIFICATION FAILED")
        sys.exit(1)
    else:
        print("\nVERIFICATION PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
