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
    """Base class for Cloudflare Workers entrypoints."""

    env: Any

    async def fetch(self, request: Any, *args: Any, **kwargs: Any) -> Response: ...
    async def queue(self, batch: Any, *args: Any, **kwargs: Any) -> None: ...
    async def scheduled(self, event: Any, *args: Any, **kwargs: Any) -> None: ...
