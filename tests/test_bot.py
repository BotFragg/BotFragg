"""Behavior and regression checks for bot."""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import aiohttp
import discord
import pytest
from cryptography.fernet import Fernet
from discord.ext import commands
from tortoise.exceptions import DBConnectionError

from src.bot import BotFraggBot, BotFraggCommandTree
from src.cogs.events import EventsCog
from src.cogs.extra import ExtraCog
from src.cogs.staff import StaffCog
from src.cogs.suggestions import SuggestionsCog
from src.cogs.valorant.accounts import AccountsCog
from src.cogs.valorant.alerts import AlertsCog
from src.cogs.valorant.battlepass import BattlepassCog
from src.cogs.valorant.login import LoginCog
from src.cogs.valorant.logout import LogoutCog
from src.cogs.valorant.penalties import PenaltiesCog
from src.cogs.valorant.settings import SettingsCog
from src.cogs.valorant.shop import (
    BalanceCog,
    NightMarketCog,
    ShopCog,
)
from src.config import Settings
from src.localization import BotFraggTranslator
from src.services.http import HTTPFailure
from tests.helpers import (
    TEST_LOCALE,
    TEST_TRANSLATOR,
    _localized_bot,
    _localized_interaction,
)


async def test_failed_extension_load_cleans_handlers_and_allows_retry(monkeypatch):
    name = "src.cogs.valorant.accounts"
    for extension in ("accounts", "settings"):
        module = f"src.cogs.valorant.{extension}"
        monkeypatch.setitem(sys.modules, module, sys.modules[module])
        monkeypatch.setattr(
            sys.modules["src.cogs.valorant"], extension, sys.modules[module]
        )
    config = SimpleNamespace(
        shard_count=None, token_encryption_key=Fernet.generate_key().decode()
    )

    async def collision(interaction):
        pass

    async with BotFraggBot(config) as bot:
        await bot.load_extension("src.cogs.valorant.settings")
        existing = dict(bot.component_handlers)
        with pytest.raises(discord.ClientException, match="already loaded"):
            await bot.add_cog(bot.get_cog("SettingsCog"))
        assert bot.component_handlers == existing
        bot.tree.add_command(
            discord.app_commands.Command(
                name="account", description="Synthetic collision", callback=collision
            )
        )
        with pytest.raises(commands.ExtensionFailed):
            await bot.load_extension(name)
        assert bot.get_cog("AccountsCog") is None
        assert bot.component_handlers == existing
        bot.tree.remove_command("account")
        await bot.load_extension(name)
        assert "accounts_page" in bot.component_handlers
        assert all(
            bot.component_handlers[action] == handler
            for action, handler in existing.items()
        )


@pytest.mark.parametrize(
    "extension", ["accounts", "alerts", "login", "penalties", "settings", "shop"]
)
async def test_command_extensions_unload_and_reload_without_stale_handlers(
    extension, monkeypatch
):
    name = f"src.cogs.valorant.{extension}"
    # Restore collection-time imports after exercising Discord's module replacement.
    monkeypatch.setitem(sys.modules, name, sys.modules[name])
    monkeypatch.setattr(
        sys.modules["src.cogs.valorant"],
        extension,
        getattr(sys.modules["src.cogs.valorant"], extension),
    )
    config = SimpleNamespace(
        shard_count=None, token_encryption_key=Fernet.generate_key().decode()
    )
    async with BotFraggBot(config) as bot:
        await bot.load_extension(name)
        original = dict(bot.component_handlers)
        assert original
        await bot.unload_extension(name)
        assert not bot.component_handlers
        await bot.load_extension(name)
        await bot.reload_extension(name)
        assert bot.component_handlers.keys() == original.keys()
        assert all(
            bot.component_handlers[action] != handler
            for action, handler in original.items()
        )
        with pytest.raises(RuntimeError, match="already registered"):
            bot.register_component(next(iter(original)), next(iter(original.values())))


async def test_unhandled_app_command_error_returns_ephemeral_response() -> None:
    """Verify that unhandled app command error returns ephemeral response."""
    sent: list[tuple[object, bool]] = []

    class Response:
        """Capture whether an interaction was deferred and whether its initial response was private."""

        def is_done(self) -> bool:
            """Report whether the fake interaction response has been sent."""
            return False

        async def send_message(self, *, embed, ephemeral: bool) -> None:
            """Record the initial message sent through the fake interaction."""
            sent.append((embed, ephemeral))

    interaction = _localized_interaction(command=None, data={}, response=Response())
    await BotFraggCommandTree.on_error(
        SimpleNamespace(
            client=SimpleNamespace(translator=TEST_TRANSLATOR),
            _command_name=BotFraggCommandTree._command_name,
        ),
        interaction,
        RuntimeError("unexpected"),
    )

    assert sent[0][0].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "error-command-failed"
    )
    assert sent[0][1] is True


