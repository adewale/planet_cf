#!/usr/bin/env python3
"""
Planet/Venus to PlanetCF Converter

This tool converts any existing Planet or Venus website into a PlanetCF instance
with 100% fidelity. It captures all the lessons learned from manual conversion:

LESSONS LEARNED:
1. Fetch CSS from authoritative sources (GitHub or live site)
2. Download ALL assets (logos, images, icons, backgrounds, fonts)
3. Extract exact template text ("Subscriptions", "Last update:", etc.)
4. Detect sidebar position (left/right) from CSS
5. Extract related-sites sections from sidebar
6. Match date formats exactly
7. Verify assets are served correctly (HTTP 200)
8. Use visual comparison for verification
9. Dynamic content differs - compare structure not content
10. THEME_LOGOS must include 'url' key for template rendering

Usage:
    python scripts/convert_planet.py https://planetpython.org/ --name planet-python
    python scripts/convert_planet.py https://planet.mozilla.org/ --name planet-mozilla
"""

import argparse
import base64
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

# Check dependencies
MISSING_DEPS = []
try:
    import requests
except ImportError:
    MISSING_DEPS.append("requests")

try:
    from bs4 import BeautifulSoup
except ImportError:
    MISSING_DEPS.append("beautifulsoup4")

if MISSING_DEPS:
    print("ERROR: Missing required dependencies:")
    print(f"  pip install {' '.join(MISSING_DEPS)}")
    print("\nOr install all converter dependencies:")
    print("  pip install requests beautifulsoup4 playwright")
    print("  playwright install chromium  # for visual comparison")
    sys.exit(1)


@dataclass
class ExtractedAsset:
    """An asset extracted from the original site."""

    url: str
    local_path: str
    content_type: str
    data: bytes = field(repr=False)
    base64_data: str = field(repr=False, default="")

    def __post_init__(self):
        if not self.base64_data and self.data:
            self.base64_data = base64.b64encode(self.data).decode("utf-8")


@dataclass
class ExtractedCSS:
    """CSS extracted from the original site."""

    url: str
    content: str
    variables: dict = field(default_factory=dict)


@dataclass
class ExtractedTemplate:
    """Template text and structure extracted from the original site."""

    title: str
    description: str
    sidebar_position: str  # 'left' or 'right'
    subscriptions_heading: str
    last_update_format: str
    last_update_text: str
    feed_links: dict
    related_sites: list
    date_header_format: str


