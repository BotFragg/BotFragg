"""Behavior and regression checks by responsibility."""

from __future__ import annotations

import discord
import pytest
from cryptography.fernet import Fernet

from src.config import Settings

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
