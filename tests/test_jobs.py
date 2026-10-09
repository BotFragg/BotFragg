"""Behavior and regression checks for jobs."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from datetime import time as utc_time
from types import SimpleNamespace
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import aiohttp
import asyncpg
import discord
import pytest
from tortoise import connections
from tortoise.exceptions import DBConnectionError

from src.cogs import extra as extra_module
from src.cogs.extra import ExtraCog
from src.cogs.tasks import TasksCog
from src.models import Account, Alert, User
from src.services import alerts as alert_service
from src.services.accounts import delete_user_data
from src.services.auth import AuthenticationRequired
from src.services.catalog import Skin
from src.services.http import HTTPFailure
from src.services.shop import Offer, ShopData
from tests.helpers import (
    _localized_bot,
)


@pytest.mark.parametrize("mode", ["skin", "daily", "expired"])
@pytest.mark.parametrize("stage", ["fetch", "send"])
@pytest.mark.parametrize(
    "failure", [aiohttp.ServerDisconnectedError, TimeoutError, OSError]
)
async def test_daily_delivery_transport_failure_does_not_stop_or_replay_runs(
    backend_database, monkeypatch, mode, stage, failure
):
    skin = Skin(str(UUID(int=1)), "offer", "Skin", None, None)
    shop = ShopData([Offer(skin, 100, 4_000_000_000)], [], [], 4_000_000_000, None)
    for user_id in (101, 102, 103):
        owner = await User.create(
            id=user_id,
            daily_shop_enabled=mode == "daily",
            current_account_id=str(user_id),
        )
        account = await Account.create(
            puuid=str(user_id), user=owner, username="Synthetic#TEST"
        )
        if mode != "daily":
            await Alert.create(account=account, skin_uuid=skin.uuid)
    delivered = []
    failed = False

    def interrupt(user_id, current_stage):
        nonlocal failed
        if user_id == 101 and current_stage == stage and not failed:
            failed = True
            raise failure("Synthetic Discord disconnect")

    async def fetch_user(user_id):
        interrupt(user_id, "fetch")

        async def send(**kwargs):
            interrupt(user_id, "send")
            delivered.append((cog.daily_alerts.current_loop, user_id))

        return NS(send=send)

    cog = TasksCog(
        _localized_bot(
            config=NS(
                user_agent_interval_minutes=15,
                game_version_interval_minutes=15,
                alert_time_utc=utc_time(0, 0),
                log_flush_interval_seconds=10,
                alert_concurrency=1,
                delay_between_alerts_seconds=0,
                link_item_image=False,
            ),
            wait_until_ready=AsyncMock(),
            get_user=lambda _: None,
            fetch_user=fetch_user,
            emoji_service=NS(
                currency=AsyncMock(return_value="VP"),
                skin_name=lambda name, tier: name,
                skin_emoji=lambda tier: "",
            ),
            shop=NS(
                storefront=AsyncMock(
                    side_effect=AuthenticationRequired("Synthetic expired login")
                )
                if mode == "expired"
                else AsyncMock(return_value=shop)
            ),
        )
    )
    today = datetime(2026, 10, 9, tzinfo=UTC)
    tomorrow = today + timedelta(days=1)
    slots = []

    async def wait_until(slot):
        slots.append(slot)

    loop = cog.daily_alerts
    loop.count = 2
    summaries = []
    run = cog.run_alerts

    async def record_run():
        summary = await run()
        summaries.append(summary)
        return summary

    monkeypatch.setattr(cog, "run_alerts", record_run)
    monkeypatch.setattr(loop, "_try_sleep_until", wait_until)
    monkeypatch.setattr(
        loop,
        "_get_next_sleep_time",
        Mock(side_effect=[today, tomorrow, tomorrow + timedelta(days=1)]),
    )
    await loop._loop(cog)
    assert slots == [today, tomorrow]
    assert sorted(delivered) == [(0, 102), (0, 103), (1, 101), (1, 102), (1, 103)]
    assert not loop.failed()
    assert [summary["delivery_failures"] for summary in summaries] == [1, 0]
    assert all(summary["shop_failures"] == 0 for summary in summaries)
    assert cog.job_health["daily_alerts"].failures == 1
    assert cog.job_health["daily_alerts"].last_success is not None


@pytest.mark.parametrize("mode", ["alert", "daily"])
@pytest.mark.parametrize("failure", [TimeoutError, OSError])
async def test_delivery_database_failures_are_not_swallowed(
    backend_database, monkeypatch, mode, failure
):
    owner = await User.create(
        id=101, daily_shop_enabled=True, current_account_id="synthetic"
    )
    account = await Account.create(
        puuid="synthetic", user=owner, username="Synthetic#TEST"
    )
    skin = Skin(str(UUID(int=1)), "offer", "Skin", None, None)
    alert = await Alert.create(account=account, skin_uuid=skin.uuid)
    target = NS(send=AsyncMock())
    cog = NS(
        bot=_localized_bot(
            get_user=lambda _: target,
            emoji_service=NS(currency=AsyncMock(return_value="VP")),
        )
    )
    monkeypatch.setattr(
        connections.get("default"),
        "execute_query",
        AsyncMock(side_effect=failure("Synthetic DB outage")),
    )
    with pytest.raises(failure, match="DB outage"):
        if mode == "daily":
            await TasksCog._send_daily_shop(
                cog, owner, account, ShopData([], [], [], 0, None)
            )
        else:
            await TasksCog._send_alert(cog, owner.id, alert, Offer(skin, 100, 0))
    target.send.assert_not_awaited()


@pytest.mark.usefixtures("database")
@pytest.mark.parametrize("phase", ["matches", "initial"])
async def test_clock_daily_job_does_not_replay_after_exhausted_worker_retries(
    monkeypatch,
    phase,
):
    owner = await User.create(id=101)
    accounts = [
        await Account.create(puuid=f"retry-{i}", user=owner, username="Synthetic#TEST")
        for i in range(2)
    ]
    skin = Skin(str(UUID(int=1)), "offer", "Skin", None, None)
    for account in accounts:
        await Alert.create(account=account, skin_uuid=skin.uuid)
    config = NS(
        user_agent_interval_minutes=15,
        game_version_interval_minutes=15,
        alert_time_utc=utc_time(0, 0),
        log_flush_interval_seconds=10,
        alert_concurrency=1,
        delay_between_alerts_seconds=0,
    )
    cog = TasksCog(
        NS(
            config=config,
            wait_until_ready=AsyncMock(),
            shop=NS(
                storefront=AsyncMock(
                    return_value=ShopData(
                        [Offer(skin, 100, 4_000_000_000)], [], [], 4_000_000_000, None
                    )
                )
            ),
        )
    )
    delivery = AsyncMock(return_value=0)
    monkeypatch.setattr(cog, "_deliver_daily_alert_result", delivery)
    original = alert_service.matching_alerts_for_skins
    failed = 0

    async def matches(account, skins):
        nonlocal failed
        if account.puuid == accounts[1].puuid and failed < 3:
            failed += 1
            raise DBConnectionError("Synthetic outage")
        return await original(account, skins)

    if phase == "matches":
        monkeypatch.setattr(alert_service, "matching_alerts_for_skins", matches)
    else:
        monkeypatch.setattr(
            alert_service,
            "user_ids_with_alerts",
            AsyncMock(
                side_effect=[
                    DBConnectionError("Synthetic outage"),
                    DBConnectionError("Synthetic outage"),
                    DBConnectionError("Synthetic outage"),
                    {owner.id},
                ]
            ),
        )
    monkeypatch.setattr(alert_service.asyncio, "sleep", AsyncMock())
    today = datetime(2026, 10, 9, tzinfo=UTC)
    tomorrow = today + timedelta(days=1)
    slots = []

    async def wait_until(slot):
        slots.append(slot)

    loop = cog.daily_alerts
    loop.count = 2
    monkeypatch.setattr(loop, "_try_sleep_until", wait_until)
    monkeypatch.setattr(
        loop,
        "_get_next_sleep_time",
        Mock(side_effect=[today, tomorrow, tomorrow + timedelta(days=1)]),
    )
    await loop._loop(cog)
    assert slots == [today, tomorrow]
    assert [call.args[2].puuid for call in delivery.await_args_list] == (
        [accounts[0].puuid, accounts[0].puuid, accounts[1].puuid]
        if phase == "matches"
        else [accounts[0].puuid, accounts[1].puuid]
    )
    assert cog.job_health["daily_alerts"].failures == 1
    assert cog.job_health["daily_alerts"].last_success is not None


@pytest.mark.parametrize(
    "mode,stage,change",
    [
        ("daily", "fetch", "delete"),
        ("daily", "currency", "relink"),
        ("daily", "currency", "disable"),
        ("daily", "currency", "switch"),
        ("alert", "fetch", "delete"),
        ("alert", "fetch", "relink"),
        ("alert", "fetch", "remove"),
    ],
)
@pytest.mark.usefixtures("backend_database")
async def test_notifications_recheck_identity_and_preferences(mode, stage, change):
    owner = await User.create(
        id=101, daily_shop_enabled=True, current_account_id="synthetic"
    )
    account = await Account.create(
        puuid="synthetic", user=owner, username="FormerName#TEST"
    )
    skin = Skin(str(UUID(int=1)), "offer", "Skin", None, None)
    alert = await Alert.create(account=account, skin_uuid=skin.uuid)
    offer = Offer(skin, 100, 4_000_000_000)
    target = NS(send=AsyncMock())

    async def mutate(wait):
        if wait != stage:
            return
        if change == "delete":
            await delete_user_data(owner.id)
        elif change == "relink":
            await account.delete()
            other = await User.create(id=202)
            await Account.create(
                puuid=account.puuid, user=other, username="NewName#TEST"
            )
        elif change == "remove":
            await alert.delete()
        else:
            await User.filter(id=owner.id).update(
                **(
                    {"daily_shop_enabled": False}
                    if change == "disable"
                    else {"current_account_id": "other"}
                )
            )

    async def fetch_user(_):
        await mutate("fetch")
        return target

    async def currency(_):
        await mutate("currency")
        return "VP"

    bot = _localized_bot(
        get_user=lambda _: None,
        fetch_user=fetch_user,
        emoji_service=NS(
            currency=currency,
            skin_name=lambda name, tier: name,
            skin_emoji=lambda tier: "",
        ),
        config=NS(link_item_image=False),
    )
    cog = NS(bot=bot)
    if mode == "daily":
        result = await TasksCog._send_daily_shop(
            cog, owner, account, ShopData([offer], [], [], 4_000_000_000, None)
        )
    else:
        result = await TasksCog._send_alert(cog, owner.id, alert, offer)
    assert result is True
    target.send.assert_not_awaited()


async def test_shard_status_retries_saved_message_id_without_posting_twice(monkeypatch):
    class Channel(discord.abc.Messageable):
        async def _get_channel(self):
            return self

    channel = Channel()
    message = NS(id=111, edit=AsyncMock())
    channel.send = AsyncMock(return_value=message)
    channel.fetch_message = AsyncMock(return_value=message)
    save = AsyncMock(side_effect=[DBConnectionError("Synthetic failed save"), None])
    monkeypatch.setattr(
        extra_module, "get_shard_status_message_id", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(extra_module, "save_shard_status_message", save)
    cog = ExtraCog(
        NS(
            config=NS(shard_status_channel_id=101),
            shards={},
            get_channel=lambda _: channel,
        )
    )
    with pytest.raises(DBConnectionError):
        await cog._update_shard_status()
    await cog._update_shard_status()
    channel.send.assert_awaited_once()
    message.edit.assert_awaited_once()
    assert save.await_count == 2 and save.await_args.args == (101, 111)


@pytest.mark.usefixtures("database")
@pytest.mark.parametrize(
    "outcome", ["unavailable", "expired", "delivery", "expired_delivery", "success"]
)
async def test_daily_health_reports_outcomes_and_recovers(outcome):
    from src.models import Account, User
    from src.services.auth import AuthenticationRequired
    from src.services.shop import ShopUnavailable

    user = await User.create(
        id=101, daily_shop_enabled=True, current_account_id="daily"
    )
    await Account.create(puuid="daily", user=user, username="Player#NA")
    target = NS(send=AsyncMock())
    shop = NS(storefront=AsyncMock(return_value=NS(offers=[], expires=0)))
    bot = _localized_bot(
        config=NS(
            user_agent_interval_minutes=15,
            game_version_interval_minutes=15,
            alert_time_utc=utc_time(0, 0),
            log_flush_interval_seconds=10,
            alert_concurrency=1,
            delay_between_alerts_seconds=0,
            link_item_image=False,
        ),
        shop=shop,
        get_user=lambda _: target,
        emoji_service=NS(currency=AsyncMock(return_value="VP")),
    )
    if outcome == "unavailable":
        shop.storefront.side_effect = ShopUnavailable("synthetic outage")
    elif outcome in {"expired", "expired_delivery"}:
        shop.storefront.side_effect = AuthenticationRequired("expired")
    if outcome in {"delivery", "expired_delivery"}:
        target.send.side_effect = discord.HTTPException(
            NS(status=403, reason="Forbidden"), "synthetic blocked DM"
        )
    cog = TasksCog(bot)
    state = cog.job_health["daily_alerts"]
    await cog.daily_alerts()
    assert state.snapshot(running=True, failed=False, now=0)["healthy"] is (
        outcome in {"expired", "success"}
    )
    assert state.failures == int(
        outcome in {"unavailable", "delivery", "expired_delivery"}
    )
    assert (
        state.last_success is None if state.failures else state.last_success is not None
    )

    shop.storefront.side_effect = None
    target.send.side_effect = None
    await cog.daily_alerts()
    assert state.snapshot(running=True, failed=False, now=0)["healthy"] is True


async def test_refresh_loop_survives_transient_http_failure():
    bot = SimpleNamespace(
        config=SimpleNamespace(
            user_agent_interval_minutes=15,
            game_version_interval_minutes=15,
            alert_time_utc=datetime.now(UTC).time(),
            log_flush_interval_seconds=10,
        ),
        wait_until_ready=AsyncMock(),
        auth=SimpleNamespace(
            refresh_version=AsyncMock(side_effect=HTTPFailure("synthetic timeout"))
        ),
    )
    cog = TasksCog(bot)
    loop = cog.version_refresh
    task = loop.start()
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=0.2)
    except HTTPFailure:
        pass
    except TimeoutError:
        pass
    finally:
        loop.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert not loop.failed()


async def test_clock_scheduled_daily_job_recovers_database_read_in_same_run(
    monkeypatch,
):
    lookup = AsyncMock(side_effect=[DBConnectionError("Synthetic restart"), set()])
    delay = AsyncMock()
    monkeypatch.setattr(alert_service, "user_ids_with_alerts", lookup)
    monkeypatch.setattr(
        alert_service, "daily_shop_user_ids", AsyncMock(return_value=set())
    )
    monkeypatch.setattr(alert_service.asyncio, "sleep", delay)
    cog = TasksCog(
        NS(
            config=NS(
                user_agent_interval_minutes=15,
                game_version_interval_minutes=15,
                alert_time_utc=(datetime.now(UTC) + timedelta(seconds=1)).timetz(),
                log_flush_interval_seconds=10,
                alert_concurrency=1,
                delay_between_alerts_seconds=0,
            ),
            wait_until_ready=AsyncMock(),
            shop=NS(),
        )
    )
    complete = asyncio.Event()
    original = cog.run_alerts

    async def run():
        summary = await original()
        complete.set()
        return summary

    cog.run_alerts = run
    task = cog.daily_alerts.start()
    try:
        await asyncio.wait_for(complete.wait(), 5)
        assert lookup.await_count == 2
        delay.assert_any_await(5)
        assert cog.job_health["daily_alerts"].last_success is not None
        assert not cog.daily_alerts.failed()
    finally:
        cog.daily_alerts.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("job", ["daily", "shard"])
async def test_database_connection_loss_does_not_permanently_stop_jobs(
    job, monkeypatch
):
    config = NS(
        user_agent_interval_minutes=15,
        game_version_interval_minutes=15,
        alert_time_utc=utc_time(0, 0),
        log_flush_interval_seconds=10,
        shard_status_channel_id=101,
    )
    bot = NS(config=config, wait_until_ready=AsyncMock(), shards={})
    failure = asyncpg.exceptions.ConnectionDoesNotExistError(
        "Synthetic database restart"
    )
    if job == "daily":
        cog = TasksCog(bot)
        cog.run_alerts = AsyncMock(side_effect=failure)
        loop = cog.daily_alerts
    else:
        import src.cogs.extra as module

        class Channel(discord.abc.Messageable):
            async def _get_channel(self):
                return self

        bot.get_channel = lambda channel_id: Channel()
        monkeypatch.setattr(
            module, "get_shard_status_message_id", AsyncMock(side_effect=failure)
        )
        cog = ExtraCog(bot)
        loop = cog.shard_status
    loop.change_interval(seconds=0.01)
    task = loop.start()
    try:
        await asyncio.wait_for(asyncio.shield(task), 0.1)
    except (
        asyncpg.exceptions.ConnectionDoesNotExistError,
        DBConnectionError,
        TimeoutError,
    ):
        pass
    finally:
        loop.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert not loop.failed(), (
        "One transient database outage permanently killed the loop"
    )


async def test_successful_background_job_remains_running():
    config = NS(
        user_agent_interval_minutes=15,
        game_version_interval_minutes=15,
        alert_time_utc=utc_time(0, 0),
        log_flush_interval_seconds=10,
    )
    cog = TasksCog(NS(config=config, wait_until_ready=AsyncMock()))
    cog.run_alerts = AsyncMock(
        return_value={"shop_failures": 0, "delivery_failures": 0}
    )
    loop = cog.daily_alerts
    loop.change_interval(seconds=0.01)
    task = loop.start()
    try:
        await asyncio.wait_for(asyncio.shield(task), 0.05)
    except TimeoutError:
        pass
    finally:
        loop.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert not loop.failed() and cog.run_alerts.await_count > 0


@pytest.mark.parametrize(
    "failure_type",
    [
        asyncpg.exceptions.ConnectionDoesNotExistError,
        ConnectionRefusedError,
        TimeoutError,
    ],
)
async def test_database_failure_inside_daily_worker_does_not_kill_loop(
    monkeypatch, failure_type
):
    import src.services.alerts as module

    failure = failure_type("Synthetic worker DB outage")
    monkeypatch.setattr(module, "user_ids_with_alerts", AsyncMock(return_value={101}))
    monkeypatch.setattr(module, "daily_shop_user_ids", AsyncMock(return_value=set()))
    user = NS(id=101)
    account = NS(user_id=101, user=user, puuid="synthetic")
    query = NS(order_by=AsyncMock(return_value=[account]))
    query.select_related = lambda *args: query
    monkeypatch.setattr(module.Account, "filter", lambda **kwargs: query)
    monkeypatch.setattr(
        module, "account_ids_with_alerts", AsyncMock(return_value=set())
    )
    monkeypatch.setattr(module, "selected_account", AsyncMock(side_effect=failure))
    config = NS(
        user_agent_interval_minutes=15,
        game_version_interval_minutes=15,
        alert_time_utc=utc_time(0, 0),
        log_flush_interval_seconds=10,
        alert_concurrency=1,
        delay_between_alerts_seconds=0,
    )
    cog = TasksCog(NS(config=config, wait_until_ready=AsyncMock(), shop=NS()))
    loop = cog.daily_alerts
    loop.change_interval(seconds=0.01)
    task = loop.start()
    try:
        await asyncio.wait_for(asyncio.shield(task), 0.1)
    except ExceptionGroup as group:
        assert len(group.exceptions) == 1
        assert isinstance(group.exceptions[0], type(failure))
    except DBConnectionError:
        pass
    except TimeoutError:
        pass
    finally:
        loop.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert not loop.failed(), (
        "TaskGroup-wrapped database failure permanently killed the daily loop"
    )


@pytest.mark.parametrize(
    "failure_type",
    [
        asyncpg.exceptions.ConnectionDoesNotExistError,
        ConnectionRefusedError,
        TimeoutError,
    ],
)
@pytest.mark.parametrize("unknown_type", [ValueError, FileNotFoundError])
async def test_daily_job_keeps_unrelated_worker_errors_visible(
    failure_type, unknown_type
):
    cog = TasksCog(
        NS(
            config=NS(
                user_agent_interval_minutes=15,
                game_version_interval_minutes=15,
                alert_time_utc=utc_time(0, 0),
                log_flush_interval_seconds=10,
            )
        )
    )
    unknown = unknown_type("Synthetic implementation error")
    cog.run_alerts = AsyncMock(
        side_effect=ExceptionGroup(
            "mixed",
            [
                failure_type("Synthetic outage"),
                unknown,
            ],
        )
    )
    with pytest.raises(ExceptionGroup) as raised:
        await cog.daily_alerts()
    assert raised.value.subgroup(lambda error: error is unknown) is not None


@pytest.mark.parametrize(
    "failure",
    [
        asyncpg.exceptions.ConnectionDoesNotExistError,
        asyncpg.exceptions.AdminShutdownError,
        asyncpg.exceptions.CrashShutdownError,
        asyncpg.exceptions.CannotConnectNowError,
        DBConnectionError,
        ConnectionRefusedError,
        TimeoutError,
    ],
)
async def test_daily_job_retries_and_recovers(failure, monkeypatch):
    from discord.ext.tasks import ExponentialBackoff

    monkeypatch.setattr(ExponentialBackoff, "delay", lambda self: 0)
    cog = TasksCog(
        NS(
            config=NS(
                user_agent_interval_minutes=15,
                game_version_interval_minutes=15,
                alert_time_utc=utc_time(0, 0),
                log_flush_interval_seconds=10,
            ),
            wait_until_ready=AsyncMock(),
        )
    )
    recovered = asyncio.Event()
    calls = 0

    async def run():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise failure("Synthetic outage")
        recovered.set()
        await asyncio.Event().wait()

    cog.run_alerts = run
    cog.daily_alerts.change_interval(seconds=0.01)
    task = cog.daily_alerts.start()
    try:
        await asyncio.wait_for(recovered.wait(), 1)
        assert calls == 2 and not cog.daily_alerts.failed()
    finally:
        cog.daily_alerts.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_tasks_cog_awaits_cancelled_background_loops(
    monkeypatch, tmp_path
) -> None:
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

    monkeypatch.setattr("src.cogs.tasks.HEALTH_PATH", tmp_path / "health.json")
    loops = [Loop(asyncio.create_task(worker())) for _ in range(5)]
    await asyncio.sleep(0)
    cog = SimpleNamespace(
        daily_alerts=loops[0],
        version_refresh=loops[1],
        catalog_refresh=loops[2],
        log_flush=loops[3],
        health_watch=loops[4],
        discord_log_handler=logging.NullHandler(),
    )

    await TasksCog.cog_unload(cog)

    assert finished == 5
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

    sent_alert = await TasksCog._send_alert(
        cog,
        user_id,
        SimpleNamespace(id=1, account=SimpleNamespace(username="Player#NA")),
        SimpleNamespace(
            skin=SimpleNamespace(name="Skin", icon=None, tier_uuid=None), expires=0
        ),
    )
    sent_shop = await TasksCog._send_daily_shop(
        cog,
        SimpleNamespace(id=user_id),
        SimpleNamespace(username="Player#NA"),
        SimpleNamespace(offers=[], expires=0),
    )
    notice_failures = await TasksCog._credentials_expired(cog, user_id)

    assert fetched_ids == [user_id, user_id, user_id]
    assert sent_alert is False and sent_shop is False and notice_failures == 1


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
