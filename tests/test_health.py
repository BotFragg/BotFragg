"""Health probes fail on stale evidence, failed jobs, and lost dependencies."""

from __future__ import annotations

import asyncio
import json
from datetime import time as daytime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.cogs.tasks import TasksCog
from src.config import Settings
from src.health import JobHealth, healthcheck, write_health


def test_daily_health_grace_is_configurable_and_bounded(monkeypatch):
    monkeypatch.setenv("DAILY_ALERT_HEALTH_GRACE_SECONDS", "10800")
    assert (
        Settings.from_env(require_secrets=False).daily_alert_health_grace_seconds
        == 10800
    )
    monkeypatch.setenv("DAILY_ALERT_HEALTH_GRACE_SECONDS", "59")
    with pytest.raises(ValueError, match="DAILY_ALERT_HEALTH_GRACE_SECONDS"):
        Settings.from_env(require_secrets=False)


def test_job_evidence_survives_failure_and_recovers(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("src.health.time.time", lambda: clock[0])
    state = JobHealth(60, first_deadline=1010)
    with state.track("synthetic"):
        pass
    assert state.last_success == 1000 and state.duration_seconds >= 0
    clock[0] += 1
    with pytest.raises(RuntimeError), state.track("synthetic"):
        raise RuntimeError("synthetic failure")
    assert state.last_success == 1000 and state.failures == 1
    assert not state.snapshot(running=True, failed=False, now=1001)["healthy"]
    clock[0] += 1
    with state.track("synthetic"):
        pass
    assert state.snapshot(running=True, failed=False, now=1002)["healthy"]
    assert state.last_failure == 1001 and state.failures == 1
    assert not state.snapshot(running=True, failed=False, now=1063)["healthy"]


def test_cancellation_and_handled_failure_never_record_success():
    state = JobHealth(60)
    with pytest.raises(asyncio.CancelledError), state.track("synthetic"):
        raise asyncio.CancelledError
    assert state.last_success is None and state.failures == 0
    with state.track("synthetic"):
        state.failure("synthetic")
    assert state.last_success is None and state.failures == 1


@pytest.mark.parametrize(
    ("running", "failed", "now", "healthy"),
    [
        (True, False, 1009, True),
        (False, False, 1009, False),
        (True, True, 1009, False),
        (True, False, 1011, False),
    ],
)
def test_initial_job_deadline_and_loop_state(running, failed, now, healthy):
    state = JobHealth(60, first_deadline=1010)
    assert state.snapshot(running=running, failed=failed, now=now)["healthy"] is healthy


@pytest.mark.parametrize("checked_at", [0, 2000, True, "1000", float("nan"), 10**400])
def test_probe_rejects_invalid_or_stale_evidence(tmp_path, monkeypatch, checked_at):
    monkeypatch.setattr("src.health.time.time", lambda: 1000)
    path = tmp_path / "health.json"
    write_health({"healthy": True, "checked_at": checked_at}, path)
    assert not healthcheck(path)


def test_atomic_probe_file_and_missing_malformed_unhealthy_states(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("src.health.time.time", lambda: 1000)
    path = tmp_path / "health.json"
    assert not healthcheck(path)
    path.write_text("{partial", encoding="utf-8")
    assert not healthcheck(path)
    write_health({"healthy": False, "checked_at": 1000}, path)
    assert not healthcheck(path)
    write_health({"healthy": True, "checked_at": 999}, path)
    assert healthcheck(path)
    assert json.loads(path.read_text(encoding="utf-8"))["checked_at"] == 999
    assert list(tmp_path.iterdir()) == [path]


async def test_watchdog_checks_jobs_discord_database_and_recovers(monkeypatch):
    import src.cogs.tasks as module

    bot = SimpleNamespace(
        config=SimpleNamespace(
            user_agent_interval_minutes=15,
            game_version_interval_minutes=15,
            alert_time_utc=daytime(0, 0),
            log_flush_interval_seconds=10,
            log_channel_id=None,
            shard_status_channel_id=None,
        ),
        is_ready=lambda: True,
        is_closed=lambda: False,
        get_cog=lambda _: None,
    )
    cog = TasksCog(bot)
    for name in cog.job_health:
        monkeypatch.setattr(getattr(cog, name), "is_running", lambda: True)
    snapshots = []
    ping = AsyncMock()
    monkeypatch.setattr(module, "ping_database", ping)
    monkeypatch.setattr(module, "write_health", snapshots.append)
    await TasksCog.health_watch.coro(cog)
    assert snapshots[-1]["healthy"]
    assert "log_flush" not in snapshots[-1]["jobs"]

    ping.side_effect = ConnectionError("synthetic database outage")
    monkeypatch.setattr(cog.version_refresh, "is_running", lambda: False)
    bot.is_ready = lambda: False
    await TasksCog.health_watch.coro(cog)
    assert set(snapshots[-1]["problems"]) == {"database", "version_refresh", "discord"}

    ping.side_effect = None
    monkeypatch.setattr(cog.version_refresh, "is_running", lambda: True)
    bot.is_ready = lambda: True
    bot.config.shard_status_channel_id = 123
    await TasksCog.health_watch.coro(cog)
    assert snapshots[-1]["problems"] == ["shard_status"]
    bot.config.shard_status_channel_id = None
    await TasksCog.health_watch.coro(cog)
    assert snapshots[-1]["healthy"]
