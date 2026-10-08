"""Behavior checks for bot."""

from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import discord
import pytest
from cryptography.fernet import Fernet
from discord.ext import commands

from src.bot import BotFraggBot, BotFraggCommandTree
from src.cogs.extra import ExtraCog
from src.cogs.staff import StaffCog
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
from tests.helpers import (
    TEST_LOCALE,
    TEST_TRANSLATOR,
    _localized_bot,
    _localized_interaction,
)


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


async def test_unhandled_prefix_command_error_returns_generic_response() -> None:
    """Verify that unhandled prefix command error returns generic response."""
    sent: list[discord.Embed] = []

    async def send(*, embed: discord.Embed) -> None:
        """Record the follow-up message sent through the fake interaction."""
        sent.append(embed)

    context = SimpleNamespace(
        command=SimpleNamespace(qualified_name="debug"), send=send
    )
    error = commands.CommandInvokeError(RuntimeError("private detail"))

    assert "on_command_error" in BotFraggBot.__dict__
    await BotFraggBot.on_command_error(
        SimpleNamespace(translator=TEST_TRANSLATOR), context, error
    )

    assert sent[0].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "error-command-failed"
    )
    assert "private detail" not in sent[0].description


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
    assert bot.intents.dm_messages and bot.intents.guild_messages
    assert not bot.intents.message_content


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
