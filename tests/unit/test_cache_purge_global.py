# tests/unit/test_cache_purge_global.py
"""Tests for global cache purging via the Cloudflare REST API.

RED phase: These tests verify the dual-layer purge strategy:
- Layer 1: Global purge via Cloudflare Purge API (when secrets configured)
- Layer 2: Local PoP purge via Cache API (always, as fallback)

And graceful degradation across instance types:
- Custom domain + secrets → full global purge
- Custom domain + no secrets → local PoP only
- workers.dev (no zone) → no-op
- No PLANET_URL → entire method is a no-op
"""

from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import make_authenticated_worker

# ============================================================================
# Boundary-layer tests for purge_edge_cache_global()
# ============================================================================


class TestPurgeEdgeCacheGlobal:
    """Test the purge_edge_cache_global boundary-layer function."""

    @pytest.mark.asyncio
    async def test_returns_true_on_success(self):
        """Returns True when the API returns 200."""
        from wrappers import purge_edge_cache_global

        with patch("wrappers.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=type("R", (), {"status_code": 200})())
            mock_client_cls.return_value = mock_client

            result = await purge_edge_cache_global("zone123", "token456", ["https://example.com/"])
            assert result is True
            assert isinstance(result, bool)
            mock_client.post.assert_called_once()
            # Verify Content-Type header is set for JSON payload
            call_args = mock_client.post.call_args
            headers = call_args[1].get("headers", {})
            assert headers.get("Content-Type") == "application/json"

    @pytest.mark.asyncio
    async def test_returns_false_on_403(self):
        """Returns False when the API returns 403 (forbidden)."""
        from wrappers import purge_edge_cache_global

        with patch("wrappers.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=type("R", (), {"status_code": 403})())
            mock_client_cls.return_value = mock_client

            result = await purge_edge_cache_global("zone123", "token456", ["https://example.com/"])
            assert result is False
            assert isinstance(result, bool)
            # Verify the API was still called (failure is based on response, not lack of call)
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_on_500(self):
        """Returns False when the API returns 500 (server error)."""
        from wrappers import purge_edge_cache_global

        with patch("wrappers.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=type("R", (), {"status_code": 500})())
            mock_client_cls.return_value = mock_client

            result = await purge_edge_cache_global("zone123", "token456", ["https://example.com/"])
            assert result is False
            assert isinstance(result, bool)
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_sends_correct_api_url(self):
        """Calls the correct Cloudflare API endpoint."""
        from wrappers import purge_edge_cache_global

        with patch("wrappers.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=type("R", (), {"status_code": 200})())
            mock_client_cls.return_value = mock_client

            await purge_edge_cache_global("my-zone-id", "my-token", ["https://example.com/"])

            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            url = call_args[0][0] if call_args[0] else call_args[1].get("url")
            assert url == "https://api.cloudflare.com/client/v4/zones/my-zone-id/purge_cache"
            # Verify zone_id is embedded in the URL, not sent as a separate parameter
            assert "my-zone-id" in url
            assert url.startswith("https://api.cloudflare.com/client/v4/zones/")
            assert url.endswith("/purge_cache")

    @pytest.mark.asyncio
    async def test_sends_bearer_auth(self):
        """Sends Authorization: Bearer header."""
        from wrappers import purge_edge_cache_global

        with patch("wrappers.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=type("R", (), {"status_code": 200})())
            mock_client_cls.return_value = mock_client

            await purge_edge_cache_global("zone123", "my-secret-token", ["https://example.com/"])

            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            headers = call_args[1].get("headers", {})
            assert headers.get("Authorization") == "Bearer my-secret-token"
            # Verify the token is in Bearer format, not raw
            assert headers["Authorization"].startswith("Bearer ")
            # Verify Content-Type is set for JSON
            assert headers.get("Content-Type") == "application/json"

    @pytest.mark.asyncio
    async def test_sends_files_in_json_body(self):
        """Sends {"files": [...]} in the request body."""
        from wrappers import purge_edge_cache_global

        with patch("wrappers.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=type("R", (), {"status_code": 200})())
            mock_client_cls.return_value = mock_client

            urls = ["https://example.com/", "https://example.com/titles"]
            await purge_edge_cache_global("zone123", "token456", urls)

            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            json_body = call_args[1].get("json", {})
            assert json_body == {"files": urls}
            # Verify the body key is "files" (Cloudflare API requirement), not "urls" or "paths"
            assert "files" in json_body
            assert len(json_body["files"]) == 2
            # Verify URLs are full URLs, not bare paths
            for url in json_body["files"]:
                assert url.startswith("https://"), f"URL must be absolute: {url}"

    @pytest.mark.asyncio
    async def test_raises_on_network_error(self):
        """Does not catch network errors — caller is responsible."""
        from wrappers import purge_edge_cache_global

        with patch("wrappers.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=ConnectionError("DNS failed"))
            mock_client_cls.return_value = mock_client

            with pytest.raises(ConnectionError, match="DNS failed"):
                await purge_edge_cache_global("zone123", "token456", ["https://example.com/"])
            # Verify the post was attempted (error came from the call, not before it)
            mock_client.post.assert_called_once()


# ============================================================================
# Orchestrator tests: _purge_edge_cache() dual-layer behavior
# ============================================================================


class TestPurgeOrchestrator:
    """Test the _purge_edge_cache() dual-layer strategy."""

    @pytest.mark.asyncio
    async def test_both_secrets_set_calls_both_layers(self):
        """When zone_id + api_token are set, calls global then local."""
        worker, env, _ = make_authenticated_worker()
        env.CLOUDFLARE_ZONE_ID = "zone123"
        env.CLOUDFLARE_API_TOKEN = "token456"

        with (
            patch("src.main.purge_edge_cache_global", new_callable=AsyncMock) as mock_global,
            patch("src.main.purge_edge_cache", new_callable=AsyncMock) as mock_local,
        ):
            mock_global.return_value = True
            result = await worker._purge_edge_cache()

            # Method returns None (void)
            assert result is None
            mock_global.assert_awaited_once()
            mock_local.assert_awaited_once()
            # Verify global purge received correct zone_id and api_token
            global_args = mock_global.call_args[0]
            assert global_args[0] == "zone123"
            assert global_args[1] == "token456"
            # Verify global purge received a list of URLs
            assert isinstance(global_args[2], list)
            assert len(global_args[2]) > 0
            # Verify local purge received the base URL and CACHEABLE_PATHS
            local_args = mock_local.call_args[0]
            assert local_args[0] == "https://test.example.com"
            from src.main import CACHEABLE_PATHS

            assert local_args[1] == CACHEABLE_PATHS

    @pytest.mark.asyncio
    async def test_no_zone_id_skips_global(self):
        """When zone_id is missing, skips global, runs local."""
        worker, env, _ = make_authenticated_worker()
        env.CLOUDFLARE_ZONE_ID = ""
        env.CLOUDFLARE_API_TOKEN = "token456"

        with (
            patch("src.main.purge_edge_cache_global", new_callable=AsyncMock) as mock_global,
            patch("src.main.purge_edge_cache", new_callable=AsyncMock) as mock_local,
        ):
            result = await worker._purge_edge_cache()

            assert result is None
            mock_global.assert_not_awaited()
            mock_local.assert_awaited_once()
            # Verify local purge still gets correct base URL
            assert mock_local.call_args[0][0] == "https://test.example.com"
            assert mock_global.call_count == 0

    @pytest.mark.asyncio
    async def test_no_api_token_skips_global(self):
        """When api_token is missing, skips global, runs local."""
        worker, env, _ = make_authenticated_worker()
        env.CLOUDFLARE_ZONE_ID = "zone123"
        env.CLOUDFLARE_API_TOKEN = ""

        with (
            patch("src.main.purge_edge_cache_global", new_callable=AsyncMock) as mock_global,
            patch("src.main.purge_edge_cache", new_callable=AsyncMock) as mock_local,
        ):
            result = await worker._purge_edge_cache()

            assert result is None
            mock_global.assert_not_awaited()
            mock_local.assert_awaited_once()
            assert mock_local.call_args[0][0] == "https://test.example.com"
            assert mock_global.call_count == 0

    @pytest.mark.asyncio
    async def test_global_failure_still_runs_local(self):
        """When global purge raises, local purge still runs."""
        worker, env, _ = make_authenticated_worker()
        env.CLOUDFLARE_ZONE_ID = "zone123"
        env.CLOUDFLARE_API_TOKEN = "token456"

        with (
            patch(
                "src.main.purge_edge_cache_global",
                new_callable=AsyncMock,
                side_effect=Exception("API timeout"),
            ),
            patch("src.main.purge_edge_cache", new_callable=AsyncMock) as mock_local,
        ):
            # Should not raise despite global exception
            result = await worker._purge_edge_cache()
            assert result is None
            mock_local.assert_awaited_once()
            # Verify local purge is called even after global exception
            assert mock_local.call_args[0][0] == "https://test.example.com"

    @pytest.mark.asyncio
    async def test_global_returns_false_still_runs_local(self):
        """When global purge returns False (API error), local purge still runs."""
        worker, env, _ = make_authenticated_worker()
        env.CLOUDFLARE_ZONE_ID = "zone123"
        env.CLOUDFLARE_API_TOKEN = "token456"

        with (
            patch(
                "src.main.purge_edge_cache_global",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch("src.main.purge_edge_cache", new_callable=AsyncMock) as mock_local,
        ):
            result = await worker._purge_edge_cache()
            assert result is None
            mock_local.assert_awaited_once()
            assert mock_local.call_args[0][0] == "https://test.example.com"


# ============================================================================
# Instance-type degradation tests
# ============================================================================


class TestInstanceTypeDegradation:
    """Verify purge degrades gracefully across all instance types.

    Each test simulates a different deployment configuration and verifies
    the correct layers run (or don't run).
    """

    @pytest.mark.asyncio
    async def test_production_with_secrets(self):
        """Production (custom domain + both secrets) → both layers run."""
        worker, env, _ = make_authenticated_worker()
        env.PLANET_URL = "https://www.planetcloudflare.dev"
        env.CLOUDFLARE_ZONE_ID = "abc123"
        env.CLOUDFLARE_API_TOKEN = "token789"

        with (
            patch("src.main.purge_edge_cache_global", new_callable=AsyncMock) as mock_global,
            patch("src.main.purge_edge_cache", new_callable=AsyncMock) as mock_local,
        ):
            mock_global.return_value = True
            result = await worker._purge_edge_cache()

            assert result is None
            mock_global.assert_awaited_once()
            mock_local.assert_awaited_once()
            # Verify global purge receives the production zone and token
            global_args = mock_global.call_args[0]
            assert global_args[0] == "abc123"
            assert global_args[1] == "token789"
            # Verify URLs are built from the production PLANET_URL
            global_urls = global_args[2]
            assert all(u.startswith("https://www.planetcloudflare.dev") for u in global_urls)

    @pytest.mark.asyncio
    async def test_production_without_secrets(self):
        """Production (custom domain, no secrets) → local only."""
        worker, env, _ = make_authenticated_worker()
        env.PLANET_URL = "https://www.planetcloudflare.dev"
        # No zone/token secrets

        with (
            patch("src.main.purge_edge_cache_global", new_callable=AsyncMock) as mock_global,
            patch("src.main.purge_edge_cache", new_callable=AsyncMock) as mock_local,
        ):
            result = await worker._purge_edge_cache()

            assert result is None
            mock_global.assert_not_awaited()
            mock_local.assert_awaited_once()
            # Local purge still gets the production URL
            assert mock_local.call_args[0][0] == "https://www.planetcloudflare.dev"
            assert mock_global.call_count == 0

    @pytest.mark.asyncio
    async def test_workers_dev_instance(self):
        """workers.dev (no zone) → local purge runs but is no-op in practice."""
        worker, env, _ = make_authenticated_worker()
        env.PLANET_URL = "https://test-planet.adewale-883.workers.dev"
        # No zone/token secrets (workers.dev has no zone)

        with (
            patch("src.main.purge_edge_cache_global", new_callable=AsyncMock) as mock_global,
            patch("src.main.purge_edge_cache", new_callable=AsyncMock) as mock_local,
        ):
            result = await worker._purge_edge_cache()

            assert result is None
            mock_global.assert_not_awaited()
            assert mock_global.call_count == 0
            # Local purge runs but is a no-op on workers.dev
            mock_local.assert_awaited_once()
            # Verify the workers.dev URL is passed to local purge
            assert mock_local.call_args[0][0] == "https://test-planet.adewale-883.workers.dev"

    @pytest.mark.asyncio
    async def test_no_planet_url(self):
        """No PLANET_URL → entire method is a no-op."""
        worker, env, _ = make_authenticated_worker()
        env.PLANET_URL = ""

        with (
            patch("src.main.purge_edge_cache_global", new_callable=AsyncMock) as mock_global,
            patch("src.main.purge_edge_cache", new_callable=AsyncMock) as mock_local,
        ):
            result = await worker._purge_edge_cache()

            assert result is None
            mock_global.assert_not_awaited()
            mock_local.assert_not_awaited()
            # Verify neither function received any calls at all
            assert mock_global.call_count == 0
            assert mock_local.call_count == 0

    @pytest.mark.asyncio
    async def test_lite_mode_instance(self):
        """Lite-mode instance (e.g., planet-python) without secrets → local only."""
        worker, env, _ = make_authenticated_worker()
        env.PLANET_URL = "https://planetpython.org"
        # Lite mode instances typically don't have zone secrets

        with (
            patch("src.main.purge_edge_cache_global", new_callable=AsyncMock) as mock_global,
            patch("src.main.purge_edge_cache", new_callable=AsyncMock) as mock_local,
        ):
            result = await worker._purge_edge_cache()

            assert result is None
            mock_global.assert_not_awaited()
            assert mock_global.call_count == 0
            mock_local.assert_awaited_once()
            # Verify lite-mode URL is passed correctly
            assert mock_local.call_args[0][0] == "https://planetpython.org"

    @pytest.mark.asyncio
    async def test_global_urls_include_all_cacheable_paths(self):
        """Global purge sends full URLs for all CACHEABLE_PATHS."""
        from src.main import CACHEABLE_PATHS

        worker, env, _ = make_authenticated_worker()
        env.PLANET_URL = "https://www.planetcloudflare.dev"
        env.CLOUDFLARE_ZONE_ID = "zone123"
        env.CLOUDFLARE_API_TOKEN = "token456"

        with (
            patch("src.main.purge_edge_cache_global", new_callable=AsyncMock) as mock_global,
            patch("src.main.purge_edge_cache", new_callable=AsyncMock),
        ):
            mock_global.return_value = True
            await worker._purge_edge_cache()

            call_args = mock_global.call_args
            urls = call_args[0][2]  # Third positional arg: urls list
            expected = [f"https://www.planetcloudflare.dev{p}" for p in CACHEABLE_PATHS]
            assert urls == expected
            # Verify all four expected paths are present
            assert len(urls) == len(CACHEABLE_PATHS)
            # Verify each URL is absolute and has the correct base
            for url in urls:
                assert (
                    url.startswith("https://www.planetcloudflare.dev/")
                    or url == "https://www.planetcloudflare.dev/"
                )
