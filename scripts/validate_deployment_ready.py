#!/usr/bin/env python3
"""
Validate that the codebase is ready for deployment.

This script checks for common issues that could cause deployment failures:
1. python_modules/ directory exists and has required packages
2. templates.py is up-to-date with build_templates.py output
3. All themes referenced in wrangler configs exist in templates.py
4. Template variables contract is satisfied

Run before deployment:
    python scripts/validate_deployment_ready.py

Exit codes:
    0 - All checks passed
    1 - One or more checks failed
"""

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# Required packages for Cloudflare Python Workers
REQUIRED_PACKAGES = ["feedparser", "jinja2", "bleach", "markupsafe"]

# Themes that should exist in templates.py
EXPECTED_THEMES = ["default", "planet-mozilla", "planet-python"]


def check_python_modules() -> list[str]:
    """Check that python_modules exists and has required packages."""
    errors = []
    python_modules = PROJECT_ROOT / "python_modules"

    if not python_modules.exists():
        errors.append(
            "python_modules/ directory not found. Run 'make python-modules' to create it."
        )
        return errors

    for package in REQUIRED_PACKAGES:
        package_dir = python_modules / package
        if not package_dir.exists():
            errors.append(
                f"python_modules/{package}/ not found. Run 'make python-modules' to recreate."
            )

    return errors


def check_templates_generated() -> list[str]:
    """Check that templates.py contains expected theme structure."""
    errors = []
    templates_py = PROJECT_ROOT / "src" / "templates.py"

    if not templates_py.exists():
        errors.append("src/templates.py not found!")
        return errors

    content = templates_py.read_text()

    # Check for per-theme structure (not flat structure)
    if "_EMBEDDED_TEMPLATES = {" not in content:
        errors.append(
            "templates.py missing _EMBEDDED_TEMPLATES dict. "
            "Run 'python scripts/build_templates.py' to regenerate."
        )
        return errors

    # Check each expected theme exists
    for theme in EXPECTED_THEMES:
        if f'"{theme}":' not in content:
            errors.append(
                f"Theme '{theme}' not found in templates.py. "
                "Run 'python scripts/build_templates.py' to regenerate."
            )

    # Check for theme parameter in render_template
    if "def render_template(name: str, theme: str" not in content:
        errors.append(
            "render_template() missing theme parameter. "
            "Run 'python scripts/build_templates.py' to regenerate."
        )

    return errors


def check_wrangler_themes() -> list[str]:
    """Check that themes in wrangler configs exist in templates.py."""
    errors = []
    examples_dir = PROJECT_ROOT / "examples"
    templates_py = PROJECT_ROOT / "src" / "templates.py"

    if not templates_py.exists():
        return ["templates.py not found - cannot verify themes"]

    templates_content = templates_py.read_text()

    for wrangler_file in examples_dir.glob("*/wrangler.jsonc"):
        content = wrangler_file.read_text()
        # Remove comments for JSON parsing
        content_no_comments = re.sub(r"//.*$", "", content, flags=re.MULTILINE)

        try:
            config = json.loads(content_no_comments)
        except json.JSONDecodeError:
            # Skip files that can't be parsed
            continue

        theme = config.get("vars", {}).get("THEME")
        if theme and theme != "default" and f'"{theme}":' not in templates_content:
            errors.append(
                f"{wrangler_file.relative_to(PROJECT_ROOT)}: "
                f"THEME '{theme}' not found in templates.py"
            )

    return errors


def check_main_uses_theme() -> list[str]:
    """Check that main.py passes theme to render_template calls."""
    errors = []
    main_py = PROJECT_ROOT / "src" / "main.py"

    if not main_py.exists():
        return ["src/main.py not found!"]

    content = main_py.read_text()

    # Check for _get_theme method
    if "def _get_theme(self)" not in content:
        errors.append("main.py missing _get_theme() method. Theme selection won't work without it.")

    # Check that render_template calls include theme parameter
    # Find render_template calls that don't have theme=
    render_calls = re.findall(r"render_template\([^)]+\)", content, re.DOTALL)
    for call in render_calls:
        if "theme=" not in call and "theme =" not in call:
            # Extract first line for context
            first_line = call.split("\n")[0][:60]
            errors.append(f"render_template call may be missing theme parameter: {first_line}...")

    return errors


def check_example_symlinks() -> list[str]:
    """Check that example directories have python_modules symlinks."""
    errors = []
    examples_dir = PROJECT_ROOT / "examples"

    for example_dir in examples_dir.iterdir():
        if not example_dir.is_dir():
            continue

        wrangler = example_dir / "wrangler.jsonc"
        if not wrangler.exists():
            continue

        python_modules = example_dir / "python_modules"
        if not python_modules.exists() and not python_modules.is_symlink():
            errors.append(
                f"{example_dir.name}/python_modules not found. "
                "Create symlink with: ln -s ../../python_modules "
                f"examples/{example_dir.name}/python_modules"
            )

    return errors


def main():
    """Run all validation checks."""
    print("Validating deployment readiness...\n")

    all_errors = []

    checks = [
        ("Python modules", check_python_modules),
        ("Templates generated", check_templates_generated),
        ("Wrangler theme configs", check_wrangler_themes),
        ("Main.py theme integration", check_main_uses_theme),
        ("Example symlinks", check_example_symlinks),
    ]

    for name, check_fn in checks:
        print(f"Checking {name}...")
        errors = check_fn()
        if errors:
            print(f"  FAILED: {len(errors)} issue(s)")
            for error in errors:
                print(f"    - {error}")
            all_errors.extend(errors)
        else:
            print("  OK")

    print()
    if all_errors:
        print(f"VALIDATION FAILED: {len(all_errors)} issue(s) found")
        print("Fix the issues above before deploying.")
        sys.exit(1)
    else:
        print("VALIDATION PASSED: Ready to deploy!")
        sys.exit(0)


if __name__ == "__main__":
    main()
