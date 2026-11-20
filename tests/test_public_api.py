"""Public API payload builders, routing, and configuration behavior."""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import Iterator
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

from src.api import PublicAPI
from src.bot import EXTENSIONS, BotFraggBot
from src.config import Settings
from src.services import public_api
from tests.helpers import _localized_bot

STAMP = datetime(2026, 11, 12, 11, 40, tzinfo=UTC)
ALLOWED_ORIGIN = "https://site.test"


class _FakeBot:
    """Minimal bot stand-in exposing only what the API reads."""

    def __init__(self, *, members: list[int] | None = None) -> None:
        self.guilds = [SimpleNamespace(member_count=count) for count in members or []]
        self.catalog = SimpleNamespace(version="11.10.00.1234567", loaded_at=None)
        self.tree = SimpleNamespace(walk_commands=lambda: iter(()))

    async def wait_until_ready(self) -> None:
        """Block forever so the refresh loop stays dormant in tests."""
        await asyncio.Event().wait()


def _settings(**overrides: Any) -> Any:
    """Return a settings-shaped object for the API constructor."""
    values: dict[str, Any] = {
        "public_api_host": "127.0.0.1",
        "public_api_port": 0,
        "public_api_allowed_origins": (ALLOWED_ORIGIN,),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _client(api: PublicAPI) -> TestClient:
    """Wrap the API's application in an in-process test client."""
    return TestClient(TestServer(api.build_app()))


def test_render_stats_publishes_reach_only() -> None:
    """The stats document must carry no usage or per-guild fields."""
    document = public_api.render_stats(
        servers=3, members=42, version="2.0.0", generated_at=STAMP
    )

    assert document == {
        "schemaVersion": 1,
        "generatedAt": "2026-11-12T11:40:00Z",
        "bot": {"version": "2.0.0"},
        "reach": {"servers": 3, "members": 42},
    }
    for key in ("usage", "registeredUsers", "users", "guilds", "topCommands"):
        assert key not in document


def test_render_stats_tolerates_empty_state() -> None:
    """An empty or not-yet-cached guild list must not raise."""
    document = public_api.render_stats(servers=0, members=0, version="unknown")

    assert document["reach"] == {"servers": 0, "members": 0}


def test_render_meta_sorts_locales_and_reports_missing_catalog() -> None:
    """Locale names are sorted and catalog freshness is null before a load."""
    document = public_api.render_meta(
        version="2.0.0",
        locales=["pt-BR", "en-US", "de"],
        client_version=None,
        catalog_refreshed_at=None,
        generated_at=STAMP,
    )

    assert document["locales"] == ["de", "en-US", "pt-BR"]
    assert document["riot"] == {
        "clientVersion": None,
        "catalogRefreshedAt": None,
    }


def test_render_meta_reports_catalog_timestamp() -> None:
    """A loaded catalog exposes its refresh time in ISO-8601 UTC."""
    document = public_api.render_meta(
        version="2.0.0",
        locales=["en-US"],
        client_version="11.10.00.1",
        catalog_refreshed_at=STAMP,
        generated_at=STAMP,
    )

    assert document["riot"]["catalogRefreshedAt"] == "2026-11-12T11:40:00Z"


def _item(
    name: str,
    *,
    qualified_name: str | None = None,
    extras: dict[str, bool] | None = None,
    description: str = "",
    guild_only: bool = False,
    parameters: list[Any] | None = None,
) -> Any:
    """Build a command-tree shaped object without a live Discord client."""
    item = SimpleNamespace(
        name=name,
        qualified_name=qualified_name or name,
        description=description,
        guild_only=guild_only,
        extras=extras or {},
    )
    if parameters is not None:
        item.parameters = [
            SimpleNamespace(name=name, required=required)
            for name, required in parameters
        ]
    return item


def test_describe_commands_excludes_owner_only_and_sorts() -> None:
    """Owner-only commands stay private and output is ordered by qualified name."""
    items: Iterator[Any] = iter(
        [
            _item("b"),
            _item("a", guild_only=True),
            _item("diag", extras={"owner_only": True}),
        ]
    )

    described = public_api.describe_commands(items)

    assert [command.qualified_name for command in described] == ["a", "b"]
    assert described[0].guild_only is True


def test_describe_commands_keeps_public_commands_from_any_module() -> None:
    """Module placement alone must not hide a public command."""
    described = public_api.describe_commands(
        [_item("lobby", extras={"owner_only": False})]
    )

    assert [command.qualified_name for command in described] == ["lobby"]


def test_describe_commands_includes_parameter_shape() -> None:
    """Command parameters are published as name and required flag only."""
    described = public_api.describe_commands(
        [_item("shop", parameters=[("user", False)])]
    )

    assert described[0].params == (public_api.PublicParam(name="user", required=False),)


def test_render_commands_serializes_manifest() -> None:
    """The manifest uses camelCase keys and preserves parameter order."""
    document = public_api.render_commands(
        [
            public_api.PublicCommand(
                name="shop",
                qualified_name="shop",
                description="View your daily shop",
                guild_only=False,
                params=(public_api.PublicParam(name="user", required=False),),
            )
        ],
        generated_at=STAMP,
    )

    assert document["commands"] == [
        {
            "name": "shop",
            "qualifiedName": "shop",
            "description": "View your daily shop",
            "guildOnly": False,
            "params": [{"name": "user", "required": False}],
        }
    ]


async def test_unbuilt_payload_returns_service_unavailable() -> None:
    """Requests before the first refresh answer 503 with a retry hint."""
    api = PublicAPI(_FakeBot(), _settings())
    client = _client(api)
    await client.start_server()
    try:
        response = await client.get("/v1/stats")
        assert response.status == 503
        assert response.headers["Retry-After"] == "5"
    finally:
        await client.close()


async def test_stats_serves_etag_and_304() -> None:
    """The stats document is cacheable and honours If-None-Match."""
    api = PublicAPI(_FakeBot(members=[10, 20]), _settings())
    client = _client(api)
    await client.start_server()
    try:
        await api.refresh_once(force=True)
        response = await client.get("/v1/stats")
        assert response.status == 200
        assert response.headers["Cache-Control"] == "public, max-age=60"
        assert response.headers["Content-Type"] == "application/json"
        etag = response.headers["ETag"]
        body = await response.json()
        assert body["reach"] == {"servers": 2, "members": 30}

        again = await client.get("/v1/stats", headers={"If-None-Match": etag})
        assert again.status == 304
        assert again.headers["ETag"] == etag
    finally:
        await client.close()


async def test_cors_echoes_only_allowlisted_origins() -> None:
    """Allowed origins are echoed with Vary; unknown origins get no header."""
    api = PublicAPI(_FakeBot(), _settings())
    client = _client(api)
    await client.start_server()
    try:
        await api.refresh_once(force=True)
        allowed = await client.get("/v1/stats", headers={"Origin": ALLOWED_ORIGIN})
        assert allowed.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
        assert allowed.headers["Access-Control-Expose-Headers"] == "ETag"
        assert allowed.headers["Vary"] == "Origin"

        denied = await client.get("/v1/stats", headers={"Origin": "https://evil.test"})
        assert "Access-Control-Allow-Origin" not in denied.headers
        assert "Access-Control-Expose-Headers" not in denied.headers

        plain = await client.get("/v1/stats")
        assert plain.headers["Vary"] == "Origin"
        assert denied.headers["Vary"] == "Origin"
    finally:
        await client.close()


async def test_options_preflight_short_circuits() -> None:
    """Preflight requests answer 204 without touching the payload cache."""
    api = PublicAPI(_FakeBot(), _settings())
    client = _client(api)
    await client.start_server()
    try:
        response = await client.options(
            "/v1/commands", headers={"Origin": ALLOWED_ORIGIN}
        )
        assert response.status == 204
    finally:
        await client.close()


async def test_failed_refresh_keeps_previous_payload() -> None:
    """A builder failure must not replace the last good document."""
    api = PublicAPI(_FakeBot(members=[5]), _settings())
    await api.refresh_once(force=True)
    previous = api._payloads["/v1/stats"].body

    def _boom() -> dict[str, Any]:
        raise RuntimeError("upstream down")

    api._builders["/v1/stats"] = _boom
    await api.refresh_once(force=True)

    assert api._payloads["/v1/stats"].body == previous


async def test_identical_refresh_keeps_etag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unchanged document keeps its body, timestamp, and ETag."""
    stamps = itertools.count()
    monkeypatch.setattr(
        public_api,
        "iso_timestamp",
        lambda _value=None: f"2026-11-12T11:40:{next(stamps):02d}Z",
    )
    api = PublicAPI(_FakeBot(members=[5]), _settings())
    await api.refresh_once(force=True)
    first = api._payloads["/v1/stats"]

    await api.refresh_once(force=True)
    second = api._payloads["/v1/stats"]

    assert second.body == first.body
    assert second.etag == first.etag


async def test_changed_document_gets_a_new_etag() -> None:
    """Changed counters must invalidate the cached document."""
    bot = _FakeBot(members=[5])
    api = PublicAPI(bot, _settings())
    await api.refresh_once(force=True)
    first_etag = api._payloads["/v1/stats"].etag

    bot.guilds = [*bot.guilds, SimpleNamespace(member_count=7)]
    await api.refresh_once(force=True)

    assert api._payloads["/v1/stats"].etag != first_etag


async def test_stop_is_idempotent() -> None:
    """Shutdown may run twice without raising."""
    api = PublicAPI(_FakeBot(), _settings())
    await api.start()
    await api.stop()
    await api.stop()


async def test_first_refresh_runs_on_a_fresh_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Machine uptime shorter than a TTL must not postpone the first payload."""
    monkeypatch.setattr("src.api.time.monotonic", lambda: 1.0)
    api = PublicAPI(_FakeBot(members=[3]), _settings())

    await api.refresh_once()

    assert set(api._payloads) == {"/v1/stats", "/v1/meta", "/v1/commands"}


async def test_refresh_respects_cache_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A recent build is skipped and an elapsed window rebuilds, per TTL."""
    clock = [100.0]
    monkeypatch.setattr("src.api.time.monotonic", lambda: clock[0])
    builds = [0]
    api = PublicAPI(_FakeBot(members=[1]), _settings())

    def _counted() -> dict[str, Any]:
        builds[0] += 1
        return public_api.render_stats(servers=1, members=1, version="test")

    api._builders["/v1/stats"] = _counted

    await api.refresh_once()
    assert builds[0] == 1

    clock[0] = 130.0
    await api.refresh_once()
    assert builds[0] == 1, "a build inside the 60 s window must be reused"

    clock[0] = 200.0
    await api.refresh_once()
    assert builds[0] == 2, "an elapsed window must rebuild"


def _setup_bot(*, public_api_enabled: bool) -> Any:
    """Build a stub whose only real behaviour is the setup_hook wiring."""
    return _localized_bot(
        config=SimpleNamespace(
            app_env="test",
            auto_sync_commands=False,
            public_api_enabled=public_api_enabled,
        ),
        riot_http=SimpleNamespace(start=AsyncMock()),
        auth=SimpleNamespace(refresh_version=AsyncMock()),
        catalog=SimpleNamespace(load=AsyncMock()),
        emoji_service=SimpleNamespace(warm=AsyncMock()),
        add_dynamic_items=lambda *_: None,
        load_extension=AsyncMock(),
        tree=SimpleNamespace(set_translator=AsyncMock()),
    )


class _RecordingAPI:
    """Record the lifecycle calls BotFraggBot makes on the public API."""

    fail = False

    def __init__(self, bot: Any, config: Any) -> None:
        """Start with no recorded activity."""
        self.started = 0
        self.stopped = 0

    async def start(self) -> None:
        """Record a start, or fail when the test asks for a bind error."""
        if _RecordingAPI.fail:
            raise RuntimeError("bind failed")
        self.started += 1

    async def stop(self) -> None:
        """Record a stop."""
        self.stopped += 1


async def test_setup_hook_starts_public_api_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An enabled setting must construct, start, and retain the API."""
    bot = _setup_bot(public_api_enabled=True)
    monkeypatch.setattr("src.bot.connect_database", AsyncMock())
    monkeypatch.setattr("src.bot.PublicAPI", _RecordingAPI)

    await BotFraggBot.setup_hook(bot)

    assert bot.api.started == 1


async def test_setup_hook_skips_public_api_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default setting must not build an API at all."""
    bot = _setup_bot(public_api_enabled=False)
    monkeypatch.setattr("src.bot.connect_database", AsyncMock())
    monkeypatch.setattr("src.bot.PublicAPI", _RecordingAPI)

    await BotFraggBot.setup_hook(bot)

    assert getattr(bot, "api", None) is None


async def test_setup_hook_survives_public_api_start_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bind failure is logged and startup continues without the API."""
    bot = _setup_bot(public_api_enabled=True)
    monkeypatch.setattr("src.bot.connect_database", AsyncMock())
    monkeypatch.setattr("src.bot.PublicAPI", _RecordingAPI)
    monkeypatch.setattr(_RecordingAPI, "fail", True)

    await BotFraggBot.setup_hook(bot)

    assert getattr(bot, "api", None) is None
    assert bot.load_extension.await_count == len(EXTENSIONS)


async def test_close_stops_public_api(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shutdown must release the API listener through the exit stack."""
    bot = object.__new__(BotFraggBot)
    api = _RecordingAPI(None, None)
    bot.api = api
    bot.riot_http = SimpleNamespace(close=AsyncMock())
    monkeypatch.setattr("src.bot.close_database", AsyncMock())
    stack = AsyncExitStack()

    bot._push_shutdown_callbacks(stack)
    await stack.aclose()

    assert api.stopped == 1
    assert bot.riot_http.close.await_count == 1


def test_settings_public_api_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """The API is disabled by default with no browser origin allowed."""
    for name in (
        "PUBLIC_API_ENABLED",
        "PUBLIC_API_HOST",
        "PUBLIC_API_PORT",
        "PUBLIC_API_ALLOWED_ORIGINS",
    ):
        monkeypatch.delenv(name, raising=False)

    config = Settings.from_env(require_secrets=False)

    assert config.public_api_enabled is False
    assert config.public_api_host == "0.0.0.0"  # noqa: S104
    assert config.public_api_port == 8081
    assert config.public_api_allowed_origins == ()


@pytest.mark.parametrize("value", ["1", "true", "yes", "on"])
def test_settings_public_api_enabled_values(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Truthy booleans enable the public API."""
    monkeypatch.setenv("PUBLIC_API_ENABLED", value)

    config = Settings.from_env(require_secrets=False)

    assert config.public_api_enabled is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off"])
def test_settings_public_api_disabled_values(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Falsy booleans keep the public API off."""
    monkeypatch.setenv("PUBLIC_API_ENABLED", value)

    config = Settings.from_env(require_secrets=False)

    assert config.public_api_enabled is False


@pytest.mark.parametrize("value", ["0", "65536", "-1", "cloud"])
def test_settings_reject_invalid_public_api_port(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Port bounds are enforced before the listener is built."""
    monkeypatch.setenv("PUBLIC_API_PORT", value)

    with pytest.raises(ValueError, match="PUBLIC_API_PORT"):
        Settings.from_env(require_secrets=False)


@pytest.mark.parametrize("value", ["0.0.0.0/api", "http://localhost", "bad host"])
def test_settings_reject_invalid_public_api_host(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Host values must be a bare hostname or address."""
    monkeypatch.setenv("PUBLIC_API_HOST", value)

    with pytest.raises(ValueError, match="PUBLIC_API_HOST"):
        Settings.from_env(require_secrets=False)


def test_settings_parse_and_dedupe_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    """Origins are normalized, deduplicated, and stripped of trailing slashes."""
    monkeypatch.setenv(
        "PUBLIC_API_ALLOWED_ORIGINS",
        "https://botfragg.gg/, http://localhost:3000, https://botfragg.gg",
    )

    config = Settings.from_env(require_secrets=False)

    assert config.public_api_allowed_origins == (
        "https://botfragg.gg",
        "http://localhost:3000",
    )


def test_settings_normalize_origin_case_and_default_ports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Browsers lowercase hosts and omit default ports, so the allowlist must too."""
    monkeypatch.setenv(
        "PUBLIC_API_ALLOWED_ORIGINS",
        "https://BotFragg.GG:443, https://botfragg.gg, http://LOCALHOST:80",
    )

    config = Settings.from_env(require_secrets=False)

    assert config.public_api_allowed_origins == (
        "https://botfragg.gg",
        "http://localhost",
    )


def test_settings_keep_non_default_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit non-default ports are part of the browser origin."""
    monkeypatch.setenv(
        "PUBLIC_API_ALLOWED_ORIGINS", "https://botfragg.gg:8443, http://localhost:3000"
    )

    config = Settings.from_env(require_secrets=False)

    assert config.public_api_allowed_origins == (
        "https://botfragg.gg:8443",
        "http://localhost:3000",
    )


@pytest.mark.parametrize(
    "value",
    [
        "https://botfragg.gg/path",
        "https://user:pass@botfragg.gg",
        "ftp://botfragg.gg",
        "https://[::1",
    ],
)
def test_settings_reject_invalid_origins(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Origins must be absolute http(s) without userinfo or a path."""
    monkeypatch.setenv("PUBLIC_API_ALLOWED_ORIGINS", value)

    with pytest.raises(ValueError, match="PUBLIC_API_ALLOWED_ORIGINS"):
        Settings.from_env(require_secrets=False)
