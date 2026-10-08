"""Behavior and regression checks for models."""

from __future__ import annotations

from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest
from tortoise.exceptions import IntegrityError

from src.models import (
    CommandInvocation,
    ShardStatusMessage,
    Suggestion,
    SuggestionFollower,
)
from src.services.auth import AuthService
from src.services.gameplay import GameplayService, GameplayUnavailable
from src.services.http import HTTPFailure


async def test_valid_client_version_recovers_after_bad_response():
    request = AsyncMock(
        side_effect=[
            NS(status=200, data={"data": []}),
            NS(
                status=200,
                data={"data": {"riotClientVersion": "new", "riotClientBuild": "build"}},
            ),
        ]
    )
    auth = AuthService(NS(), NS(request=request), NS())
    with pytest.raises(HTTPFailure):
        await auth.refresh_version()
    await auth.refresh_version()
    assert auth.riot_headers["X-Riot-ClientVersion"] == "new"
    assert auth._user_agent().startswith("RiotClient/build ")


async def test_missing_next_reward_metadata_is_recoverable():
    service = GameplayService(NS(), NS(), NS())
    try:
        result = await service._reward([], 1, "en-US")
    except GameplayUnavailable:
        return
    assert result["name"] is None


@pytest.mark.usefixtures("database")
async def test_command_analytics_keeps_dm_context_nullable() -> None:
    """Verify that command analytics keeps DM context nullable."""
    entry = await CommandInvocation.create(command="shop", user_id=789)
    assert (entry.command, entry.user_id, entry.guild_id, entry.channel_id) == (
        "shop",
        789,
        None,
        None,
    )


@pytest.mark.usefixtures("database")
async def test_suggestion_followers_are_unique_per_user() -> None:
    """Verify that suggestion followers are unique per user."""
    suggestion = await Suggestion.create(author_id=789, content="Add a feature")
    await SuggestionFollower.create(suggestion=suggestion, user_id=456)
    with pytest.raises(IntegrityError):
        await SuggestionFollower.create(suggestion=suggestion, user_id=456)


@pytest.mark.usefixtures("database")
async def test_shard_status_message_is_reused_per_channel() -> None:
    """Verify that shard status message is reused per channel."""
    message, created = await ShardStatusMessage.update_or_create(
        channel_id=123, defaults={"message_id": 456}
    )
    assert (message.message_id, created) == (456, True)
    message, created = await ShardStatusMessage.update_or_create(
        channel_id=123, defaults={"message_id": 789}
    )
    assert (message.message_id, created) == (789, False)
