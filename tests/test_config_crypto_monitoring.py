"""Tests for settings validation, credential encryption, and privacy filters."""

from __future__ import annotations

import json
import logging
import time
from types import SimpleNamespace

import discord
import pytest
from cryptography.fernet import Fernet

from src import monitoring
from src.cogs.tasks import DiscordLogHandler
from src.config import Settings
from src.monitoring import StructuredFormatter, _scrub
from src.services.auth import decode_jwt, token_expiry
from src.services.crypto import AuthVault
from src.services.http import _safe_log_url

_OPTIONAL_URLS = (
    "SUPPORT_URL",
    "VOTE_URL",
    "WEBSITE_URL",
    "SHARD_LOG_WEBHOOK_URL",
)


def _clear_optional_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear optional URL variables so settings tests use a controlled environment."""
    monkeypatch.setenv("APP_ENV", "test")
    for name in _OPTIONAL_URLS:
        monkeypatch.delenv(name, raising=False)


def test_settings_choose_sqlite_for_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that settings choose SQLite for development."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DISCORD_TOKEN", "token")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = Settings.from_env()
    assert config.database_url == "sqlite://data/botfragg.sqlite3"
    assert config.max_accounts_per_user == 10


def test_settings_reject_invalid_token_encryption_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that settings reject invalid token encryption key."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DISCORD_TOKEN", "token")
    key = "not-a-valid-fernet-key"
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", key)

    with pytest.raises(
        ValueError, match="TOKEN_ENCRYPTION_KEY must be a valid Fernet key"
    ) as raised:
        Settings.from_env()

    assert key not in str(raised.value)


@pytest.mark.parametrize("name", ["SHARD_COUNT", "LOG_CHANNEL_ID"])
@pytest.mark.parametrize("value", ["0", "-1", "not-an-int"])
def test_settings_reject_non_positive_ids(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    """Verify that settings reject zero and negative IDs."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=f"{name} must be a positive integer"):
        Settings.from_env(require_secrets=False)


def test_settings_treat_blank_optional_urls_as_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that blank optional URLs are treated as unset."""
    _clear_optional_urls(monkeypatch)
    for name in _OPTIONAL_URLS:
        monkeypatch.setenv(name, " \t ")

    config = Settings.from_env(require_secrets=False)

    assert (
        config.support_url,
        config.vote_url,
        config.website_url,
        config.shard_log_webhook_url,
    ) == (None, None, None, None)


@pytest.mark.parametrize("name", ["SUPPORT_URL", "VOTE_URL", "WEBSITE_URL"])
@pytest.mark.parametrize("value", ["https://example.com/help", "http://example.com"])
def test_settings_accept_http_links(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    """Verify that settings accept HTTP links."""
    _clear_optional_urls(monkeypatch)
    monkeypatch.setenv(name, value)

    config = Settings.from_env(require_secrets=False)

    assert getattr(config, name.lower()) == value


@pytest.mark.parametrize("name", ["SUPPORT_URL", "VOTE_URL", "WEBSITE_URL"])
@pytest.mark.parametrize(
    "value",
    [
        "relative/path",
        "//example.com/help",
        "ftp://example.com/help",
        "https:///missing-host",
        "https://example.com:bad/help",
        "https://user:password@example.com/help",
    ],
)
def test_settings_reject_invalid_http_links_without_echoing_value(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    """Verify that settings reject invalid HTTP links without echoing value."""
    _clear_optional_urls(monkeypatch)
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=name) as raised:
        Settings.from_env(require_secrets=False)

    assert value not in str(raised.value)


@pytest.mark.parametrize("host", ["discord.com", "discordapp.com"])
def test_settings_accept_webhook_urls_supported_by_discord_py(
    monkeypatch: pytest.MonkeyPatch, host: str
) -> None:
    """Verify that settings accept webhook URLs supported by discord.py."""
    _clear_optional_urls(monkeypatch)
    webhook_id = "123456789012345678"
    token = "a" * 60
    value = f"https://{host}/api/webhooks/{webhook_id}/{token}"
    monkeypatch.setenv("SHARD_LOG_WEBHOOK_URL", value)

    config = Settings.from_env(require_secrets=False)
    parsed = discord.Webhook.from_url(value, session=object())

    assert config.shard_log_webhook_url == value
    assert parsed.id == int(webhook_id)


@pytest.mark.parametrize(
    "value",
    [
        "http://discord.com/api/webhooks/123456789012345678/" + "a" * 60,
        "https://evil.discord.com/api/webhooks/123456789012345678/" + "a" * 60,
        "https://discord.com:443/api/webhooks/123456789012345678/" + "a" * 60,
        "https://discord.com/api/webhooks/1234567890123456/" + "a" * 60,
        "https://discord.com/api/webhooks/123456789012345678/" + "a" * 59,
        "https://discord.com/api/webhooks/123456789012345678/" + "a" * 60 + "/extra",
        "https://user@discord.com/api/webhooks/123456789012345678/" + "a" * 60,
        "https://discord.com/api/webhooks/not-a-webhook",
    ],
)
def test_settings_reject_invalid_webhook_urls_without_echoing_token(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Verify that settings reject invalid webhook urls without echoing token."""
    _clear_optional_urls(monkeypatch)
    monkeypatch.setenv("SHARD_LOG_WEBHOOK_URL", value)

    with pytest.raises(ValueError, match="SHARD_LOG_WEBHOOK_URL") as raised:
        Settings.from_env(require_secrets=False)

    assert value not in str(raised.value)


