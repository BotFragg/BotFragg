"""Persistence and orchestration for analytics."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from weakref import WeakValueDictionary

from tortoise.functions import Count

from ..models import (
    CommandInvocation,
)

# shortcut: guards are process-local; share deletion generations before running multiple bot processes.
_active_commands: dict[int, set[asyncio.Event]] = {}
_analytics_locks: WeakValueDictionary[int, asyncio.Lock] = WeakValueDictionary()


@asynccontextmanager
async def command_analytics(user_id: int) -> AsyncIterator[asyncio.Event]:
    """Keep a command's analytics cancellable until its completion is recorded."""
    cancelled = asyncio.Event()
    commands = _active_commands.setdefault(user_id, set())
    commands.add(cancelled)
    try:
        yield cancelled
    finally:
        commands.remove(cancelled)
        if not commands:
            _active_commands.pop(user_id, None)


@asynccontextmanager
async def deleting_analytics(user_id: int) -> AsyncIterator[None]:
    """Serialize deletion with analytics writes and cancel earlier completions."""
    async with _analytics_locks.setdefault(user_id, asyncio.Lock()):
        yield
        for cancelled in _active_commands.get(user_id, ()):
            cancelled.set()


async def record_command_invocation(
    *,
    command: str,
    user_id: int,
    guild_id: int | None,
    channel_id: int | None,
    cancelled: asyncio.Event | None = None,
) -> None:
    """Persist a successful command invocation with its optional Discord scope."""
    async with _analytics_locks.setdefault(user_id, asyncio.Lock()):
        if cancelled is not None and cancelled.is_set():
            return
        await CommandInvocation.create(
            command=command,
            user_id=user_id,
            guild_id=guild_id,
            channel_id=channel_id,
        )


async def command_stats(
    *, user_id: int | None = None, guild_id: int | None = None
) -> tuple[int, str | None]:
    """Return a scoped command-use count and the most-used command.

    Exactly one of ``user_id`` or ``guild_id`` is required. Ties for the most-used
    command are resolved alphabetically for stable results.
    """
    if (user_id is None) == (guild_id is None):
        raise ValueError("Provide exactly one of user_id or guild_id")

    filters = {"user_id": user_id} if user_id is not None else {"guild_id": guild_id}
    # ponytail: scopes scan retained rows; add indexes when measured latency needs them.
    records = await (
        CommandInvocation.filter(**filters)
        .group_by("command")
        .annotate(total=Count("id"))
        .values("command", "total")
    )
    if not records:
        return 0, None

    count = sum(record["total"] for record in records)
    favorite = min(records, key=lambda record: (-record["total"], record["command"]))[
        "command"
    ]
    return count, favorite
