"""Persistence and orchestration for analytics."""

from __future__ import annotations

from tortoise.functions import Count

from ..models import (
    CommandInvocation,
)


async def record_command_invocation(
    *,
    command: str,
    user_id: int,
    guild_id: int | None,
    channel_id: int | None,
) -> None:
    """Persist a successful command invocation with its optional Discord scope."""
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
