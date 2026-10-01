"""Shared Riot HTTP transport with URL redaction and per-host rate-limit backoff."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import aiohttp

from ..config import Settings

log = logging.getLogger(__name__)


def _safe_log_url(url: str) -> str:
    """Remove credentials, query data, and UUID path segments from a URL."""
    parsed = urlsplit(url)
    path = []
    for segment in parsed.path.split("/"):
        try:
            UUID(segment)
        except ValueError:
            path.append(segment)
        else:
            path.append("[Filtered]")
    return parsed._replace(
        netloc=parsed.netloc.rsplit("@", 1)[-1],
        path="/".join(path),
        query="",
        fragment="",
    ).geturl()


@dataclass(slots=True)
class HTTPResult:
    """Hold an HTTP response status and decoded body."""

    status: int
    data: Any


class HTTPClient:
    """Own a reusable aiohttp session and normalize transport failures."""

    def __init__(self, config: Settings) -> None:
        """Store request settings and initialize session and rate-limit state."""
        self.config = config
        self.session: aiohttp.ClientSession | None = None
        self._limited_until: dict[str, float] = {}

    async def start(self) -> None:
        """Create the shared aiohttp session with configured timeout and pool limits."""
        timeout = aiohttp.ClientTimeout(total=self.config.http_timeout_seconds)
        connector = aiohttp.TCPConnector(limit=100, ttl_dns_cache=300)
        self.session = aiohttp.ClientSession(timeout=timeout, connector=connector)

    async def close(self) -> None:
        """Close the shared session when it has been started and remains open."""
        if self.session and not self.session.closed:
            await self.session.close()

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: Any = None,
        data: Any = None,
    ) -> HTTPResult:
        """Send a request, decode its body, and apply per-host rate-limit backoff.

        Raises:
            RuntimeError: If the client has not been started.
            HTTPFailure: If the request is rate-limited, times out, or fails at the
                transport layer.
        """
        if not self.session:
            raise RuntimeError("HTTP client is not started")
        host = urlsplit(url).hostname or "unknown"
        retry_at = self._limited_until.get(host, 0)
        if retry_at > time.monotonic():
            raise HTTPFailure(
                f"Rate limited for {retry_at - time.monotonic():.0f} seconds"
            )
        if self.config.log_urls:
            log.info("%s %s", method, _safe_log_url(url))
        try:
            async with self.session.request(
                method, url, headers=headers, json=json, data=data
            ) as response:
                try:
                    body: Any = await response.json(content_type=None)
                except aiohttp.ContentTypeError, ValueError:
                    body = await response.text()
                if response.status == 429 or (
                    isinstance(body, dict) and body.get("error") == "rate_limited"
                ):
                    seconds = self._retry_after(response.headers.get("Retry-After"))
                    self._limited_until[host] = time.monotonic() + seconds
                    raise HTTPFailure(f"Rate limited for {seconds:.0f} seconds")
                return HTTPResult(response.status, body)
        except TimeoutError as exc:
            raise HTTPFailure("Request timed out") from exc
        except aiohttp.ClientError as exc:
            raise HTTPFailure(str(exc)) from exc

    def _retry_after(self, value: str | None) -> int:
        """Parse and clamp a Retry-After value to the configured backoff limit."""
        try:
            seconds = int(value or self.config.rate_limit_backoff_seconds)
        except ValueError:
            seconds = self.config.rate_limit_backoff_seconds
        return min(max(seconds + 1, 1), self.config.rate_limit_cap_seconds)


class HTTPFailure(RuntimeError):
    """Raised for rate limits, transport failures, and bounded request timeouts."""
