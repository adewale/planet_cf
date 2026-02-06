# Type stubs for Cloudflare Workers Python runtime
# https://developers.cloudflare.com/workers/languages/python/

from typing import Any

# Headers can be dict or list of tuples (for multi-value headers like Set-Cookie)
HeadersType = dict[str, str] | list[tuple[str, str]] | None

class Response:
    """Cloudflare Workers Response object."""

    status: int
    body: bytes | str
    headers: dict[str, str]

    def __init__(
        self,
        body: bytes | str = ...,
        status: int = ...,
        headers: HeadersType = ...,
    ) -> None: ...

class WorkerEntrypoint:
    """Base class for Cloudflare Workers entrypoints.

    The Workers runtime calls these handler methods with positional arguments:
    - fetch(request, env, ctx)
    - queue(batch, env, ctx)
    - scheduled(event, env, ctx)

    env and ctx are optional with defaults to support test environments
    where they may not be provided.
    """

    env: Any

    async def fetch(
        self,
        request: Any,
        env: Any = ...,
        ctx: Any = ...,
    ) -> Response: ...
    async def queue(
        self,
        batch: Any,
        env: Any = ...,
        ctx: Any = ...,
    ) -> None: ...
    async def scheduled(
        self,
        event: Any,
        env: Any = ...,
        ctx: Any = ...,
    ) -> None: ...
