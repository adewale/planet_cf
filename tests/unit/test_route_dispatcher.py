# tests/unit/test_route_dispatcher.py
"""Tests for the route dispatcher."""


from src.route_dispatcher import (
    Route,
    RouteDispatcher,
    RouteMatch,
    create_default_routes,
)


class TestRoute:
    """Tests for Route dataclass."""

    def test_route_properties(self):
        """Route has correct properties."""
        route = Route(
            path="/api/feeds",
            content_type="json",
            cacheable=True,
        )

        assert route.path == "/api/feeds"
        assert route.content_type == "json"
        assert route.cacheable is True

    def test_default_values(self):
        """Route has sensible defaults."""
        route = Route(path="/test")

        assert route.handler is None
        assert route.methods is None
        assert route.prefix is False
        assert route.pattern is None
        assert route.content_type == "html"
        assert route.cacheable is True
        assert route.requires_auth is False
        assert route.lite_mode_disabled is False

    def test_route_name_defaults_to_path(self):
        """Route name defaults to path."""
        route = Route(path="/test")

        assert route.route_name == "/test"

    def test_route_name_prefix_adds_star(self):
        """Prefix routes add * to route name."""
        route = Route(path="/admin", prefix=True)

        assert route.route_name == "/admin*"

    def test_custom_route_name(self):
        """Custom route name overrides default."""
        route = Route(path="/admin", prefix=True, route_name="admin_area")

        assert route.route_name == "admin_area"


class TestRouteMatch:
    """Tests for RouteMatch dataclass."""

    def test_match_properties(self):
        """RouteMatch exposes route properties."""
        route = Route(
            path="/test",
            content_type="json",
            cacheable=False,
            requires_auth=True,
        )
        match = RouteMatch(route=route, path="/test")

        assert match.content_type == "json"
        assert match.cacheable is False
        assert match.cache_status == "bypass"
        assert match.requires_auth is True
        assert match.route_name == "/test"

    def test_cacheable_cache_status(self):
        """Cacheable routes have 'cacheable' status."""
        route = Route(path="/test", cacheable=True)
        match = RouteMatch(route=route, path="/test")

        assert match.cache_status == "cacheable"

    def test_path_params(self):
        """Path params are accessible."""
        route = Route(path="/feeds/:id", pattern="/feeds/:id")
        match = RouteMatch(
            route=route,
            path="/feeds/123",
            path_params={"id": "123"},
        )

        assert match.path_params["id"] == "123"


class TestRouteDispatcherExactMatch:
    """Tests for exact path matching."""

    def test_exact_match(self):
        """Matches exact path."""
        routes = [Route(path="/")]
        dispatcher = RouteDispatcher(routes)

        match = dispatcher.match("/")

        assert match is not None
        assert match.route.path == "/"

    def test_exact_match_no_leading_slash(self):
        """Adds leading slash if missing."""
        routes = [Route(path="/test")]
        dispatcher = RouteDispatcher(routes)

        match = dispatcher.match("test")

        assert match is not None
        assert match.path == "/test"

    def test_no_match_returns_none(self):
        """Returns None when no route matches."""
        routes = [Route(path="/")]
        dispatcher = RouteDispatcher(routes)

        match = dispatcher.match("/notfound")

        assert match is None

    def test_exact_match_multiple_routes(self):
        """Matches correct route from multiple."""
        routes = [
            Route(path="/"),
            Route(path="/search", content_type="search"),
            Route(path="/admin", content_type="admin"),
        ]
        dispatcher = RouteDispatcher(routes)

        match = dispatcher.match("/search")

        assert match is not None
        assert match.content_type == "search"


class TestRouteDispatcherPrefixMatch:
    """Tests for prefix path matching."""

    def test_prefix_match(self):
        """Matches paths starting with prefix."""
        routes = [Route(path="/admin", prefix=True)]
        dispatcher = RouteDispatcher(routes)

        assert dispatcher.match("/admin") is not None
        assert dispatcher.match("/admin/feeds") is not None
        assert dispatcher.match("/admin/feeds/123") is not None

    def test_prefix_no_match(self):
        """Doesn't match paths not starting with prefix."""
        routes = [Route(path="/admin/", prefix=True)]  # Note: trailing slash
        dispatcher = RouteDispatcher(routes)

        # /administrator doesn't start with /admin/
        assert dispatcher.match("/administrator") is None
        assert dispatcher.match("/other") is None
        # But /admin/something does match
        assert dispatcher.match("/admin/feeds") is not None

    def test_static_prefix_match(self):
        """Static files prefix matching."""
        routes = [Route(path="/static/", prefix=True)]
        dispatcher = RouteDispatcher(routes)

        assert dispatcher.match("/static/style.css") is not None
        assert dispatcher.match("/static/js/app.js") is not None
        assert dispatcher.match("/staticfile") is None


class TestRouteDispatcherPatternMatch:
    """Tests for regex pattern matching."""

    def test_pattern_match_single_param(self):
        """Matches pattern with single parameter."""
        routes = [Route(path="/feeds/:id", pattern="/feeds/:id")]
        dispatcher = RouteDispatcher(routes)

        match = dispatcher.match("/feeds/123")

        assert match is not None
        assert match.path_params["id"] == "123"

    def test_pattern_match_multiple_params(self):
        """Matches pattern with multiple parameters."""
        routes = [Route(path="/feeds/:feed_id/entries/:entry_id", pattern="/feeds/:feed_id/entries/:entry_id")]
        dispatcher = RouteDispatcher(routes)

        match = dispatcher.match("/feeds/42/entries/99")

        assert match is not None
        assert match.path_params["feed_id"] == "42"
        assert match.path_params["entry_id"] == "99"

    def test_pattern_no_match(self):
        """Pattern doesn't match invalid paths."""
        routes = [Route(path="/feeds/:id", pattern="/feeds/:id")]
        dispatcher = RouteDispatcher(routes)

        assert dispatcher.match("/feeds/") is None
        assert dispatcher.match("/feeds") is None
        assert dispatcher.match("/other/123") is None


