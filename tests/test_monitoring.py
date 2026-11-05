"""Behavior and regression checks for monitoring."""

from __future__ import annotations

import json
import logging
import sys
from collections import deque
from datetime import time as daytime
from types import SimpleNamespace as NS

import aiohttp
import discord
import pytest

from src import main as entrypoint
from src.cogs.tasks import DiscordLogHandler, TasksCog
from src.monitoring import PlainFormatter, _category, _scrub


@pytest.mark.parametrize(
    ("logger_name", "category"),
    [
        ("src.cogs.events", "command"),
        ("src.cogs.events.guild", "guild"),
        ("src.health", "jobs"),
        ("src.services.valorant_status", "status"),
        ("src.services.crosshair_render", "crosshair"),
        ("discord.gateway", "discord"),
        ("tortoise.db_client", "database"),
    ],
)
def test_log_categories_use_operator_names(logger_name, category):
    """Verify that log categories shorten internal module paths."""
    assert _category(logger_name) == category


@pytest.mark.parametrize(
    "path, expected",
    [
        (
            "channels/123456789012345678/messages/234567890123456789",
            "channels/[Filtered]/messages/[Filtered]",
        ),
        (
            "guilds/123456789012345678/members/234567890123456789",
            "guilds/[Filtered]/members/[Filtered]",
        ),
        (
            "guilds/123456789012345678/roles/234567890123456789",
            "guilds/[Filtered]/roles/[Filtered]",
        ),
        ("users/123456789012345678", "users/[Filtered]"),
        (
            "webhooks/123456789012345678/AUDIT_SYNTHETIC_TOKEN",
            "webhooks/[Filtered]/[Filtered]",
        ),
        (
            "interactions/123456789012345678/AUDIT_SYNTHETIC_TOKEN/callback",
            "interactions/[Filtered]/[Filtered]/callback",
        ),
        (
            "applications/123456789012345678/commands",
            "applications/[Filtered]/commands",
        ),
        ("users/@me", "users/@me"),
    ],
)
def test_rate_limit_warnings_scrub_discord_url_identifiers(path, expected):
    url = f"https://discord.com/api/v10/{path}"
    record = logging.LogRecord(
        "discord.http",
        logging.WARNING,
        "http.py",
        1,
        "We are being rate limited. POST %s responded with 429. Retrying in 1s.",
        (url,),
        None,
    )
    formatted = PlainFormatter().format(record)
    filtered_url = f"https://discord.com/api/v10/{expected}"
    assert filtered_url in formatted
    assert _scrub(url) == filtered_url


def test_dependency_payloads_stay_out_of_logs(monkeypatch, capsys):
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(root, "level", logging.NOTSET)
    for name in ("src", "discord.gateway", "tortoise.db_client", "aiosqlite"):
        monkeypatch.setattr(logging.getLogger(name), "level", logging.NOTSET)
    config = NS(discord_token=None)
    monkeypatch.setattr(entrypoint.Settings, "from_env", lambda: config)

    def run(*args, **kwargs):
        logging.getLogger("src.bot").debug("Application diagnostic")
        for name in ("discord.gateway", "tortoise.db_client", "aiosqlite"):
            logging.getLogger(name).debug("Private payload %s", "SYNTHETIC_PRIVATE")
            logging.getLogger(name).warning("Dependency warning")

    monkeypatch.setattr(entrypoint, "BotFraggBot", lambda _: NS(run=run))
    try:
        entrypoint.main()
        output = capsys.readouterr().err
        assert "Application diagnostic" not in output
        assert "SYNTHETIC_PRIVATE" not in output
        assert "Dependency warning" in output
    finally:
        for handler in root.handlers:
            handler.close()


def test_formatter_removes_webhook_and_interaction_tokens():
    synthetic_token = "AUDIT_SYNTHETIC_" + "a" * 60
    record = logging.LogRecord(
        "discord.webhook.async_",
        logging.DEBUG,
        "synthetic.py",
        1,
        "Webhook ID %s with POST %s has returned status code 200",
        (
            123456789012345678,
            f"https://discord.com/api/webhooks/123456789012345678/{synthetic_token}",
        ),
        None,
    )
    assert synthetic_token not in PlainFormatter().format(record)


