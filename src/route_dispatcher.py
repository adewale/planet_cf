# src/route_dispatcher.py
"""Route dispatcher for HTTP request routing.

This module provides the RouteDispatcher class that encapsulates
the routing logic from the fetch() handler:
- Route table with patterns, handlers, and metadata
- Pattern matching (exact and prefix)
- Method filtering
- Route metadata (content type, cache status)

Usage:
    # Define routes (static files are served by Workers Static Assets, not the Worker)
    routes = [
        Route(path="/", handler=serve_html, content_type="html", cacheable=True),
        Route(path="/search", handler=search, content_type="search", cacheable=False),
        Route(path="/admin", handler=admin, prefix=True, content_type="admin"),
    ]

    dispatcher = RouteDispatcher(routes)
    match = dispatcher.match("/admin/feeds")

    if match:
        response = await match.handler(request)
"""

import re
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Route:
    """Definition of a route.

    Attributes:
        path: URL path pattern (exact match or prefix)
        handler: Async handler function for the route
        methods: Allowed HTTP methods (None = all methods)
        prefix: If True, match paths that start with this path
        pattern: Regex pattern for dynamic path matching
        content_type: Content type identifier for logging
        cacheable: Whether this route's response can be cached
        route_name: Name for the route (for logging), defaults to path
        requires_auth: Whether this route requires authentication
        requires_mode: Minimum mode required for this route (None=always, 'admin', or 'full')
    """

    path: str
    handler: Callable[..., Coroutine[Any, Any, Any]] | None = None
    methods: list[str] | None = None
    prefix: bool = False
    pattern: str | None = None
    content_type: str = "html"
    cacheable: bool = True
    route_name: str | None = None
    requires_auth: bool = False
    requires_mode: str | None = None

    def __post_init__(self) -> None:
        """Set default route name if not provided."""
        if self.route_name is None:
            if self.prefix:
                self.route_name = f"{self.path}*"
            elif self.pattern:
                self.route_name = self.path
            else:
                self.route_name = self.path


@dataclass
class RouteMatch:
    """Result of a route match.

    Attributes:
        route: The matched route
        path_params: Extracted path parameters (for pattern routes)
        path: The matched path
    """

    route: Route
    path_params: dict[str, str] = field(default_factory=dict)
    path: str = ""

    @property
    def handler(self) -> Callable[..., Coroutine[Any, Any, Any]] | None:
        """Get the handler function for this route."""
        return self.route.handler

    @property
    def content_type(self) -> str:
        """Get the content type for this route."""
        return self.route.content_type

    @property
    def cacheable(self) -> bool:
        """Get whether this route is cacheable."""
        return self.route.cacheable

    @property
    def cache_status(self) -> str:
        """Get the cache status string for logging."""
        return "cacheable" if self.route.cacheable else "bypass"

    @property
    def route_name(self) -> str:
        """Get the route name for logging."""
        return self.route.route_name or self.route.path

    @property
    def requires_auth(self) -> bool:
        """Get whether this route requires authentication."""
        return self.route.requires_auth

    @property
    def requires_mode(self) -> str | None:
        """Get the minimum mode required for this route."""
        return self.route.requires_mode


class RouteDispatcher:
    """Dispatcher for routing HTTP requests.

    Matches incoming requests against a list of routes and
    returns the matching route with metadata.

    Attributes:
        routes: List of route definitions
    """

    def __init__(self, routes: list[Route] | None = None):
        """Initialize the dispatcher.

        Args:
            routes: List of route definitions
        """
        self.routes: list[Route] = routes or []
        self._compiled_patterns: dict[str, re.Pattern] = {}

    def add_route(self, route: Route) -> None:
        """Add a route to the dispatcher.

        Args:
            route: Route definition to add
        """
        self.routes.append(route)

    def _compile_pattern(self, pattern: str) -> re.Pattern:
        """Compile a route pattern to regex.

        Args:
            pattern: Route pattern with :param placeholders

        Returns:
            Compiled regex pattern
        """
        if pattern in self._compiled_patterns:
            return self._compiled_patterns[pattern]

        # Convert :param style to named groups
        regex = pattern
        # Match :param_name patterns
        regex = re.sub(r":([a-zA-Z_][a-zA-Z0-9_]*)", r"(?P<\1>[^/]+)", regex)
        # Escape other special chars
        regex = f"^{regex}$"

        compiled = re.compile(regex)
        self._compiled_patterns[pattern] = compiled
        return compiled

    def match(self, path: str, method: str = "GET") -> RouteMatch | None:
        """Match a path against the routes.

        Args:
            path: URL path to match
            method: HTTP method

        Returns:
            RouteMatch if a route matches, None otherwise
        """
        # Normalize path
        if not path.startswith("/"):
            path = "/" + path

        for route in self.routes:
            # Check method
            if route.methods and method.upper() not in route.methods:
                continue

            # Pattern matching (dynamic routes)
            if route.pattern:
                compiled = self._compile_pattern(route.pattern)
                match = compiled.match(path)
                if match:
                    return RouteMatch(
                        route=route,
                        path_params=match.groupdict(),
                        path=path,
                    )
                continue

            # Prefix matching
            if route.prefix:
                if path.startswith(route.path):
                    return RouteMatch(route=route, path=path)
                continue

            # Exact matching
            if path == route.path:
                return RouteMatch(route=route, path=path)

        return None

    def get_route_name(self, path: str, method: str = "GET") -> str:
        """Get the route name for a path.

        Args:
            path: URL path
            method: HTTP method

        Returns:
            Route name if matched, "unknown" otherwise
        """
        match = self.match(path, method)
        if match:
            return match.route_name
        return "unknown"


def create_default_routes() -> list[Route]:
    """Create the default route definitions for Planet CF.

    Returns a list of routes without handlers - handlers should be
    set by the caller.

    Returns:
        List of Route definitions
    """
    return [
        # Public routes (cacheable)
        Route(path="/", content_type="html", cacheable=True),
        Route(path="/index.html", content_type="html", cacheable=True),
        Route(path="/titles", content_type="html", cacheable=True),
        Route(path="/titles.html", content_type="html", cacheable=True),
        Route(path="/feed.atom", content_type="atom", cacheable=True),
        Route(path="/feed.rss", content_type="rss", cacheable=True),
        Route(path="/feed.rss10", content_type="rss10", cacheable=True),
        Route(path="/feeds.opml", content_type="opml", cacheable=True),
        Route(path="/health", content_type="health", cacheable=False),
        Route(path="/search", content_type="search", cacheable=False, requires_mode="full"),
        # Static files are served by Workers Static Assets at the edge (no Worker needed)
        # OAuth routes (not cacheable)
        Route(
            path="/auth/github",
            content_type="auth",
            cacheable=False,
            requires_mode="admin",
        ),
        Route(
            path="/auth/github/callback",
            content_type="auth",
            cacheable=False,
            requires_mode="admin",
        ),
        # Admin routes (not cacheable, requires auth)
        Route(
            path="/admin",
            prefix=True,
            content_type="admin",
            cacheable=False,
            requires_auth=True,
            route_name="/admin/*",
            requires_mode="admin",
        ),
    ]
