"""Tests for command invocation recording and scoped statistics."""

from __future__ import annotations

import pytest

from src.models import CommandInvocation
from src.services.analytics import command_stats, record_command_invocation


@pytest.mark.usefixtures("database")
async def test_record_command_invocation_preserves_dm_context() -> None:
    """Verify that record command invocation preserves DM context."""
    await record_command_invocation(
        command="shop", user_id=789, guild_id=None, channel_id=None
    )

    entry = await CommandInvocation.get(command="shop")
    assert (entry.user_id, entry.guild_id, entry.channel_id) == (789, None, None)


@pytest.mark.usefixtures("database")
async def test_command_stats_are_scoped_and_keep_alphabetical_ties() -> None:
    """Verify that command stats are scoped and keep alphabetical ties."""
    await CommandInvocation.bulk_create(
        [
            CommandInvocation(command="shop", user_id=123, guild_id=10),
            CommandInvocation(command="shop", user_id=123, guild_id=10),
            CommandInvocation(command="balance", user_id=123, guild_id=10),
            CommandInvocation(command="balance", user_id=123, guild_id=10),
            CommandInvocation(command="shop", user_id=123, guild_id=20),
            CommandInvocation(command="shop", user_id=456, guild_id=10),
            CommandInvocation(command="balance", user_id=456, guild_id=10),
            CommandInvocation(command="shop", user_id=456, guild_id=20),
            CommandInvocation(command="shop", user_id=789),
        ]
    )

    assert await command_stats(user_id=123) == (5, "shop")
    assert await command_stats(guild_id=10) == (6, "balance")
    assert await command_stats(guild_id=20) == (2, "shop")


@pytest.mark.usefixtures("database")
async def test_command_stats_returns_empty_result_and_requires_one_scope() -> None:
    """Verify that command stats returns empty result and requires one scope."""
    assert await command_stats(user_id=999) == (0, None)

    with pytest.raises(ValueError, match="exactly one"):
        await command_stats()
    with pytest.raises(ValueError, match="exactly one"):
        await command_stats(user_id=123, guild_id=456)