def test_formatter_removes_oauth_code_from_gateway_payload():
    record = logging.LogRecord(
        "discord.gateway",
        logging.DEBUG,
        "synthetic.py",
        1,
        "WebSocket Event: %s",
        (
            json.dumps(
                {
                    "components": [
                        {"value": "http://localhost/redirect?code=AUDIT_SYNTHETIC_CODE"}
                    ]
                }
            ),
        ),
        None,
    )
    assert "AUDIT_SYNTHETIC_CODE" not in PlainFormatter().format(record)


@pytest.mark.asyncio
async def test_log_flush_bounds_single_oversized_record():
    attempts = []

    async def send(*, embed):
        attempts.append(len(embed.description))
        if len(embed.description) > 4096:
            raise discord.HTTPException(
                NS(status=400, reason="Bad Request"), "Embed description too long"
            )

    channel = NS(send=send)
    config = NS(
        user_agent_interval_minutes=15,
        game_version_interval_minutes=15,
        alert_time_utc=daytime(0, 0),
        log_flush_interval_seconds=10,
        log_channel_id=123,
    )
    cog = TasksCog(NS(config=config, get_channel=lambda _: channel))
    cog.discord_log_handler.messages = deque(["x" * 5000, "normal log"], maxlen=1000)
    await TasksCog.log_flush.coro(cog)
    await TasksCog.log_flush.coro(cog)
    assert max(attempts) <= 4096 and not cog.discord_log_handler.messages, (
        f"Long record requeued indefinitely: {attempts}"
    )


@pytest.mark.asyncio
async def test_log_flush_failure_keeps_newest_logs_when_buffer_is_full():
    cog = None

    async def send(*, embed):
        cog.discord_log_handler.messages.extend(f"new {i}" for i in range(1000))
        raise discord.HTTPException(NS(status=503, reason="Unavailable"), "retry")

    config = NS(
        user_agent_interval_minutes=15,
        game_version_interval_minutes=15,
        alert_time_utc=daytime(0, 0),
        log_flush_interval_seconds=10,
        log_channel_id=123,
    )
    cog = TasksCog(NS(config=config, get_channel=lambda _: NS(send=send)))
    cog.discord_log_handler.messages.append("stale")
    await TasksCog.log_flush.coro(cog)
    assert "stale" not in cog.discord_log_handler.messages
    assert "new 999" in cog.discord_log_handler.messages


@pytest.mark.asyncio
async def test_log_flush_requeues_when_log_channel_is_not_messageable():
    config = NS(
        user_agent_interval_minutes=15,
        game_version_interval_minutes=15,
        alert_time_utc=daytime(0, 0),
        log_flush_interval_seconds=10,
        log_channel_id=123,
    )
    cog = TasksCog(NS(config=config, get_channel=lambda _: NS()))
    cog.discord_log_handler.messages.append("kept")
    await TasksCog.log_flush.coro(cog)
    assert "kept" in cog.discord_log_handler.messages
    assert cog.job_health["log_flush"].failures == 1


@pytest.mark.parametrize(
    "failure",
    [discord.HTTPException, aiohttp.ServerDisconnectedError, TimeoutError, OSError],
)
@pytest.mark.parametrize("stage", ["fetch", "send"])
async def test_split_log_retries_preserve_content_and_order(failure, stage):
    attempts, delivered = [], []
    interrupted = False

    def interrupt(current_stage):
        nonlocal interrupted
        if current_stage == stage and not interrupted:
            interrupted = True
            if failure is discord.HTTPException:
                raise failure(NS(status=503, reason="Unavailable"), "retry")
            raise failure("Synthetic Discord disconnect")

    async def send(*, embed):
        attempts.append(embed.description)
        interrupt("send")
        delivered.append(embed.description[4:-4])

    async def fetch_channel(_):
        interrupt("fetch")
        return NS(send=send)

    cog = TasksCog(
        NS(
            config=NS(
                user_agent_interval_minutes=15,
                game_version_interval_minutes=15,
                alert_time_utc=daytime(0, 0),
                log_flush_interval_seconds=10,
                log_channel_id=123,
            ),
            get_channel=lambda _: None,
            fetch_channel=fetch_channel,
        )
    )
    cog.discord_log_handler.messages.extend(["x" * 8000, "last"])
    for _ in range(4):
        await TasksCog.log_flush.coro(cog)
    if stage == "send":
        assert attempts[0] == attempts[1]
    assert all(len(attempt) <= 4096 for attempt in attempts)
    assert "".join(delivered) == "x" * 8000 + "\nlast"
    assert not cog.discord_log_handler.messages
    assert cog.job_health["log_flush"].failures == 1
    assert cog.job_health["log_flush"].last_success is not None
    for loop in (
        cog.daily_alerts,
        cog.version_refresh,
        cog.log_flush,
    ):
        assert loop._before_loop is TasksCog.before_jobs