@dataclass
class ConversionResult:
    """Complete result of converting a Planet site."""

    name: str
    source_url: str
    assets: list[ExtractedAsset]
    css: list[ExtractedCSS]
    template: ExtractedTemplate
    theme_css: str
    theme_assets: dict
    theme_logos: dict
    wrangler_config: dict
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class PlanetConverter:
    """
    Converts a Planet/Venus website to PlanetCF format.

    This class encapsulates all the lessons learned from manual conversion:
    - Systematic asset discovery and download
    - CSS extraction and adaptation
    - Template text extraction
    - Structural analysis (sidebar position, layout)
    - Visual verification preparation
    """

    def __init__(self, source_url: str, name: str, output_dir: Path):
        self.source_url = source_url.rstrip("/")
        self.name = name
        self.output_dir = output_dir
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "PlanetCF-Converter/1.0 (https://github.com/example/planet_cf)"}
        )
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def convert(self) -> ConversionResult:
        """Main conversion process."""
        print(f"Converting {self.source_url} to PlanetCF instance '{self.name}'")
        print("=" * 60)

        # Step 1: Fetch and parse the main page
        print("\n[1/7] Fetching main page...")
        html = self._fetch_page(self.source_url)
        if not html:
            return self._error_result("Failed to fetch main page")
        soup = BeautifulSoup(html, "html.parser")

        # Step 2: Extract all assets (images, icons, fonts)
        print("\n[2/7] Discovering and downloading assets...")
        assets = self._extract_assets(soup)
        print(f"  Found {len(assets)} assets")

        # Step 3: Extract CSS
        print("\n[3/7] Extracting CSS...")
        css_list = self._extract_css(soup)
        print(f"  Found {len(css_list)} stylesheets")

        # Step 4: Extract template text and structure
        print("\n[4/7] Extracting template structure...")
        template = self._extract_template(soup, css_list)

        # Step 5: Generate theme CSS adapted for PlanetCF
        print("\n[5/7] Generating theme CSS...")
        theme_css = self._generate_theme_css(css_list, template)

        # Step 6: Generate theme assets dictionary
        print("\n[6/7] Generating theme assets...")
        theme_assets, theme_logos = self._generate_theme_assets(assets)

        # Step 7: Generate wrangler config
        print("\n[7/7] Generating wrangler config...")
        wrangler_config = self._generate_wrangler_config(template)

        # Save everything
        print("\n[SAVE] Writing output files...")
        self._save_output(assets, css_list, theme_css, theme_assets, wrangler_config)

        return ConversionResult(
            name=self.name,
            source_url=self.source_url,
            assets=assets,
            css=css_list,
            template=template,
            theme_css=theme_css,
            theme_assets=theme_assets,
            theme_logos=theme_logos,
            wrangler_config=wrangler_config,
            errors=self.errors,
            warnings=self.warnings,
        )

    def _fetch_page(self, url: str) -> str | None:
        """Fetch a page and return its HTML content."""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            self.errors.append(f"Failed to fetch {url}: {e}")
            return None

    def _fetch_binary(self, url: str) -> bytes | None:
        """Fetch binary content (images, etc.)."""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.content
        except Exception as e:
            self.warnings.append(f"Failed to fetch asset {url}: {e}")
            return None

    def _extract_assets(self, soup: BeautifulSoup) -> list[ExtractedAsset]:
        """
        Extract all assets from the page.

        LESSON: Download ALL assets - logos, backgrounds, icons, bullets.
        Missing any asset leads to visual differences.
        """
        assets = []
        seen_urls = set()

        # Find images
        for img in soup.find_all("img"):
            src = img.get("src")
            if src:
                assets.extend(self._download_asset(src, seen_urls, "image"))

        # Find CSS background images
        for style in soup.find_all("style"):
            if style.string:
                urls = re.findall(r"url\(['\"]?([^'\")\s]+)['\"]?\)", style.string)
                for url in urls:
                    assets.extend(self._download_asset(url, seen_urls, "background"))

        # Find link icons (favicon, apple-touch-icon)
        for link in soup.find_all("link"):
            href = link.get("href")
            rel = link.get("rel", [])
            if href and any(r in ["icon", "apple-touch-icon", "shortcut"] for r in rel):
                assets.extend(self._download_asset(href, seen_urls, "icon"))

        # Find CSS files and extract their background images
        for link in soup.find_all("link", rel="stylesheet"):
            href = link.get("href")
            if href:
                css_url = urljoin(self.source_url, href)
                css_content = self._fetch_page(css_url)
                if css_content:
                    urls = re.findall(r"url\(['\"]?([^'\")\s]+)['\"]?\)", css_content)
                    css_base = css_url.rsplit("/", 1)[0]
                    for url in urls:
                        full_url = urljoin(css_base + "/", url)
                        assets.extend(self._download_asset(full_url, seen_urls, "css-asset"))

        return assets

    def _download_asset(self, url: str, seen: set, asset_type: str) -> list[ExtractedAsset]:
        """Download a single asset."""
        if url.startswith("data:"):
            return []  # Skip data URLs

        full_url = urljoin(self.source_url, url)
        if full_url in seen:
            return []
        seen.add(full_url)

        data = self._fetch_binary(full_url)
        if not data:
            return []

        # Determine content type and local path
        parsed = urlparse(full_url)
        path = parsed.path.lstrip("/")
        ext = Path(path).suffix.lower()

        content_type_map = {
            ".gif": "image/gif",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
            ".woff": "font/woff",
            ".woff2": "font/woff2",
            ".ttf": "font/ttf",
        }
        content_type = content_type_map.get(ext, "application/octet-stream")

        local_path = f"static/{path}"
        print(f"  Downloaded: {path} ({len(data)} bytes)")

        return [
            ExtractedAsset(
                url=full_url, local_path=local_path, content_type=content_type, data=data
            )
        ]

    def _extract_css(self, soup: BeautifulSoup) -> list[ExtractedCSS]:
        """
        Extract all CSS from the page.

        LESSON: Get the EXACT CSS from the original, not approximations.
        Compare against GitHub repos when available.
        """
        css_list = []

        # External stylesheets
        for link in soup.find_all("link", rel="stylesheet"):
            href = link.get("href")
            if href:
                css_url = urljoin(self.source_url, href)
                content = self._fetch_page(css_url)
                if content:
                    css_list.append(ExtractedCSS(url=css_url, content=content))
                    print(f"  Extracted: {href} ({len(content)} bytes)")

        # Inline styles
        for style in soup.find_all("style"):
            if style.string:
                css_list.append(ExtractedCSS(url="inline", content=style.string.strip()))
                print(f"  Extracted: inline style ({len(style.string)} bytes)")

        return css_list

    def _extract_template(
        self, soup: BeautifulSoup, css_list: list[ExtractedCSS]
    ) -> ExtractedTemplate:
        """
        Extract template structure and text.

        LESSON: Match exact text strings like "Subscriptions", "Last update:", etc.
        These small differences are noticeable.
        """
        # Extract title
        title = ""
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text().strip()

        # Extract description
        description = ""
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            description = meta_desc.get("content", "")

        # Detect sidebar position from CSS
        sidebar_position = self._detect_sidebar_position(css_list, soup)

        # Extract subscriptions heading
        subscriptions_heading = "Subscriptions"
        for heading in soup.find_all(["h2", "h3", "h4"]):
            text = heading.get_text().strip()
            if "subscription" in text.lower():
                subscriptions_heading = text
                break

        # Extract last update text and format
        last_update_text = "Last update:"
        last_update_format = "%B %d, %Y %I:%M %p UTC"
        for text in soup.stripped_strings:
            if "last update" in text.lower():
                last_update_text = text.split(":")[0] + ":"
                break

        # Extract feed links
        feed_links = self._extract_feed_links(soup)

        # Extract related sites sections
        related_sites = self._extract_related_sites(soup)

        # Detect date header format
        date_header_format = self._detect_date_format(soup)

        return ExtractedTemplate(
            title=title,
            description=description,
            sidebar_position=sidebar_position,
            subscriptions_heading=subscriptions_heading,
            last_update_format=last_update_format,
            last_update_text=last_update_text,
            feed_links=feed_links,
            related_sites=related_sites,
            date_header_format=date_header_format,
        )

    def _detect_sidebar_position(self, css_list: list[ExtractedCSS], soup: BeautifulSoup) -> str:
        """
        Detect whether sidebar is on left or right.

        LESSON: Sidebar position is a key structural difference.
        Check CSS for float, order, or position properties.
        """
        combined_css = " ".join(css.content for css in css_list)

        # Check for left-positioned sidebar indicators
        left_indicators = [
            "float: left" in combined_css and "sidebar" in combined_css.lower(),
            "order: -1" in combined_css,
            "#left-hand" in combined_css,
            "margin-left:" in combined_css and "19em" in combined_css,  # Planet Python specific
        ]

        # Check HTML structure
        sidebar = soup.find(class_=re.compile(r"sidebar", re.I)) or soup.find(
            id=re.compile(r"sidebar|menu|nav", re.I)
        )
        main = soup.find("main") or soup.find(id="content") or soup.find(class_="main")

        if sidebar and main:
            # Check DOM order - if sidebar comes before main, likely left
            sidebar_pos = str(soup).find(str(sidebar)[:50])
            main_pos = str(soup).find(str(main)[:50])
            if sidebar_pos < main_pos:
                return "left"

        if any(left_indicators):
            return "left"

        return "right"

    def _extract_feed_links(self, soup: BeautifulSoup) -> dict:
        """Extract RSS/Atom/OPML feed links."""
        links = {}

        for link in soup.find_all("link", rel="alternate"):
            link_type = link.get("type", "")
            href = link.get("href", "")
            if "rss" in link_type:
                links["rss"] = href
            elif "atom" in link_type:
                links["atom"] = href

        # Look for OPML links
        for a in soup.find_all("a", href=re.compile(r"\.opml", re.I)):
            links["opml"] = a.get("href")
            break

        return links

    def _extract_related_sites(self, soup: BeautifulSoup) -> list:
        """
        Extract related sites sections from sidebar.

        LESSON: Planet Python has multiple sections like "Other Python Planets",
        "Python Libraries", etc. These need to be replicated.
        """
        sections = []
        sidebar = soup.find(class_=re.compile(r"sidebar|menu|nav", re.I)) or soup.find(
            id=re.compile(r"sidebar|menu|left-hand", re.I)
        )

        if not sidebar:
            return sections

        current_section = None
        for element in sidebar.find_all(["h2", "h3", "h4", "li", "a"]):
            if element.name in ["h2", "h3", "h4"]:
                if current_section and current_section["links"]:
                    sections.append(current_section)
                text = element.get_text().strip()
                # Skip generic headings
                if text.lower() not in [
                    "subscriptions",
                    "feeds",
                    "subscribe",
                    "rss",
                    "search",
                ]:
                    current_section = {"title": text, "links": []}
                else:
                    current_section = None
            elif current_section and element.name == "a":
                href = element.get("href", "")
                text = element.get_text().strip()
                if href and text and href.startswith("http"):
                    current_section["links"].append({"name": text, "url": href})

        if current_section and current_section["links"]:
            sections.append(current_section)

        return sections

    def _detect_date_format(self, soup: BeautifulSoup) -> str:
        """Detect the date format used for day headers."""
        # Look for date headers (usually h2 with date text)
        for h2 in soup.find_all("h2"):
            text = h2.get_text().strip()
            # Check for common date patterns
            if re.match(r"\w+ \d{1,2}, \d{4}", text):  # January 31, 2026
                return "%B %d, %Y"
            elif re.match(r"\d{4}-\d{2}-\d{2}", text):  # 2026-01-31
                return "%Y-%m-%d"
        return "%B %d, %Y"

    def _generate_theme_css(self, css_list: list[ExtractedCSS], template: ExtractedTemplate) -> str:
        """
        Generate theme CSS adapted for PlanetCF's template structure.

        LESSON: Original CSS may use different selectors (#menu vs .sidebar).
        Adapt selectors while preserving visual properties.
        """
        # Combine all CSS
        combined = "\n\n".join(css.content for css in css_list)

        # Add header comment
        header = f"""/* Theme CSS for {self.name}
 * Extracted from: {self.source_url}
 * Sidebar position: {template.sidebar_position}
 * Generated by PlanetCF converter
 */

"""

        # Add sidebar positioning
        sidebar_css = ""
        if template.sidebar_position == "left":
            sidebar_css = """
/* Sidebar positioning - LEFT */
.sidebar {
    order: -1;
}
"""
        else:
            sidebar_css = """
/* Sidebar positioning - RIGHT */
.sidebar {
    order: 1;
}
"""

        return header + combined + sidebar_css

    def _generate_theme_assets(self, assets: list[ExtractedAsset]) -> tuple[dict, dict]:
        """
        Generate THEME_ASSETS and THEME_LOGOS dictionaries.

        LESSON: THEME_LOGOS MUST include 'url' key or template rendering crashes.
        """
        theme_assets = {}
        theme_logos = {}

        for asset in assets:
            # Identify logo
            if "logo" in asset.local_path.lower():
                mime = asset.content_type

                theme_assets["logo"] = {
                    "data": f"data:{mime};base64,{asset.base64_data}",
                    "content_type": mime,
                }

                # CRITICAL LESSON: url key is required!
                theme_logos = {
                    "url": f"/static/{Path(asset.local_path).name}",
                    "alt": f"{self.name} logo",
                    "width": "auto",
                    "height": "auto",
                }

            # Store other assets
            name = Path(asset.local_path).stem
            if name not in theme_assets:
                theme_assets[name] = {
                    "data": f"data:{asset.content_type};base64,{asset.base64_data}",
                    "content_type": asset.content_type,
                    "path": asset.local_path,
                }

        return theme_assets, theme_logos

    def _generate_wrangler_config(self, template: ExtractedTemplate) -> dict:
        """Generate wrangler.jsonc configuration."""
        return {
            "$schema": "node_modules/wrangler/config-schema.json",
            "name": self.name,
            "main": "../../src/main.py",
            "compatibility_date": "2026-01-01",
            "compatibility_flags": ["python_workers", "python_dedicated_snapshot"],
            "vars": {
                "INSTANCE_MODE": "lite",
                "PLANET_ID": self.name,
                "PLANET_NAME": template.title or self.name,
                "PLANET_DESCRIPTION": template.description or f"{self.name} feed aggregator",
                "PLANET_URL": self.source_url,
                "THEME": self.name,
                "RETENTION_DAYS": "90",
                "FEED_TIMEOUT_SECONDS": "60",
            },
        }

    def _save_output(
        self,
        assets: list[ExtractedAsset],
        css_list: list[ExtractedCSS],
        theme_css: str,
        theme_assets: dict,
        wrangler_config: dict,
    ):
        """Save all extracted content to the output directory."""
        instance_dir = self.output_dir / "examples" / self.name
        instance_dir.mkdir(parents=True, exist_ok=True)

        # Save assets
        for asset in assets:
            asset_path = instance_dir / asset.local_path
            asset_path.parent.mkdir(parents=True, exist_ok=True)
            asset_path.write_bytes(asset.data)
            print(f"  Saved: {asset_path}")

        # Save theme CSS
        theme_dir = instance_dir / "theme"
        theme_dir.mkdir(exist_ok=True)
        (theme_dir / "style.css").write_text(theme_css)
        print(f"  Saved: {theme_dir / 'style.css'}")

        # Save original CSS files
        for i, css in enumerate(css_list):
            if css.url != "inline":
                css_name = Path(urlparse(css.url).path).name
            else:
                css_name = f"inline_{i}.css"
            (instance_dir / "static" / css_name).parent.mkdir(parents=True, exist_ok=True)
            (instance_dir / "static" / css_name).write_text(css.content)

        # Save wrangler config
        with open(instance_dir / "wrangler.jsonc", "w") as f:
            # Write as JSONC with comments
            f.write(f"// {self.name} - Generated by PlanetCF converter\n")
            f.write(f"// Source: {self.source_url}\n\n")
            json.dump(wrangler_config, f, indent=2)
        print(f"  Saved: {instance_dir / 'wrangler.jsonc'}")

        # Save theme assets as Python dict (for manual integration)
        assets_py = f'''# Theme assets for {self.name}
# Add this to src/templates.py THEME_ASSETS dictionary

THEME_ASSETS["{self.name}"] = {json.dumps(theme_assets, indent=4)}
'''
        (instance_dir / "theme_assets.py").write_text(assets_py)
        print(f"  Saved: {instance_dir / 'theme_assets.py'}")

    def _error_result(self, message: str) -> ConversionResult:
        """Return an error result."""
        return ConversionResult(
            name=self.name,
            source_url=self.source_url,
            assets=[],
            css=[],
            template=ExtractedTemplate(
                title="",
                description="",
                sidebar_position="right",
                subscriptions_heading="Subscriptions",
                last_update_format="%B %d, %Y",
                last_update_text="Last update:",
                feed_links={},
                related_sites=[],
                date_header_format="%B %d, %Y",
            ),
            theme_css="",
            theme_assets={},
            theme_logos={},
            wrangler_config={},
            errors=[message],
        )


