"""Behavior and regression checks for bot."""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import discord
import pytest
from cryptography.fernet import Fernet
from discord.ext import commands
from tortoise.exceptions import DBConnectionError

from src.bot import BotFraggBot, BotFraggCommandTree
from src.cogs.dev import DevCog
from src.cogs.events import EventsCog
from src.cogs.extra import ExtraCog
from src.cogs.valorant.accounts import AccountsCog
from src.cogs.valorant.alerts import AlertsCog
from src.cogs.valorant.battlepass import BattlepassCog
from src.cogs.valorant.crosshair import CrosshairCog
from src.cogs.valorant.loadout import LoadoutCog
from src.cogs.valorant.login import LoginCog
from src.cogs.valorant.logout import LogoutCog
from src.cogs.valorant.penalties import PenaltiesCog
from src.cogs.valorant.profile import ProfileCog
from src.cogs.valorant.settings import SettingsCog
from src.cogs.valorant.shop import (
    BalanceCog,
    NightMarketCog,
    ShopCog,
)
from src.cogs.valorant.status import StatusCog
from src.config import Settings
from src.localization import BotFraggTranslator
from src.services.http import HTTPFailure
from tests.helpers import (
    TEST_TRANSLATOR,
    RecordingFollowup,
    RecordingResponse,
    _localized_bot,
    _localized_interaction,
    _text,
    _user,
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
    interaction = _localized_interaction(
        command=None, data={}, response=RecordingResponse()
    )
    await BotFraggCommandTree.on_error(
        SimpleNamespace(
            client=SimpleNamespace(translator=TEST_TRANSLATOR),
            _command_name=BotFraggCommandTree._command_name,
        ),
        interaction,
        RuntimeError("unexpected"),
    )

    assert interaction.response.sent[0]["embed"].description == _text(
        "error-command-failed"
    )
    assert interaction.response.sent[0]["ephemeral"] is True


async def test_links_show_the_fixed_invite_and_project_website() -> None:
    """Verify that links shows the fixed invite URL and the project website."""
    user = SimpleNamespace(
        id=123,
        name="BotFragg",
        display_avatar=SimpleNamespace(url="https://example.com/avatar.png"),
    )
    bot = _localized_bot(
        user=user,
        config=SimpleNamespace(support_url=None, vote_url=None, website_url=None),
    )
    interaction = _localized_interaction(
        response=RecordingResponse(), followup=RecordingFollowup()
    )

    cog = ExtraCog(bot)
    await ExtraCog.links.callback(cog, interaction)

    controls = interaction.followup.sent[0]["view"]
    invite = controls.children[0]
    assert (
        invite.url
        == "https://discord.com/oauth2/authorize?client_id=808657534025072651"
    )

    website = next(button for button in controls.children if button.label == "Website")
    assert website.url == "https://botfragg.imkks.fyi/"

    bot.config.website_url = "https://example.com/community"
    await ExtraCog.links.callback(cog, interaction)
    website = next(
        button
        for button in interaction.followup.sent[1]["view"].children
        if button.label == "Website"
    )
    assert website.url == "https://example.com/community"
    assert interaction.response.deferred == [{"thinking": True, "ephemeral": False}] * 2


async def test_donate_buttons_point_at_the_funding_pages() -> None:
    """Verify that donate exposes Ko-fi and GitHub Sponsors as link buttons."""
    user = SimpleNamespace(
        id=123,
        name="BotFragg",
        display_avatar=SimpleNamespace(url="https://example.com/avatar.png"),
    )
    bot = _localized_bot(
        user=user,
        config=SimpleNamespace(support_url=None, vote_url=None, website_url=None),
    )
    interaction = _localized_interaction(
        response=RecordingResponse(), followup=RecordingFollowup()
    )

    await ExtraCog.donate.callback(ExtraCog(bot), interaction)

    assert interaction.response.deferred == [{"thinking": True, "ephemeral": False}]
    controls = interaction.followup.sent[0]["view"]
    assert [button.url for button in controls.children] == [
        "https://ko-fi.com/kumkashree",
        "https://github.com/sponsors/BotFragg",
    ]
    assert all(button.label for button in controls.children)


def test_command_name_includes_the_subcommand_path() -> None:
    """Verify that logged command names include subcommands."""
    assert (
        BotFraggCommandTree._command_name(
            {"name": "settings", "options": [{"type": 1, "name": "view"}]}
        )
        == "settings.view"
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
    monkeypatch.setattr(commands.AutoShardedBot, "close", close_discord)

    await bot.close()

    assert events == ["extensions", "http", "database"]


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
        CrosshairCog(bot),
        AlertsCog(bot),
        BattlepassCog(bot),
        PenaltiesCog(bot),
        StatusCog(bot),
        ProfileCog(bot),
        LoadoutCog(bot),
        ExtraCog(bot),
        DevCog(bot),
    ):
        await bot.add_cog(cog)
    assert {command.name for command in bot.tree.get_commands()} == {
        "login",
        "logout",
        "deletedata",
        "donate",
        "account",
        "accounts",
        "settings",
        "shop",
        "crosshair",
        "bundles",
        "nightmarket",
        "balance",
        "alert",
        "alerts",
        "testalerts",
        "battlepass",
        "missions",
        "penalties",
        "status",
        "profile",
        "loadout",
        "ping",
        "botinfo",
        "help",
        "links",
        "dev",
    }


async def test_ping_uses_database_probe_and_keeps_latency_embed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that ping uses database probe and keeps latency embed."""
    probed = False

    async def ping_database() -> None:
        """Stub and record the database health check."""
        nonlocal probed
        probed = True

    monkeypatch.setattr("src.cogs.extra.ping_database", ping_database)
    bot = _localized_bot(
        get_shard=lambda shard_id: SimpleNamespace(latency=0.041), latency=0.2
    )
    interaction = _localized_interaction(
        response=RecordingResponse(),
        followup=RecordingFollowup(),
        guild=SimpleNamespace(shard_id=3),
    )

    await ExtraCog.ping.callback(ExtraCog(bot), interaction)

    card = interaction.followup.sent[0]["embed"]
    assert interaction.response.deferred == [{"thinking": True, "ephemeral": False}]
    assert probed
    assert card.title == "🏓 Pong"
    assert [field.name for field in card.fields] == [
        "Websocket latency",
        "Database latency",
    ]
    assert card.fields[0].value == "41ms"
    assert card.fields[1].value.endswith("ms")


@pytest.mark.parametrize("failure", ["stalled", "unreachable"])
async def test_ping_reports_an_unavailable_database(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    """A stalled or unreachable database probe must show as unavailable."""

    async def stalled() -> None:
        """Never return before the probe timeout."""
        await asyncio.sleep(60)

    async def unavailable() -> None:
        """Fail the way a closed pool or refused connection does."""
        raise DBConnectionError("synthetic outage")

    if failure == "stalled":
        monkeypatch.setattr("src.cogs.extra.ping_database", stalled)
        monkeypatch.setattr("src.cogs.extra.PING_TIMEOUT_SECONDS", 0.01)
    else:
        monkeypatch.setattr("src.cogs.extra.ping_database", unavailable)
    bot = _localized_bot(
        get_shard=lambda _shard_id: SimpleNamespace(latency=0.041), latency=0.2
    )
    interaction = _localized_interaction(
        response=RecordingResponse(),
        followup=RecordingFollowup(),
        guild=SimpleNamespace(shard_id=3),
    )

    await ExtraCog.ping.callback(ExtraCog(bot), interaction)

    assert interaction.response.deferred == [{"thinking": True, "ephemeral": False}]
    card = interaction.followup.sent[0]["embed"]
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
    setup_order: list[str] = []

    async def connect_database(settings: Settings, *, generate_schemas: bool) -> None:
        """Capture the settings passed to database initialization."""
        setup_order.append("database")
        database_call["settings"] = settings
        database_call["generate_schemas"] = generate_schemas

    async def load_notices() -> None:
        """Record the notice-state load that follows database initialization."""
        setup_order.append("notices")

    async def no_op(*args: object, **kwargs: object) -> None:
        """Provide an intentionally empty callback for this test."""
        return None

    monkeypatch.setattr("src.bot.connect_database", connect_database)
    monkeypatch.setattr(bot.dev_notices, "load", load_notices)
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
    assert setup_order[:2] == ["database", "notices"]


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
    interaction = _localized_interaction(client=bot, user=_user(2))

    await ExtraCog.help.callback(cog, interaction)
    await ExtraCog.help.callback(cog, interaction)

    assert fetch.await_count == 1