def test_scrub_removes_compact_auth_fields_and_raw_tokens() -> None:
    """Verify that the log scrubber removes compact auth fields and raw tokens."""
    message = (
        "Bearer bearer-secret, refresh_token=refresh-secret, "
        "headerpayload.claimspayload.signaturepayload, "
        "notification failed for user 123456789012345678 <@123456789012345678>"
    )

    scrubbed = _scrub(message)

    assert all(
        secret not in scrubbed
        for secret in (
            "bearer-secret",
            "refresh-secret",
            "headerpayload.claimspayload.signaturepayload",
            "123456789012345678",
        )
    )


def test_scrub_removes_riot_puuids() -> None:
    """Verify that the log scrubber removes Riot PUUIDs."""
    puuid = "123e4567-e89b-12d3-a456-426614174000"

    assert _scrub(f"failed for {puuid}") == "failed for [Filtered]"


def test_plain_logs_scrub_message_values_and_ignore_extras() -> None:
    """Verify that message values are scrubbed and extra fields are not rendered."""
    puuid = "123e4567-e89b-12d3-a456-426614174000"
    record = logging.LogRecord(
        "src.services.shop",
        logging.INFO,
        "shop.py",
        12,
        "Loaded account %s",
        (puuid,),
        None,
    )
    record.user_id = 123456789012345678

    formatted = PlainFormatter().format(record)

    assert " UTC  INFO   [shop] Loaded account [Filtered]" in formatted
    assert "user_id" not in formatted
    assert "123456789012345678" not in formatted


def test_plain_logs_render_timestamp_level_category_and_traceback() -> None:
    """Verify the operator line format and that tracebacks are scrubbed."""
    try:
        raise RuntimeError("delivery failed token=Bearer eyJhbGciOi.SECRET.SIG")
    except RuntimeError:
        record = logging.LogRecord(
            "src.health",
            logging.INFO,
            "shop.py",
            12,
            "version refresh finished in 0.0s",
            (),
            sys.exc_info(),
        )

    formatted = PlainFormatter().format(record)

    assert " UTC  INFO   [jobs] version refresh finished in 0.0s" in formatted
    assert "SECRET" not in formatted
    assert "Traceback (most recent call last):" in formatted
    assert "delivery failed" in formatted


def test_plain_formatter_does_not_mutate_the_record() -> None:
    """Verify that repeated formatting keeps the traceback for later handlers."""
    try:
        raise RuntimeError("private database detail")
    except RuntimeError:
        record = logging.LogRecord(
            "src.cogs.tasks",
            logging.WARNING,
            "tasks.py",
            9,
            "Could not deliver daily shop notification",
            (),
            sys.exc_info(),
        )

    first = PlainFormatter().format(record)
    second = PlainFormatter().format(record)

    assert first == second
    assert " UTC  WARN   [jobs] Could not deliver daily shop notification" in second
    assert "private database detail" in second
    assert "Traceback (most recent call last):" in second


def test_discord_log_handler_uses_the_scrubbed_plain_formatter() -> None:
    """Verify that Discord log lines are normalized text with identifiers scrubbed."""
    puuid = "123e4567-e89b-12d3-a456-426614174000"
    handler = DiscordLogHandler()
    record = logging.LogRecord(
        "src.services.shop",
        logging.INFO,
        "shop.py",
        12,
        "Failed for %s",
        (puuid,),
        None,
    )
    record.user_id = 123456789012345678

    handler.emit(record)
    line = handler.messages[0]

    assert " UTC  INFO   [shop] Failed for [Filtered]" in line
    assert "user_id" not in line
    assert "123456789012345678" not in line


@pytest.mark.asyncio
async def test_log_flush_failure_restores_a_partial_batch():
    """A failed send must restore every line when the buffer still had room."""

    async def send(*, embed):
        raise discord.HTTPException(NS(status=503, reason="Unavailable"), "retry")

    config = NS(
        user_agent_interval_minutes=15,
        alert_time_utc=daytime(0, 0),
        log_flush_interval_seconds=10,
        log_channel_id=123,
    )
    cog = TasksCog(NS(config=config, get_channel=lambda _: NS(send=send)))
    cog.discord_log_handler.messages.extend(f"line {index}" for index in range(600))

    await TasksCog.log_flush.coro(cog)

    assert len(cog.discord_log_handler.messages) == 600
