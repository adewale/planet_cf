# src/templates.py
"""
Template loading and rendering utilities for Planet CF.

This module provides:
- A shared Jinja2 Environment for rendering templates
- Template loading from files (for development/deployment bundling)
- Helper functions for common rendering patterns

Templates are loaded from the templates/ directory at import time.
In the Cloudflare Workers context, templates should be bundled with the worker.
"""

from pathlib import Path

from jinja2 import BaseLoader, Environment, TemplateNotFound

# =============================================================================
# Template Loader
# =============================================================================

# Base path for templates (relative to project root)
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


class FileSystemLoader(BaseLoader):
    """
    Load templates from the filesystem.

    This loader reads templates from the templates/ directory.
    Templates are cached after first load for performance.
    """

    def __init__(self, search_path: Path):
        self.search_path = search_path
        self._template_cache: dict[str, str] = {}

    def get_source(self, environment: Environment, template: str) -> tuple[str, str, callable]:
        """Load a template from the filesystem."""
        # Check cache first
        if template in self._template_cache:
            source = self._template_cache[template]
            path = str(self.search_path / template)
            return source, path, lambda: True

        # Load from filesystem
        template_path = self.search_path / template
        if not template_path.exists():
            raise TemplateNotFound(template)

        source = template_path.read_text(encoding="utf-8")
        self._template_cache[template] = source

        return source, str(template_path), lambda: True


class DictLoader(BaseLoader):
    """
    Load templates from a dictionary.

    This loader is useful for testing or when templates are bundled
    as strings (e.g., in a single-file deployment).
    """

    def __init__(self, templates: dict[str, str]):
        self.templates = templates

    def get_source(self, environment: Environment, template: str) -> tuple[str, str, callable]:
        """Load a template from the dictionary."""
        if template not in self.templates:
            raise TemplateNotFound(template)

        source = self.templates[template]
        return source, template, lambda: True


# =============================================================================
# Shared Jinja2 Environment
# =============================================================================

def _create_environment(loader: BaseLoader | None = None) -> Environment:
    """
    Create a Jinja2 environment with appropriate settings.

    Args:
        loader: Optional template loader. If None, uses FileSystemLoader.

    Returns:
        Configured Jinja2 Environment
    """
    if loader is None:
        loader = FileSystemLoader(TEMPLATES_DIR)

    return Environment(
        loader=loader,
        autoescape=True,  # Auto-escape HTML by default for security
        trim_blocks=True,
        lstrip_blocks=True,
    )


# Module-level environment (created on first access)
_jinja_env: Environment | None = None


def get_jinja_env() -> Environment:
    """
    Get the shared Jinja2 environment.

    This function returns a singleton Environment instance that is
    reused across all template rendering operations.

    Returns:
        The shared Jinja2 Environment
    """
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = _create_environment()
    return _jinja_env


def reset_jinja_env() -> None:
    """
    Reset the shared Jinja2 environment.

    This is primarily useful for testing to ensure a fresh environment.
    """
    global _jinja_env
    _jinja_env = None


def set_jinja_env(env: Environment) -> None:
    """
    Set a custom Jinja2 environment.

    This is useful for testing with mock templates.

    Args:
        env: The Environment to use
    """
    global _jinja_env
    _jinja_env = env


# =============================================================================
# Template Rendering Helpers
# =============================================================================

def render_template(template_name: str, **context) -> str:
    """
    Render a template with the given context.

    Args:
        template_name: Name of the template file (e.g., "index.html")
        **context: Template context variables

    Returns:
        Rendered template as a string
    """
    env = get_jinja_env()
    template = env.get_template(template_name)
    return template.render(**context)


def render_string(template_string: str, **context) -> str:
    """
    Render a template string with the given context.

    This is useful for one-off templates that aren't stored in files.

    Args:
        template_string: The template as a string
        **context: Template context variables

    Returns:
        Rendered template as a string
    """
    env = get_jinja_env()
    template = env.from_string(template_string)
    return template.render(**context)


# =============================================================================
# Template Names Constants
# =============================================================================

# Standard template file names
TEMPLATE_INDEX = "index.html"
TEMPLATE_SEARCH = "search.html"
TEMPLATE_ADMIN_DASHBOARD = "admin/dashboard.html"
