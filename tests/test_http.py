"""HTTP decoding and rate-limit regressions using synthetic localhost responses."""

import asyncio
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from discord.ext.tasks import ExponentialBackoff

from src.cogs.tasks import TasksCog
from src.services.auth import AuthService
from src.services.http import HTTPClient, HTTPFailure, _safe_log_url


@asynccontextmanager
async def response_server(body, *, status=200, retry_after=None):
    async def respond(request):
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if retry_after is not None:
            headers["Retry-After"] = retry_after
        return web.Response(body=body, status=status, headers=headers)

    app = web.Application()
    app.router.add_get("/synthetic", respond)
    runner = web.AppRunner(app)
    await runner.setup()
    try:
        await web.TCPSite(runner, "127.0.0.1", 0).start()
        yield f"http://127.0.0.1:{runner.addresses[0][1]}/synthetic"
    finally:
        await runner.cleanup()


def client():
    return HTTPClient(
        NS(
            http_timeout_seconds=2,
            log_urls=False,
            rate_limit_backoff_seconds=60,
            rate_limit_cap_seconds=3600,
        )
    )


@pytest.mark.parametrize("status", [200, 502])
async def test_undecodable_body_is_a_transport_failure(status):
    async with response_server(b"\xff\xfe", status=status) as url:
        http = client()
        await http.start()
        try:
            with pytest.raises(HTTPFailure):
                await http.request("GET", url)
        finally:
            await http.close()


async def test_decodable_non_json_body_keeps_text_fallback():
    async with response_server(b"not json", status=502) as url:
        http = client()
        await http.start()
        try:
            result = await http.request("GET", url)
            assert result.status == 502 and result.data == "not json"
        finally:
            await http.close()


async def test_version_loop_retries_an_undecodable_response(monkeypatch):
    monkeypatch.setattr(ExponentialBackoff, "delay", lambda self: 0)
    async with response_server(b"\xff\xfe", status=502) as url:
        http = client()
        await http.start()
        retried = asyncio.Event()
        calls = 0

        async def request(method, requested_url, **kwargs):
            nonlocal calls
            calls += 1
            if calls > 1:
                retried.set()
            return await http.request(method, url, **kwargs)

        cog = TasksCog(
            NS(
                config=NS(
                    user_agent_interval_minutes=15,
                    game_version_interval_minutes=15,
                    alert_time_utc=datetime.now(UTC).time(),
                    log_flush_interval_seconds=10,
                ),
                auth=AuthService(NS(), NS(request=request), NS()),
                wait_until_ready=AsyncMock(),
            )
        )
        task = cog.version_refresh.start()
        try:
            await asyncio.wait_for(retried.wait(), 2)
            assert not cog.version_refresh.failed()
        finally:
            cog.version_refresh.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await http.close()


@pytest.mark.parametrize("as_date", [False, True])
async def test_retry_after_sets_the_requested_host_cooldown(as_date):
    value = (
        format_datetime(datetime.now(UTC) + timedelta(seconds=600), usegmt=True)
        if as_date
        else "600"
    )
    async with response_server(b"{}", status=429, retry_after=value) as url:
        http = client()
        await http.start()
        try:
            with pytest.raises(HTTPFailure):
                await http.request("GET", url)
            remaining = http._limited_until["127.0.0.1"] - time.monotonic()
            assert 598 <= remaining <= 602
            with pytest.raises(HTTPFailure):
                await http.request("GET", url)
        finally:
            await http.close()