def test_settings_load_glitchtip_tracking(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that settings load GlitchTip tracking."""
    monkeypatch.setenv("GLITCHTIP_DSN", "http://key@localhost:8080/1")
    monkeypatch.setenv("GLITCHTIP_TRACES_SAMPLE_RATE", "0.5")
    config = Settings.from_env(require_secrets=False)
    assert (config.glitchtip_dsn, config.glitchtip_traces_sample_rate) == (
        "http://key@localhost:8080/1",
        0.5,
    )


def test_production_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that production requires database URL."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DISCORD_TOKEN", "token")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="DATABASE_URL"):
        Settings.from_env()


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


def test_http_log_urls_remove_account_ids_credentials_and_queries() -> None:
    """Verify that HTTP log urls remove account IDs credentials and queries."""
    puuid = "123e4567-e89b-12d3-a456-426614174000"
    safe_url = _safe_log_url(
        f"https://user:password@pd.na.a.pvp.net/store/v3/storefront/{puuid}"
        "?token=secret"
    )

    assert safe_url == "https://pd.na.a.pvp.net/store/v3/storefront/[Filtered]"
    assert puuid not in safe_url
    assert "password" not in safe_url
    assert "secret" not in safe_url


def test_error_tracking_ignores_http_breadcrumbs_and_handles_null_category() -> None:
    """Verify that error tracking ignores HTTP breadcrumbs and handles null category."""
    assert monitoring._breadcrumb({"category": "aiohttp"}, {}) is None
    assert monitoring._breadcrumb({"category": None, "token": "secret"}, {}) == {
        "category": None,
        "token": "[Filtered]",
    }


def test_glitchtip_logs_keep_botfragg_events_and_drop_unrelated_or_url_data() -> None:
    """Verify that GlitchTip logs keep Botfragg events and drop unrelated or URL data."""
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


def test_auth_vault_round_trip_and_wrong_key() -> None:
    """Verify that credential encryption round-trips and rejects the wrong key."""
    first = AuthVault(Fernet.generate_key().decode())
    second = AuthVault(Fernet.generate_key().decode())
    encrypted = first.encrypt({"rso": "secret", "refresh_token": "rotating"})
    assert "secret" not in encrypted
    assert first.decrypt(encrypted) == {"refresh_token": "rotating", "rso": "secret"}
    with pytest.raises(ValueError, match="cannot be decrypted"):
        second.decrypt(encrypted)


def test_jwt_decode_and_expiry() -> None:
    """Verify that JWT decode and expiry."""
    import base64
    import json

    expires = int(time.time()) + 3600
    payload = (
        base64.urlsafe_b64encode(json.dumps({"sub": "puuid", "exp": expires}).encode())
        .decode()
        .rstrip("=")
    )
    token = f"x.{payload}.y"
    assert decode_jwt(token)["sub"] == "puuid"
    assert token_expiry(token) == expires
    assert decode_jwt("broken") == {}
