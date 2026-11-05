"""Tests for command invocation recording and scoped statistics."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from src.models import CommandInvocation
from src.services.accounts import delete_user_data
from src.services.analytics import (
    command_analytics,
    command_stats,
    prune_command_analytics,
    record_command_invocation,
)


@pytest.mark.usefixtures("database")
async def test_deletion_suppresses_prior_commands_but_allows_new_commands():
    async with command_analytics(101) as cancelled:
        await delete_user_data(101)
        await record_command_invocation(
            command="shop",
            user_id=101,
            guild_id=None,
            channel_id=None,
            cancelled=cancelled,
        )
    assert not await CommandInvocation.exists(user_id=101)
    async with command_analytics(101) as cancelled:
        await record_command_invocation(
            command="ping",
            user_id=101,
            guild_id=None,
            channel_id=None,
            cancelled=cancelled,
        )
    assert await CommandInvocation.filter(user_id=101).count() == 1


@pytest.mark.usefixtures("database")
async def test_deletion_waits_for_an_active_analytics_insert(monkeypatch):
    started, resume = asyncio.Event(), asyncio.Event()
    original = CommandInvocation.create

    async def delayed_insert(**kwargs):
        started.set()
        await resume.wait()
        return await original(**kwargs)

    monkeypatch.setattr(CommandInvocation, "create", delayed_insert)
    async with command_analytics(102) as cancelled:
        recording = asyncio.create_task(
            record_command_invocation(
                command="shop",
                user_id=102,
                guild_id=None,
                channel_id=None,
                cancelled=cancelled,
            )
        )
        await started.wait()
        deleting = asyncio.create_task(delete_user_data(102))
        await asyncio.sleep(0)
        assert not deleting.done()
        resume.set()
        await asyncio.gather(recording, deleting)
    assert not await CommandInvocation.exists(user_id=102)


@pytest.mark.usefixtures("database")
async def test_failed_deletion_does_not_suppress_command_analytics(monkeypatch):
    from tortoise.queryset import QuerySet

    from src.models import User

    original = QuerySet.delete

    def failed_delete(query):
        if query.model is User:
            raise RuntimeError("Synthetic failed deletion")
        return original(query)

    monkeypatch.setattr(QuerySet, "delete", failed_delete)
    async with command_analytics(103) as cancelled:
        with pytest.raises(RuntimeError, match="failed deletion"):
            await delete_user_data(103)
        await record_command_invocation(
            command="shop",
            user_id=103,
            guild_id=None,
            channel_id=None,
            cancelled=cancelled,
        )
    assert await CommandInvocation.exists(user_id=103)


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


@pytest.mark.usefixtures("database")
async def test_retention_deletes_only_analytics_older_than_the_cutoff() -> None:
    """Verify that batched retention removes old analytics and keeps recent ones."""
    old = [
        await CommandInvocation.create(command="shop", user_id=101) for _ in range(3)
    ]
    recent = await CommandInvocation.create(command="profile", user_id=101)
    cutoff = datetime.now(UTC) - timedelta(days=90)
    old_ids = [row.id for row in old]
    await CommandInvocation.filter(id__in=old_ids).update(
        created_at=cutoff - timedelta(seconds=1)
    )

    assert await prune_command_analytics(cutoff, batch_size=1) == 3
    assert not await CommandInvocation.filter(id__in=old_ids).exists()
    assert await CommandInvocation.exists(id=recent.id)


@pytest.mark.usefixtures("database")
async def test_retention_uses_the_default_batch_size() -> None:
    """Verify that retention works without an explicit batch size."""
    old = await CommandInvocation.create(command="shop", user_id=101)
    recent = await CommandInvocation.create(command="profile", user_id=101)
    cutoff = datetime.now(UTC) - timedelta(days=90)
    await CommandInvocation.filter(id=old.id).update(
        created_at=cutoff - timedelta(seconds=1)
    )

    assert await prune_command_analytics(cutoff) == 1
    assert not await CommandInvocation.exists(id=old.id)
    assert await CommandInvocation.exists(id=recent.id)
