#!/usr/bin/env python3
"""Visual Comparison Tool for Planet CF instances.

This script compares our Planet CF instances against the original sites
by taking screenshots and generating pixel-diff images.

Requirements:
    pip install playwright pillow pixelmatch

Usage:
    python scripts/visual_compare.py [--python] [--mozilla] [--all]

Example:
    python scripts/visual_compare.py --all
"""

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Error: playwright not installed. Run: pip install playwright")
    print("Then run: playwright install chromium")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("Error: Pillow not installed. Run: pip install Pillow")
    sys.exit(1)

try:
    from pixelmatch.contrib.PIL import pixelmatch
except ImportError:
    print("Error: pixelmatch not installed. Run: pip install pixelmatch")
    sys.exit(1)

# Output directory for screenshots and diffs
OUTPUT_DIR = Path(__file__).parent.parent / "visual_comparison_output"

# Sites to compare
SITES = {
    "planet-python": {
        "original": "https://planetpython.org/",
        "ours": "https://planet-python.adewale-883.workers.dev/",
        "viewport": {"width": 1280, "height": 800},
    },
    "planet-mozilla": {
        "original": "https://planet.mozilla.org/",
        "ours": "https://planet-mozilla.adewale-883.workers.dev/",
        "viewport": {"width": 1280, "height": 800},
    },
}


async def take_screenshot(page, url: str, output_path: Path, viewport: dict) -> bool:
    """Take a screenshot of a URL."""
    try:
        await page.set_viewport_size(viewport)
        await page.goto(url, wait_until="networkidle", timeout=60000)
        # Wait for content to settle
        await page.wait_for_timeout(2000)
        await page.screenshot(path=str(output_path), full_page=False)
        print(f"  Screenshot saved: {output_path}")
        return True
    except Exception as e:
        print(f"  Error taking screenshot of {url}: {e}")
        return False


def compare_images(img1_path: Path, img2_path: Path, diff_path: Path) -> tuple[float, int]:
    """Compare two images and generate a diff image.

    Returns:
        Tuple of (match_percentage, diff_pixel_count)
    """
    img1 = Image.open(img1_path)
    img2 = Image.open(img2_path)

    # Resize to same dimensions if needed
    if img1.size != img2.size:
        # Use the smaller dimensions
        width = min(img1.width, img2.width)
        height = min(img1.height, img2.height)
        img1 = img1.crop((0, 0, width, height))
        img2 = img2.crop((0, 0, width, height))

    # Create diff image
    diff = Image.new("RGBA", img1.size)

    # Calculate number of different pixels
    diff_pixels = pixelmatch(img1, img2, diff, threshold=0.1)

    # Save diff image
    diff.save(str(diff_path))

    # Calculate match percentage
    total_pixels = img1.width * img1.height
    match_percentage = ((total_pixels - diff_pixels) / total_pixels) * 100

    return match_percentage, diff_pixels


async def compare_site(browser, site_name: str, site_config: dict, timestamp: str) -> dict:
    """Compare a single site and return results."""
    print(f"\nComparing {site_name}...")

    site_dir = OUTPUT_DIR / site_name / timestamp
    site_dir.mkdir(parents=True, exist_ok=True)

    context = await browser.new_context()
    page = await context.new_page()

    results = {
        "site": site_name,
        "original_url": site_config["original"],
        "our_url": site_config["ours"],
        "original_screenshot": None,
        "our_screenshot": None,
        "diff_image": None,
        "match_percentage": 0.0,
        "diff_pixels": 0,
        "success": False,
    }

    original_path = site_dir / "original.png"
    our_path = site_dir / "ours.png"
    diff_path = site_dir / "diff.png"

    # Take screenshot of original
    print(f"  Taking screenshot of original: {site_config['original']}")
    original_success = await take_screenshot(
        page, site_config["original"], original_path, site_config["viewport"]
    )

    if original_success:
        results["original_screenshot"] = str(original_path)

    # Take screenshot of our version (if URL is configured)
    if "example.workers.dev" not in site_config["ours"]:
        print(f"  Taking screenshot of ours: {site_config['ours']}")
        our_success = await take_screenshot(
            page, site_config["ours"], our_path, site_config["viewport"]
        )

        if our_success:
            results["our_screenshot"] = str(our_path)

        # Generate diff if both screenshots exist
        if original_success and our_success:
            print("  Generating diff image...")
            match_pct, diff_pixels = compare_images(original_path, our_path, diff_path)
            results["diff_image"] = str(diff_path)
            results["match_percentage"] = match_pct
            results["diff_pixels"] = diff_pixels
            results["success"] = True
            print(f"  Match: {match_pct:.2f}% ({diff_pixels} different pixels)")
    else:
        print(f"  Skipping our version - URL not configured: {site_config['ours']}")
        print("  Update the 'ours' URL in SITES configuration after deployment")

    await context.close()
    return results


async def main(sites_to_compare: list[str]):
    """Main comparison routine."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("=" * 60)
    print("Planet CF Visual Comparison Tool")
    print("=" * 60)
    print(f"Timestamp: {timestamp}")
    print(f"Output directory: {OUTPUT_DIR}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch()

        all_results = []

        for site_name in sites_to_compare:
            if site_name in SITES:
                result = await compare_site(browser, site_name, SITES[site_name], timestamp)
                all_results.append(result)
            else:
                print(f"Warning: Unknown site '{site_name}'")

        await browser.close()

    # Print summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    for result in all_results:
        print(f"\n{result['site']}:")
        print(f"  Original URL: {result['original_url']}")
        print(f"  Our URL: {result['our_url']}")
        if result["success"]:
            print(f"  Match: {result['match_percentage']:.2f}%")
            print(f"  Different pixels: {result['diff_pixels']}")
            print(f"  Diff image: {result['diff_image']}")
        elif result["original_screenshot"]:
            print(f"  Original screenshot: {result['original_screenshot']}")
            print("  Our version not compared (URL not configured)")
        else:
            print("  Comparison failed")

    print("\n" + "=" * 60)
    print("Done!")

    return all_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Visual comparison tool for Planet CF instances")
    parser.add_argument(
        "--python",
        action="store_true",
        help="Compare Planet Python",
    )
    parser.add_argument(
        "--mozilla",
        action="store_true",
        help="Compare Planet Mozilla",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Compare all sites",
    )

    args = parser.parse_args()

    if args.all:
        sites = list(SITES.keys())
    else:
        sites = []
        if args.python:
            sites.append("planet-python")
        if args.mozilla:
            sites.append("planet-mozilla")

    if not sites:
        print("No sites specified. Use --python, --mozilla, or --all")
        parser.print_help()
        sys.exit(1)

    asyncio.run(main(sites))