class TestRouteDispatcherMethodFiltering:
    """Tests for HTTP method filtering."""

    def test_method_filtering_matches(self):
        """Matches when method is allowed."""
        routes = [Route(path="/api/feeds", methods=["GET", "POST"])]
        dispatcher = RouteDispatcher(routes)

        assert dispatcher.match("/api/feeds", "GET") is not None
        assert dispatcher.match("/api/feeds", "POST") is not None

    def test_method_filtering_rejects(self):
        """Rejects when method not allowed."""
        routes = [Route(path="/api/feeds", methods=["GET"])]
        dispatcher = RouteDispatcher(routes)

        assert dispatcher.match("/api/feeds", "POST") is None
        assert dispatcher.match("/api/feeds", "DELETE") is None

    def test_no_method_filter_allows_all(self):
        """No method filter allows all methods."""
        routes = [Route(path="/api/feeds")]
        dispatcher = RouteDispatcher(routes)

        assert dispatcher.match("/api/feeds", "GET") is not None
        assert dispatcher.match("/api/feeds", "POST") is not None
        assert dispatcher.match("/api/feeds", "DELETE") is not None

    def test_method_case_insensitive(self):
        """Method matching is case insensitive on input."""
        routes = [Route(path="/api/feeds", methods=["GET"])]
        dispatcher = RouteDispatcher(routes)

        assert dispatcher.match("/api/feeds", "get") is not None
        assert dispatcher.match("/api/feeds", "Get") is not None


class TestRouteDispatcherGetRouteName:
    """Tests for route name lookup."""

    def test_get_route_name_found(self):
        """Returns route name when found."""
        routes = [Route(path="/search", route_name="search_page")]
        dispatcher = RouteDispatcher(routes)

        assert dispatcher.get_route_name("/search") == "search_page"

    def test_get_route_name_not_found(self):
        """Returns 'unknown' when not found."""
        routes = [Route(path="/")]
        dispatcher = RouteDispatcher(routes)

        assert dispatcher.get_route_name("/notfound") == "unknown"


class TestRouteDispatcherAddRoute:
    """Tests for adding routes dynamically."""

    def test_add_route(self):
        """Can add routes dynamically."""
        dispatcher = RouteDispatcher()
        dispatcher.add_route(Route(path="/new"))

        assert dispatcher.match("/new") is not None

    def test_add_multiple_routes(self):
        """Can add multiple routes."""
        dispatcher = RouteDispatcher()
        dispatcher.add_route(Route(path="/one"))
        dispatcher.add_route(Route(path="/two"))

        assert dispatcher.match("/one") is not None
        assert dispatcher.match("/two") is not None


class TestCreateDefaultRoutes:
    """Tests for default route creation."""

    def test_creates_public_routes(self):
        """Creates standard public routes."""
        routes = create_default_routes()
        paths = [r.path for r in routes]

        assert "/" in paths
        assert "/search" in paths
        assert "/feed.atom" in paths
        assert "/feed.rss" in paths
        assert "/feeds.opml" in paths

    def test_creates_auth_routes(self):
        """Creates OAuth routes."""
        routes = create_default_routes()
        paths = [r.path for r in routes]

        assert "/auth/github" in paths
        assert "/auth/github/callback" in paths

    def test_creates_admin_routes(self):
        """Creates admin routes."""
        routes = create_default_routes()
        admin_routes = [r for r in routes if r.path.startswith("/admin")]

        assert len(admin_routes) > 0
        assert admin_routes[0].prefix is True

    def test_public_routes_cacheable(self):
        """Public routes are cacheable."""
        routes = create_default_routes()
        home_route = next(r for r in routes if r.path == "/")

        assert home_route.cacheable is True

    def test_auth_routes_not_cacheable(self):
        """Auth routes are not cacheable."""
        routes = create_default_routes()
        auth_route = next(r for r in routes if r.path == "/auth/github")

        assert auth_route.cacheable is False

    def test_lite_mode_flags(self):
        """Correct routes are marked as lite mode disabled."""
        routes = create_default_routes()

        search_route = next(r for r in routes if r.path == "/search")
        assert search_route.lite_mode_disabled is True

        home_route = next(r for r in routes if r.path == "/")
        assert home_route.lite_mode_disabled is False


class TestRouteDispatcher404:
    """Tests for 404 handling."""

    def test_unknown_route_returns_none(self):
        """Unknown routes return None for 404 handling."""
        routes = create_default_routes()
        dispatcher = RouteDispatcher(routes)

        # Random paths that don't exist
        assert dispatcher.match("/random/path") is None
        assert dispatcher.match("/api/v1/something") is None
        assert dispatcher.match("/index.php") is None

    def test_empty_dispatcher(self):
        """Empty dispatcher always returns None."""
        dispatcher = RouteDispatcher()

        assert dispatcher.match("/") is None
        assert dispatcher.match("/anything") is None
