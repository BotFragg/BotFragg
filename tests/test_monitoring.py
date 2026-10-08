"""Behavior and regression checks for monitoring."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest

from src import monitoring
from src.cogs.tasks import DiscordLogHandler
from src.monitoring import StructuredFormatter, _scrub


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