async def test_links_invite_preserves_zero_permissions() -> None:
    """Verify that links invite preserves zero permissions."""
    sent: dict[str, object] = {}

    class Response:
        """Capture whether an interaction was deferred and whether its initial response was private."""

        async def defer(self, *, thinking: bool) -> None:
            """Record that the fake interaction response was deferred."""
            assert thinking

    class Followup:
        """Capture outgoing embeds and privacy flags sent after an interaction's initial response."""

        async def send(self, **kwargs: object) -> None:
            """Record the follow-up message sent through the fake interaction."""
            sent.update(kwargs)

    user = SimpleNamespace(
        id=123,
        name="BotFragg",
        display_avatar=SimpleNamespace(url="https://example.com/avatar.png"),
    )
    bot = _localized_bot(
        user=user,
        config=SimpleNamespace(support_url=None, vote_url=None, website_url=None),
    )
    interaction = _localized_interaction(response=Response(), followup=Followup())

    cog = ExtraCog(bot)
    await ExtraCog.links.callback(cog, interaction)

    controls = sent["view"]
    invite = controls.children[0]
    query = parse_qs(urlparse(invite.url).query)
    assert query["scope"] == ["bot applications.commands"]
    assert query["permissions"] == ["0"]


def test_glitchtip_groups_subcommands_separately() -> None:
    """Verify that GlitchTip groups subcommands separately."""
    assert (
        BotFraggCommandTree._command_name(
            {"name": "suggestion", "options": [{"type": 1, "name": "track"}]}
        )
        == "suggestion.track"
    )


def test_bot_preserves_discord_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that bot preserves Discord HTTP client."""
    monkeypatch.setenv("DISCORD_TOKEN", "test")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    bot = BotFraggBot(Settings.from_env())
    assert hasattr(bot.http, "static_login")
    assert not bot.intents.guild_messages and not bot.intents.dm_messages
    assert not bot.intents.message_content
    assert bot.command_prefix == []


async def test_bot_stops_extensions_before_closing_shared_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that bot stops extensions before closing shared resources."""
    monkeypatch.setenv("DISCORD_TOKEN", "test")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    bot = BotFraggBot(Settings.from_env())
    events: list[str] = []

    class HTTP:
        """Stub the shared Riot client so request handling and shutdown can be observed."""

        async def close(self) -> None:
            """Record that the fake client or database connection was closed."""
            events.append("http")

    bot.riot_http = HTTP()

    async def close_database() -> None:
        """Record database shutdown during bot cleanup."""
        events.append("database")

    async def close_discord(_bot) -> None:
        """Record Discord client shutdown during bot cleanup."""
        events.append("extensions")

    monkeypatch.setattr("src.bot.close_database", close_database)
    monkeypatch.setattr("src.bot.flush_monitoring", lambda: events.append("monitoring"))
    monkeypatch.setattr(commands.AutoShardedBot, "close", close_discord)

    await bot.close()

    assert events == ["extensions", "http", "database", "monitoring"]


async def test_initial_release_command_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that the initial release command groups remain available."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DISCORD_TOKEN", "test")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    bot = BotFraggBot(Settings.from_env())
    for cog in (
        LoginCog(bot),
        LogoutCog(bot),
        AccountsCog(bot),
        SettingsCog(bot),
        ShopCog(bot),
        NightMarketCog(bot),
        BalanceCog(bot),
        AlertsCog(bot),
        BattlepassCog(bot),
        PenaltiesCog(bot),
        ExtraCog(bot),
        SuggestionsCog(bot),
        StaffCog(bot),
    ):
        await bot.add_cog(cog)
    assert {command.name for command in bot.tree.get_commands()} == {
        "login",
        "logout",
        "deletedata",
        "account",
        "accounts",
        "settings",
        "shop",
        "bundles",
        "nightmarket",
        "balance",
        "alert",
        "alerts",
        "testalerts",
        "battlepass",
        "missions",
        "penalties",
        "ping",
        "botinfo",
        "help",
        "links",
        "suggest",
        "suggestion",
        "userinfo",
        "serverinfo",
    }


