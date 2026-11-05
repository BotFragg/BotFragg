"""Behavior and regression checks by responsibility."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from src.config import Settings

_OPTIONAL_URLS = (
    "SUPPORT_URL",
    "VOTE_URL",
    "WEBSITE_URL",
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

    assert (config.support_url, config.vote_url, config.website_url) == (
        None,
        None,
        None,
    )


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


def test_production_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that production requires database URL."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DISCORD_TOKEN", "token")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="DATABASE_URL"):
        Settings.from_env()


@pytest.mark.parametrize("value", ["0", "-1", "1001", "5000"])
def test_shard_count_is_bounded(monkeypatch, value):
    """An out-of-range shard count must fail fast instead of stalling startup."""
    monkeypatch.setenv("SHARD_COUNT", value)
    with pytest.raises(ValueError, match="SHARD_COUNT"):
        Settings.from_env(require_secrets=False)
