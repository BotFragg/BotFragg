"""Behavior and regression checks for monitoring."""

from __future__ import annotations

import json
import logging
from collections import deque
from datetime import time as daytime
from types import SimpleNamespace
from types import SimpleNamespace as NS

import aiohttp
import discord
import pytest
import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.transport import Transport

from src import main as entrypoint
from src import monitoring
from src.cogs.tasks import DiscordLogHandler, TasksCog
from src.monitoring import StructuredFormatter, _scrub


@pytest.mark.parametrize(
    ("logger_name", "message", "sensitive"),
    [
        (
            "discord.state",
            "Timed out waiting for guild ID %s after %.2fs.",
            123456789012345678,
        ),
        (
            "src.services.auth",
            "Auth request failed token=%s after %.2fs.",
            "AUDIT_SYNTHETIC_SECRET",
        ),
    ],
)
def test_sdk_telemetry_discards_raw_logging_parameters(logger_name, message, sensitive):
    class OfflineTransport(Transport):
        def __init__(self):
            super().__init__()
            self.envelopes = []

        def capture_envelope(self, envelope):
            self.envelopes.append(envelope)

    transport = OfflineTransport()
    integration = LoggingIntegration(sentry_logs_level=logging.INFO)
    client = sentry_sdk.Client(
        dsn="https://synthetic@monitoring.example/1",
        transport=transport,
        default_integrations=False,
        auto_enabling_integrations=False,
        integrations=[integration],
        enable_logs=True,
        send_default_pii=False,
        include_local_variables=False,
        before_send=lambda event, hint: monitoring._scrub_event(event),
        before_send_log=monitoring._scrub_log,
    )
    try:
        with sentry_sdk.isolation_scope() as scope:
            scope.set_client(client)
            record = logging.LogRecord(
                logger_name,
                logging.ERROR,
                "synthetic.py",
                1,
                message,
                (sensitive, 1.25),
                None,
            )
            record.job = "audit"
            integration._handle_record(record)
            integration._handle_sentry_logs_record(record)
            client.flush(timeout=2)
        payloads = {
            item.type: json.loads(item.get_bytes())
            for envelope in transport.envelopes
            for item in envelope.items
        }
        assert {"event", "log"} <= payloads.keys()
        for kind in ("event", "log"):
            encoded = json.dumps(payloads[kind])
            assert str(sensitive) not in encoded
            assert "[Filtered]" in encoded
            assert "1.25" in encoded and "audit" in encoded
    finally:
        client.close(timeout=2)


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
    formatted = json.loads(StructuredFormatter().format(record))["message"]
    filtered_url = f"https://discord.com/api/v10/{expected}"
    assert filtered_url in formatted
    assert _scrub({"exception": {"url": url}}) == {"exception": {"url": filtered_url}}


@pytest.mark.parametrize("verbose", [False, True])
def test_verbose_logging_keeps_dependency_payloads_out_of_logs(
    monkeypatch, capsys, verbose
):
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(root, "level", logging.NOTSET)
    for name in ("src", "discord.gateway", "tortoise.db_client", "aiosqlite"):
        monkeypatch.setattr(logging.getLogger(name), "level", logging.NOTSET)
    config = NS(verbose_logging=verbose, discord_token=None)
    monkeypatch.setattr(entrypoint.Settings, "from_env", lambda: config)
    monkeypatch.setattr(entrypoint, "configure_monitoring", lambda _: None)

    def run(*args, **kwargs):
        logging.getLogger("src.bot").debug("Application diagnostic")
        for name in ("discord.gateway", "tortoise.db_client", "aiosqlite"):
            logging.getLogger(name).debug("Private payload %s", "SYNTHETIC_PRIVATE")
            logging.getLogger(name).warning("Dependency warning")

    monkeypatch.setattr(entrypoint, "BotFraggBot", lambda _: NS(run=run))
    try:
        entrypoint.main()
        output = capsys.readouterr().err
        assert ("Application diagnostic" in output) is verbose
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
    assert synthetic_token not in StructuredFormatter().format(record)


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
    assert "AUDIT_SYNTHETIC_CODE" not in StructuredFormatter().format(record)


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
        cog.catalog_refresh,
        cog.log_flush,
    ):
        assert loop._before_loop is TasksCog.before_jobs


def test_error_tracking_scrubs_riot_credentials() -> None:
    """Verify that error tracking scrubs Riot credentials."""
    event = _scrub(
        {"extra": {"authorization": "Bearer secret", "profile": {"token": "abc"}}}
    )
    assert event == {
        "extra": {"authorization": "[Filtered]", "profile": {"token": "[Filtered]"}}
    }


