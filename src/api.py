"""Read-only HTTP API served by the bot process for the public website.

The listener is opt-in: with ``PUBLIC_API_ENABLED=false`` nothing is built and
no socket is opened. Payloads are rendered from in-memory Discord state by
:mod:`src.services.public_api` and refreshed by one background task, so request
handling never touches the database.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from aiohttp import web
from aiohttp.web_middlewares import Middleware

from .config import ROOT, Settings
from .services import public_api

if TYPE_CHECKING:
    from .bot import BotFraggBot

log = logging.getLogger(__name__)

STATS_PATH = "/v1/stats"
META_PATH = "/v1/meta"
COMMANDS_PATH = "/v1/commands"

REFRESH_INTERVAL_SECONDS = 60
RETRY_AFTER_SECONDS = 5
ETAG_LENGTH = 16

_TTL: dict[str, int] = {
    STATS_PATH: 60,
    META_PATH: 300,
    COMMANDS_PATH: 3600,
}

_Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


@dataclass(frozen=True, slots=True)
class _Payload:
    """Hold one serialized response document and its conditional headers."""

    body: bytes
    etag: str
    cache_control: str
    fingerprint: str


def _cors_middleware(origins: frozenset[str]) -> Middleware:
    """Build a middleware that answers preflights and echoes allowed origins."""

    @web.middleware
    async def cors(request: web.Request, handler: _Handler) -> web.StreamResponse:
        origin = request.headers.get("Origin")
        allowed = origin is not None and origin in origins
        response: web.StreamResponse
        if request.method == "OPTIONS" and request.path in _TTL:
            response = web.Response(status=204)
        else:
            response = await handler(request)
        response.headers["Vary"] = "Origin"
        if allowed and origin is not None:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "If-None-Match"
            response.headers["Access-Control-Expose-Headers"] = "ETag"
            response.headers["Access-Control-Max-Age"] = "86400"
        return response

    return cast("Middleware", cors)


def _fingerprint(document: dict[str, Any]) -> str:
    """Hash a payload while ignoring its volatile ``generatedAt`` timestamp."""
    stable = {key: value for key, value in document.items() if key != "generatedAt"}
    encoded = json.dumps(stable, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class PublicAPI:
    """Serve the three read-only endpoints and keep their payloads fresh."""

    def __init__(self, bot: BotFraggBot, config: Settings) -> None:
        """Bind the bot, its settings, and an empty payload cache."""
        self.bot = bot
        self.config = config
        self._origins = frozenset(config.public_api_allowed_origins)
        self._runner: web.AppRunner | None = None
        self._task: asyncio.Task[None] | None = None
        self._payloads: dict[str, _Payload] = {}
        self._built_at: dict[str, float] = {}
        self._failures: dict[str, str] = {}
        self._version = public_api.installed_version()
        self._locales = public_api.discover_locales(ROOT / "locales")
        self._builders: dict[str, Callable[[], dict[str, Any]]] = {
            STATS_PATH: self._build_stats,
            META_PATH: self._build_meta,
            COMMANDS_PATH: self._build_commands,
        }

    async def start(self) -> None:
        """Bind the listener and start the refresh task; safe to call twice."""
        if self._runner is not None:
            return
        app = self.build_app()
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(
            runner, self.config.public_api_host, self.config.public_api_port
        )
        try:
            await site.start()
        except Exception:
            await runner.cleanup()
            raise
        self._runner = runner
        self._task = asyncio.create_task(self._refresh_loop(), name="public-api")
        log.info(
            "public API listening on %s:%s",
            self.config.public_api_host,
            self.config.public_api_port,
        )

    def build_app(self) -> web.Application:
        """Build the aiohttp application with routes and the CORS middleware."""
        app = web.Application(middlewares=[_cors_middleware(self._origins)])
        for path in _TTL:
            app.router.add_get(path, self._handler(path))
        return app

    async def stop(self) -> None:
        """Cancel the refresh task and release the listener; idempotent."""
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        runner, self._runner = self._runner, None
        if runner is not None:
            await runner.cleanup()

    async def refresh_once(self, *, force: bool = False) -> None:
        """Rebuild every payload whose cache window has elapsed.

        A failed builder keeps the previous document and is retried on the next
        pass, so an upstream outage never publishes zeros. ``generatedAt`` marks
        when the document last changed, so a refresh producing identical content
        keeps the previous body and ETag and clients keep getting 304.
        """
        now = time.monotonic()
        for path, builder in self._builders.items():
            built_at = self._built_at.get(path)
            if not force and built_at is not None and now - built_at < _TTL[path]:
                continue
            try:
                document = builder()
                fingerprint = _fingerprint(document)
                existing = self._payloads.get(path)
                if existing is not None and existing.fingerprint == fingerprint:
                    self._built_at[path] = now
                    self._failures.pop(path, None)
                    continue
                body = json.dumps(document, separators=(",", ":")).encode("utf-8")
                self._payloads[path] = _Payload(
                    body=body,
                    etag=hashlib.sha256(body).hexdigest()[:ETAG_LENGTH],
                    cache_control=f"public, max-age={_TTL[path]}",
                    fingerprint=fingerprint,
                )
                self._built_at[path] = now
                self._failures.pop(path, None)
            except Exception as exc:
                signature = f"{type(exc).__name__}: {exc}"
                if self._failures.get(path) != signature:
                    self._failures[path] = signature
                    log.exception("Could not refresh %s", path)

    async def _refresh_loop(self) -> None:
        """Refresh payloads once the bot is ready, then every minute."""
        await self.bot.wait_until_ready()
        while True:
            await self.refresh_once()
            await asyncio.sleep(REFRESH_INTERVAL_SECONDS)

    def _handler(self, path: str) -> _Handler:
        """Build the route handler serving one cached payload."""

        async def serve(request: web.Request) -> web.StreamResponse:
            payload = self._payloads.get(path)
            if payload is None:
                return web.Response(
                    status=503,
                    headers={"Retry-After": str(RETRY_AFTER_SECONDS)},
                )
            etag = f'"{payload.etag}"'
            headers = {"ETag": etag, "Cache-Control": payload.cache_control}
            candidate = request.headers.get("If-None-Match")
            if candidate is not None and candidate.strip().strip('"') == payload.etag:
                return web.Response(status=304, headers=headers)
            return web.Response(
                body=payload.body,
                headers={**headers, "Content-Type": "application/json"},
            )

        return serve

    def _build_stats(self) -> dict[str, Any]:
        """Render reach counters from cached Discord guild state."""
        guilds = self.bot.guilds
        return public_api.render_stats(
            servers=len(guilds),
            members=sum(guild.member_count or 0 for guild in guilds),
            version=self._version,
        )

    def _build_meta(self) -> dict[str, Any]:
        """Render build, locale, and catalog freshness metadata."""
        return public_api.render_meta(
            version=self._version,
            locales=self._locales,
            client_version=self.bot.catalog.version or None,
            catalog_refreshed_at=self.bot.catalog.loaded_at,
        )

    def _build_commands(self) -> dict[str, Any]:
        """Render the command manifest from the registered command tree."""
        return public_api.render_commands(
            public_api.describe_commands(self.bot.tree.walk_commands()),
        )