@pytest.mark.parametrize(
    "status, body, content_length",
    [
        (429, b"{}", 2),
        (429, b"\xff\xfe", 2),
        (429, b"not json", 8),
        (429, b"{", 30),
        (200, b'{"error":"rate_limited"}', 24),
    ],
    ids=["valid", "invalid-utf8", "text", "truncated", "body-rate-limit"],
)
async def test_rate_limit_blocks_next_request_despite_broken_body(
    status, body, content_length
):
    requests = 0

    async def respond(reader, writer):
        nonlocal requests
        try:
            await reader.readuntil(b"\r\n\r\n")
            requests += 1
            writer.write(
                (
                    f"HTTP/1.1 {status} Synthetic\r\n"
                    "Content-Type: application/json; charset=utf-8\r\n"
                    "Retry-After: 600\r\n"
                    f"Content-Length: {content_length}\r\n"
                    "Connection: close\r\n\r\n"
                ).encode()
                + body
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async with await asyncio.start_server(respond, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        http = client()
        await http.start()
        try:
            for _ in range(2):
                with pytest.raises(HTTPFailure, match="Rate limited"):
                    await http.request("GET", f"http://127.0.0.1:{port}/synthetic")
                remaining = http._limited_until["127.0.0.1"] - time.monotonic()
                assert 598 <= remaining <= 602
            assert requests == 1
        finally:
            await http.close()


@pytest.mark.parametrize("status", [200, 429])
@pytest.mark.parametrize("late_seconds, early_seconds", [(1, 600), (600, 1)])
async def test_overlapping_rate_limits_preserve_the_longest_cooldown(
    status, late_seconds, early_seconds
):
    arrived = asyncio.Event()
    release = asyncio.Event()
    requests = 0

    async def respond(request):
        nonlocal requests
        requests += 1
        if request.path == "/late":
            arrived.set()
            await release.wait()
            seconds = late_seconds
        else:
            seconds = early_seconds
        return web.json_response(
            {"error": "rate_limited"},
            status=status,
            headers={"Retry-After": str(seconds)},
        )

    app = web.Application()
    app.router.add_get("/{path}", respond)
    runner = web.AppRunner(app)
    await runner.setup()
    http = client()
    task = None
    try:
        await http.start()
        await web.TCPSite(runner, "127.0.0.1", 0).start()
        url = f"http://127.0.0.1:{runner.addresses[0][1]}"
        task = asyncio.create_task(http.request("GET", url + "/late"))
        await asyncio.wait_for(arrived.wait(), 2)
        with pytest.raises(HTTPFailure, match="Rate limited"):
            await http.request("GET", url + "/early")
        early_deadline = http._limited_until["127.0.0.1"]
        release.set()
        with pytest.raises(
            HTTPFailure, match=r"Rate limited for (?:59[89]|60[0-2]) seconds"
        ):
            await task
        assert http._limited_until["127.0.0.1"] >= early_deadline
        remaining = http._limited_until["127.0.0.1"] - time.monotonic()
        assert 598 <= remaining <= 602
        with pytest.raises(
            HTTPFailure, match=r"Rate limited for (?:59[89]|60[0-2]) seconds"
        ):
            await http.request("GET", url + "/early")
        assert requests == 2
    finally:
        release.set()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        await http.close()
        await runner.cleanup()


@pytest.mark.parametrize(
    "header, expected",
    [
        (None, 61),
        ("", 61),
        ("invalid", 61),
        ("Wed, 32 Oct 2026 00:10:00 GMT", 61),
        ("0", 1),
        ("-10", 1),
        ("9999", 3600),
        ("Wed, 07 Oct 2026 00:10:00 GMT", 601),
        ("Wednesday, 07-Oct-26 00:10:00 GMT", 601),
        ("Wed Oct  7 00:10:00 2026", 601),
        ("Wed, 07 Oct 2026 01:10:00 +0100", 601),
        ("Wed, 07 Oct 2026 00:00:00 GMT", 1),
        ("Tue, 06 Oct 2026 00:00:00 GMT", 1),
        ("Thu, 08 Oct 2026 00:00:00 GMT", 3600),
    ],
)
def test_retry_after_preserves_fallback_and_clamps(monkeypatch, header, expected):
    monkeypatch.setattr(
        "src.services.http.time.time",
        lambda: datetime(2026, 10, 7, tzinfo=UTC).timestamp(),
    )
    assert client()._retry_after(header) == expected


def test_http_log_urls_remove_account_ids_credentials_and_queries() -> None:
    """Verify that HTTP log urls remove account IDs credentials and queries."""
    puuid = "123e4567-e89b-12d3-a456-426614174000"
    safe_url = _safe_log_url(
        f"https://user:password@pd.na.a.pvp.net/store/v3/storefront/{puuid}"
        "?token=secret"
    )

    assert safe_url == "https://pd.na.a.pvp.net/store/v3/storefront/[Filtered]"
    assert puuid not in safe_url
    assert "password" not in safe_url
    assert "secret" not in safe_url
