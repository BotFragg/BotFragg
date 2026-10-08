"""Behavior checks for models."""

from __future__ import annotations

import pytest
from tortoise.exceptions import IntegrityError

from src.models import (
    CommandInvocation,
    ShardStatusMessage,
    Suggestion,
    SuggestionFollower,
)


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