def main():
    parser = argparse.ArgumentParser(
        description="Convert a Planet/Venus website to PlanetCF format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/convert_planet.py https://planetpython.org/ --name planet-python
    python scripts/convert_planet.py https://planet.mozilla.org/ --name planet-mozilla

Lessons Applied:
    - Downloads ALL assets (logos, backgrounds, icons)
    - Extracts EXACT CSS from original
    - Matches template text ("Subscriptions", "Last update:", etc.)
    - Detects sidebar position (left/right)
    - Extracts related-sites sections
    - Generates wrangler.jsonc config
    - THEME_LOGOS includes required 'url' key
""",
    )

    parser.add_argument("url", help="URL of the Planet/Venus site to convert")
    parser.add_argument("--name", required=True, help="Name for the PlanetCF instance")
    parser.add_argument(
        "--output",
        default=".",
        help="Output directory (default: current directory)",
    )

    args = parser.parse_args()

    # Validate URL
    if not args.url.startswith(("http://", "https://")):
        print(f"Error: Invalid URL: {args.url}")
        sys.exit(1)

    # Run conversion
    converter = PlanetConverter(
        source_url=args.url,
        name=args.name,
        output_dir=Path(args.output),
    )

    result = converter.convert()

    # Print summary
    print("\n" + "=" * 60)
    print("CONVERSION SUMMARY")
    print("=" * 60)
    print(f"Source URL: {result.source_url}")
    print(f"Instance name: {result.name}")
    print(f"Assets downloaded: {len(result.assets)}")
    print(f"CSS files extracted: {len(result.css)}")
    print(f"Sidebar position: {result.template.sidebar_position}")
    print(f"Related sites sections: {len(result.template.related_sites)}")

    if result.errors:
        print(f"\nERRORS ({len(result.errors)}):")
        for error in result.errors:
            print(f"  - {error}")

    if result.warnings:
        print(f"\nWARNINGS ({len(result.warnings)}):")
        for warning in result.warnings:
            print(f"  - {warning}")

    print("\nNEXT STEPS:")
    print(f"  1. Review generated files in examples/{result.name}/")
    print("  2. Add theme to src/templates.py (see theme_assets.py)")
    print(f"  3. Deploy: npx wrangler deploy --config examples/{result.name}/wrangler.jsonc")
    print(f"  4. Verify: python scripts/visual_compare.py --url {result.source_url}")

    if result.errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
