"""Application emoji failures must preserve startup and text fallbacks."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import discord
import pytest

from src.bot import BotFraggBot
from src.services.emojis import ApplicationEmojiService
from tests.helpers import _localized_bot


@pytest.mark.parametrize(
    "failure", [aiohttp.ServerDisconnectedError, TimeoutError, OSError]
)
@pytest.mark.parametrize("stage", ["fetch", "create"])
async def test_emoji_transport_failure_does_not_stop_startup(
    monkeypatch, failure, stage
):
    clock = [1000]
    monkeypatch.setattr("src.services.emojis.time.monotonic", lambda: clock[0])
    client = SimpleNamespace(
        fetch_application_emojis=AsyncMock(return_value=[]),
        create_application_emoji=AsyncMock(side_effect=failure("Synthetic failure")),
    )
    if stage == "fetch":
        client.fetch_application_emojis.side_effect = failure("Synthetic failure")
    service = ApplicationEmojiService(client)
    bot = _localized_bot(
        config=SimpleNamespace(app_env="test", auto_sync_commands=False),
        riot_http=SimpleNamespace(start=AsyncMock()),
        auth=SimpleNamespace(refresh_version=AsyncMock()),
        catalog=SimpleNamespace(load=AsyncMock()),
        emoji_service=service,
        add_dynamic_items=lambda *_: None,
        load_extension=AsyncMock(),
        tree=SimpleNamespace(set_translator=AsyncMock()),
    )
    monkeypatch.setattr("src.bot.connect_database", AsyncMock())

    await BotFraggBot.setup_hook(bot)

    assert bot.load_extension.await_count == 14
    assert await service.currency("vp") == ""
    assert await service.battlepass_bars() == ("", "")
    assert service.skin_name("Synthetic skin", None) == "Synthetic skin"
    client.create_application_emoji.side_effect = None
    client.create_application_emoji.return_value = "<:vp:123>"
    clock[0] += 30
    assert await service.currency("vp") == "<:vp:123>"


@pytest.mark.parametrize(
    "failure",
    [discord.Forbidden, aiohttp.ServerDisconnectedError, TimeoutError, OSError],
)
async def test_emoji_failures_use_per_emoji_cooldown_and_recover(monkeypatch, failure):
    clock = [1000]
    monkeypatch.setattr("src.services.emojis.time.monotonic", lambda: clock[0])
    error = (
        failure(SimpleNamespace(status=403, reason="Forbidden"), "Synthetic denial")
        if failure is discord.Forbidden
        else failure("Synthetic outage")
    )
    create = AsyncMock(side_effect=[error, error, "<:vp:123>"])
    service = ApplicationEmojiService(SimpleNamespace(create_application_emoji=create))
    assert (
        await asyncio.gather(*(service.currency("vp") for _ in range(10))) == [""] * 10
    )
    create.assert_awaited_once()
    clock[0] += 29
    assert await service.currency("vp") == ""
    create.assert_awaited_once()
    assert await service.currency("kc") == ""
    assert create.await_count == 2
    clock[0] += 1
    assert (
        await asyncio.gather(*(service.currency("vp") for _ in range(10)))
        == ["<:vp:123>"] * 10
    )
    assert create.await_count == 3
    assert await service.currency("vp") == "<:vp:123>"
    assert create.await_count == 3