def test_error_tracking_scrubs_compact_auth_fields_and_raw_tokens() -> None:
    """Verify that error tracking scrubs compact auth fields and raw tokens."""
    event = _scrub(
        {
            "extra": {
                "rso": "rso-secret",
                "idt": "id-token-secret",
                "ent": "entitlement-secret",
                "auth_blob": "encrypted-secret",
                "user_id": 123456789012345678,
            },
            "message": (
                "Bearer bearer-secret, refresh_token=refresh-secret, "
                "headerpayload.claimspayload.signaturepayload, "
                "notification failed for user 123456789012345678 <@123456789012345678>"
            ),
        }
    )
    assert event["extra"] == {
        "rso": "[Filtered]",
        "idt": "[Filtered]",
        "ent": "[Filtered]",
        "auth_blob": "[Filtered]",
        "user_id": "[Filtered]",
    }
    assert all(
        secret not in event["message"]
        for secret in (
            "bearer-secret",
            "refresh-secret",
            "headerpayload.claimspayload.signaturepayload",
            "123456789012345678",
        )
    )


def test_error_tracking_scrubs_riot_puuids() -> None:
    """Verify that error tracking scrubs Riot PUUIDs."""
    puuid = "123e4567-e89b-12d3-a456-426614174000"
    event = _scrub({"extra": {"puuid": puuid}, "message": f"failed for {puuid}"})

    assert event == {
        "extra": {"puuid": "[Filtered]"},
        "message": "failed for [Filtered]",
    }


def test_structured_logs_include_safe_extra_fields() -> None:
    """Verify that structured logs include safe extra fields."""
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

    payload = json.loads(StructuredFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "src.services.shop"
    assert payload["message"] == "Loaded account [Filtered]"
    assert payload["user_id"] == "[Filtered]"


def test_discord_log_handler_uses_the_scrubbed_structured_formatter() -> None:
    """Verify that Discord log handler uses the scrubbed structured formatter."""
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
    payload = json.loads(handler.messages[0])

    assert payload["message"] == "Failed for [Filtered]"
    assert payload["user_id"] == "[Filtered]"


def test_error_tracking_ignores_http_breadcrumbs_and_handles_null_category() -> None:
    """Verify that error tracking ignores HTTP breadcrumbs and handles null category."""
    assert monitoring._breadcrumb({"category": "aiohttp"}, {}) is None
    assert monitoring._breadcrumb({"category": None, "token": "secret"}, {}) == {
        "category": None,
        "token": "[Filtered]",
    }


def test_glitchtip_logs_keep_botfragg_events_and_drop_unrelated_or_url_data() -> None:
    """Verify that GlitchTip logs keep BotFragg events and drop unrelated or URL data."""
    assert monitoring._scrub_log(
        {
            "body": "Completed",
            "severity_text": "info",
            "attributes": {"logger.name": "src.cogs.events"},
        },
        {},
    ) == {
        "body": "Completed",
        "severity_text": "info",
        "attributes": {"logger.name": "src.cogs.events"},
    }
    assert (
        monitoring._scrub_log(
            {
                "body": "Noise",
                "severity_text": "info",
                "attributes": {"logger.name": "asyncio"},
            },
            {},
        )
        is None
    )
    assert (
        monitoring._scrub_log(
            {
                "body": "GET https://private.example",
                "severity_text": "info",
                "attributes": {"logger.name": "src.services.http"},
            },
            {},
        )["body"]
        == "HTTP request"
    )


def test_glitchtip_enables_supported_telemetry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that GlitchTip enables supported telemetry."""
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        monitoring.sentry_sdk, "init", lambda **kwargs: captured.update(kwargs)
    )
    monkeypatch.setattr(
        monitoring.sentry_sdk,
        "start_session",
        lambda: captured.setdefault("session", True),
    )
    monitoring.configure_monitoring(
        SimpleNamespace(
            glitchtip_dsn="http://key@localhost:8080/1",
            app_env="test",
            glitchtip_traces_sample_rate=1.0,
            glitchtip_profiles_sample_rate=1.0,
            glitchtip_logs_enabled=True,
        )
    )
    assert captured["dsn"] == "http://key@localhost:8080/1"
    assert captured["traces_sample_rate"] == captured["profiles_sample_rate"] == 1.0
    assert captured["auto_session_tracking"] is False
    assert captured["enable_logs"] is captured["session"] is True


def test_transaction_tracking_removes_request_data() -> None:
    """Verify that transaction tracking removes request data."""
    event = monitoring._scrub_transaction(
        {
            "request": {"url": "private"},
            "spans": [{"op": "http.client", "data": {"url": "private"}}],
        },
        {},
    )
    assert event == {"spans": [{"op": "http.client", "description": "HTTP request"}]}


def test_error_tracking_removes_request_data() -> None:
    """Verify that error tracking removes request data."""
    event = monitoring._scrub_event(
        {
            "request": {
                "url": "https://auth.riotgames.com/callback?code=secret&state=secret",
                "data": {"authorization": "Bearer secret"},
            },
            "message": "OAuth callback failed",
        }
    )

    assert event == {"message": "OAuth callback failed"}


def test_error_tracking_flushes_on_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that error tracking flushes on shutdown."""
    captured: dict[str, float | bool] = {}
    monkeypatch.setattr(
        monitoring.sentry_sdk,
        "end_session",
        lambda: captured.setdefault("session", True),
    )
    monkeypatch.setattr(
        monitoring.sentry_sdk,
        "flush",
        lambda *, timeout: captured.setdefault("timeout", timeout),
    )
    monitoring.flush_monitoring()
    assert captured == {"session": True, "timeout": 2.0}
