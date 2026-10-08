"""Behavior checks for jobs."""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import discord
import pytest

from src.cogs.extra import ExtraCog
from src.cogs.tasks import TasksCog
from tests.helpers import (
    _localized_bot,
)


async def test_tasks_cog_awaits_cancelled_background_loops() -> None:
    """Verify that tasks cog awaits cancelled background loops."""
    finished = 0

    async def worker() -> None:
        """Simulate the cancellable background task used by the test."""
        nonlocal finished
        try:
            await asyncio.Event().wait()
        finally:
            finished += 1

    class Loop:
        """Expose a running task and record cancellation for cog-shutdown assertions."""

        def __init__(self, task: asyncio.Task[None]) -> None:
            """Retain the worker task whose shutdown and cancellation are asserted."""
            self.task = task

        def get_task(self) -> asyncio.Task[None]:
            """Return the fake background loop's current task."""
            return self.task

        def cancel(self) -> None:
            """Cancel the fake task and record the cancellation."""
            self.task.cancel()

    loops = [Loop(asyncio.create_task(worker())) for _ in range(4)]
    await asyncio.sleep(0)
    cog = SimpleNamespace(
        daily_alerts=loops[0],
        version_refresh=loops[1],
        catalog_refresh=loops[2],
        log_flush=loops[3],
        discord_log_handler=logging.NullHandler(),
    )

    await TasksCog.cog_unload(cog)

    assert finished == 4
    assert all(loop.get_task().done() for loop in loops)


async def test_task_notifications_handle_http_errors_while_fetching_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that task notifications handle HTTP errors while fetching user."""
    fetched_ids: list[int] = []

    async def fetch_user(user_id: int) -> None:
        """Return the configured Discord user fixture."""
        fetched_ids.append(user_id)
        raise discord.HTTPException(
            SimpleNamespace(status=503, reason="Unavailable"), "unavailable"
        )

    async def currency(_name: str) -> str:
        """Return a stable currency marker for embed assertions."""
        return "VP"

    bot = _localized_bot(
        get_user=lambda _user_id: None,
        fetch_user=fetch_user,
        emoji_service=SimpleNamespace(
            currency=currency, skin_name=lambda name, _tier_uuid: name
        ),
        config=SimpleNamespace(link_item_image=False),
    )
    cog = SimpleNamespace(bot=bot)
    user_id = 123

    monkeypatch.setattr("src.cogs.tasks.offer_cards", lambda *_args, **_kwargs: [])

    await TasksCog._send_alert(
        cog,
        user_id,
        SimpleNamespace(id=1, account=SimpleNamespace(username="Player#NA")),
        SimpleNamespace(
            skin=SimpleNamespace(name="Skin", icon=None, tier_uuid=None), expires=0
        ),
    )
    await TasksCog._send_daily_shop(
        cog,
        SimpleNamespace(id=user_id),
        SimpleNamespace(username="Player#NA"),
        SimpleNamespace(offers=[], expires=0),
    )
    await TasksCog._credentials_expired(cog, user_id)

    assert fetched_ids == [user_id, user_id, user_id]


async def test_extra_cog_awaits_cancelled_background_loop() -> None:
    """Verify that extra cog awaits cancelled background loop."""
    finished = asyncio.Event()

    async def worker() -> None:
        """Simulate the cancellable background task used by the test."""
        try:
            await asyncio.Event().wait()
        finally:
            finished.set()

    task = asyncio.create_task(worker())
    await asyncio.sleep(0)

    class Loop:
        """Expose a running task and record cancellation for cog-shutdown assertions."""

        def get_task(self) -> asyncio.Task[None]:
            """Return the fake background loop's current task."""
            return task

        def cancel(self) -> None:
            """Cancel the fake task and record the cancellation."""
            task.cancel()

    await ExtraCog.cog_unload(SimpleNamespace(shard_status=Loop()))

    assert finished.is_set()
    assert task.done()