async def test_ping_uses_database_probe_and_keeps_latency_embed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that ping uses database probe and keeps latency embed."""
    sent: dict[str, object] = {}
    probed = False

    class Response:
        """Capture whether an interaction was deferred and whether its initial response was private."""

        async def defer(self, *, thinking: bool) -> None:
            """Record that the fake interaction response was deferred."""
            sent["thinking"] = thinking

    class Followup:
        """Capture outgoing embeds and privacy flags sent after an interaction's initial response."""

        async def send(self, *, embed: discord.Embed) -> None:
            """Record the follow-up message sent through the fake interaction."""
            sent["embed"] = embed

    async def ping_database() -> None:
        """Stub and record the database health check."""
        nonlocal probed
        probed = True

    monkeypatch.setattr("src.cogs.extra.ping_database", ping_database)
    bot = _localized_bot(
        get_shard=lambda shard_id: SimpleNamespace(latency=0.041), latency=0.2
    )
    interaction = _localized_interaction(
        response=Response(),
        followup=Followup(),
        guild=SimpleNamespace(shard_id=3),
    )

    await ExtraCog.ping.callback(ExtraCog(bot), interaction)

    card = sent["embed"]
    assert sent["thinking"] is True
    assert probed
    assert card.title == "🏓 Pong"
    assert [field.name for field in card.fields] == [
        "Websocket latency",
        "Database latency",
    ]
    assert card.fields[0].value == "41ms"
    assert card.fields[1].value.endswith("ms")


async def test_ping_reports_a_stalled_database_instead_of_hanging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A database probe that never returns must not leave /ping hanging."""
    sent: dict[str, object] = {}

    class Response:
        """Capture whether the interaction was deferred."""

        async def defer(self, *, thinking: bool) -> None:
            """Record the deferral request."""

    class Followup:
        """Capture the embed sent after the probe."""

        async def send(self, *, embed: discord.Embed) -> None:
            """Record the follow-up embed."""
            sent["embed"] = embed

    async def stalled() -> None:
        """Never return before the probe timeout."""
        await asyncio.sleep(60)

    monkeypatch.setattr("src.cogs.extra.ping_database", stalled)
    monkeypatch.setattr("src.cogs.extra.PING_TIMEOUT_SECONDS", 0.01)
    bot = _localized_bot(
        get_shard=lambda _shard_id: SimpleNamespace(latency=0.041), latency=0.2
    )
    interaction = _localized_interaction(
        response=Response(),
        followup=Followup(),
        guild=SimpleNamespace(shard_id=3),
    )

    await ExtraCog.ping.callback(ExtraCog(bot), interaction)

    card = sent["embed"]
    assert card.fields[1].value == "Unavailable"


async def test_ping_reports_an_unreachable_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A database that fails immediately must also show as unavailable."""
    sent: dict[str, object] = {}

    class Response:
        """Capture whether the interaction was deferred."""

        async def defer(self, *, thinking: bool) -> None:
            """Record the deferral request."""

    class Followup:
        """Capture the embed sent after the probe."""

        async def send(self, *, embed: discord.Embed) -> None:
            """Record the follow-up embed."""
            sent["embed"] = embed

    async def unavailable() -> None:
        """Fail the way a closed pool or refused connection does."""
        raise DBConnectionError("synthetic outage")

    monkeypatch.setattr("src.cogs.extra.ping_database", unavailable)
    bot = _localized_bot(
        get_shard=lambda _shard_id: SimpleNamespace(latency=0.041), latency=0.2
    )
    interaction = _localized_interaction(
        response=Response(),
        followup=Followup(),
        guild=SimpleNamespace(shard_id=3),
    )

    await ExtraCog.ping.callback(ExtraCog(bot), interaction)

    card = sent["embed"]
    assert card.fields[1].value == "Unavailable"


async def test_setup_hook_passes_bot_settings_to_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that setup hook passes bot settings to database."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DISCORD_TOKEN", "test")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    bot = BotFraggBot(Settings.from_env())
    database_call: dict[str, object] = {}

    async def connect_database(settings: Settings, *, generate_schemas: bool) -> None:
        """Capture the settings passed to database initialization."""
        database_call["settings"] = settings
        database_call["generate_schemas"] = generate_schemas

    async def no_op(*args: object, **kwargs: object) -> None:
        """Provide an intentionally empty callback for this test."""
        return None

    monkeypatch.setattr("src.bot.connect_database", connect_database)
    monkeypatch.setattr(bot.riot_http, "start", no_op)
    monkeypatch.setattr(bot.auth, "refresh_version", no_op)
    monkeypatch.setattr(bot.catalog, "load", no_op)
    monkeypatch.setattr(bot.emoji_service, "warm", no_op)
    monkeypatch.setattr(bot, "add_dynamic_items", lambda *_: None)
    monkeypatch.setattr(bot, "load_extension", no_op)
    monkeypatch.setattr(bot.tree, "sync", no_op)

    await bot.setup_hook()

    assert database_call == {
        "settings": bot.config,
        "generate_schemas": True,
    }


async def test_shard_webhook_transport_failure_does_not_escape(monkeypatch):
    """A dropped webhook connection must not raise out of the shard listener."""

    class Hook:
        """Stand in for the Discord webhook whose send fails."""

        @classmethod
        def from_url(cls, _url, session=None):
            """Return a webhook double that fails the way aiohttp does."""
            return SimpleNamespace(send=fail)

    async def fail(*_args, **_kwargs):
        raise aiohttp.ServerDisconnectedError("synthetic")

    monkeypatch.setattr("src.cogs.events.discord.Webhook", Hook)
    bot = SimpleNamespace(
        config=SimpleNamespace(shard_log_webhook_url="https://example.invalid/hook"),
        riot_http=SimpleNamespace(session=object()),
        shard_count=2,
    )

    await EventsCog(bot)._log_shard_event(0, "connected")


async def test_guild_log_transport_failure_does_not_escape(monkeypatch):
    """A dropped connection while resolving the log channel must not raise."""

    async def fail(*_args, **_kwargs):
        raise aiohttp.ServerDisconnectedError("synthetic")

    bot = SimpleNamespace(
        config=SimpleNamespace(guild_join_log_channel_id=123),
        get_channel=lambda _: None,
        fetch_channel=fail,
        guilds=[],
    )

    await EventsCog(bot)._log_guild_event(
        SimpleNamespace(id=1, name="Guild"), 123, "I've joined a guild!"
    )


async def test_botinfo_retries_soon_after_a_failed_fetch(monkeypatch):
    """A failed commit lookup must not be cached for the full window."""
    from src.cogs.extra import GITHUB_RETRY_SECONDS, ExtraCog

    bot = SimpleNamespace(
        riot_http=SimpleNamespace(
            request=AsyncMock(side_effect=HTTPFailure("synthetic outage"))
        ),
        translator=BotFraggTranslator(),
    )
    cog = ExtraCog(bot)
    monkeypatch.setattr("src.cogs.extra.monotonic", lambda: 1000.0)

    summary = await cog._latest_commit_summary(discord.Locale.american_english)

    assert summary == bot.translator.text(
        discord.Locale.american_english, "botinfo-commits-unavailable"
    )
    assert cog._latest_updates_expires == 1000.0 + GITHUB_RETRY_SECONDS


def test_botinfo_numbers_use_the_locale_grouping() -> None:
    """Source lines and process numbers must render with locale grouping."""
    translator = BotFraggTranslator()

    assert "5.125" in translator.text(
        discord.Locale.german, "botinfo-source-lines", count=5125
    )
    assert "1,5%" in translator.text(
        discord.Locale.german, "botinfo-process-cpu", value=1.5, unit="%"
    )


async def test_botinfo_caps_the_commit_field(monkeypatch):
    """Five long commit lines must not exceed Discord's embed-field limit."""
    from src.cogs.extra import ExtraCog

    bot = SimpleNamespace(riot_http=SimpleNamespace(), translator=BotFraggTranslator())
    cog = ExtraCog(bot)
    monkeypatch.setattr("src.cogs.extra.monotonic", lambda: 0.0)
    cog._latest_updates = [("a" * 64, "x" * 100, None) for _ in range(5)]
    cog._latest_updates_expires = float("inf")

    summary = await cog._latest_commit_summary(discord.Locale.american_english)

    assert len(summary) == 1024
    assert summary.startswith(
        "[`aaaaaaa`](https://github.com/BotFragg/BotFragg/commit/"
    )


async def test_help_fetches_command_mentions_once():
    """The help command must not fetch the application commands on every call."""
    from src.cogs.extra import ExtraCog

    fetch = AsyncMock(return_value=[])
    bot = SimpleNamespace(
        user=SimpleNamespace(
            id=1, display_avatar=SimpleNamespace(url="https://example.com/a.png")
        ),
        tree=SimpleNamespace(fetch_commands=fetch, walk_commands=lambda: []),
        translator=BotFraggTranslator(),
        config=SimpleNamespace(support_url=None, vote_url=None, website_url=None),
    )
    cog = ExtraCog(bot)
    interaction = SimpleNamespace(
        client=bot,
        locale=discord.Locale.american_english,
        user=SimpleNamespace(id=2),
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )

    await ExtraCog.help.callback(cog, interaction)
    await ExtraCog.help.callback(cog, interaction)

    assert fetch.await_count == 1
