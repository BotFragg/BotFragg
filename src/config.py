"""Environment-backed settings, validation helpers, and repository paths."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, time
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(Path.cwd() / ".env")
load_dotenv(ROOT / ".env")


def _bool(name: str, default: bool) -> bool:
    """Parse a named environment variable as a strict boolean or use its default."""
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def _int(name: str, default: int, minimum: int = 0) -> int:
    """Parse an integer setting and reject values below its configured minimum."""
    value = int(os.getenv(name, str(default)))
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _optional_int(name: str, *, maximum: int | None = None) -> int | None:
    """Return a bounded optional positive integer setting, or ``None`` when blank."""
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if parsed <= 0 or (maximum is not None and parsed > maximum):
        raise ValueError(f"{name} must be a positive integer within bounds")
    return parsed


def _optional_url(name: str) -> str | None:
    """Validate and return an optional absolute HTTP(S) URL without userinfo."""
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError(f"{name} must be an absolute HTTP(S) URL") from None
    if (
        any(character.isspace() for character in value)
        or parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port == 0
    ):
        raise ValueError(f"{name} must be an absolute HTTP(S) URL")
    return value


def _time(name: str, default: str) -> time:
    """Parse an HH:MM or HH:MM:SS setting as a UTC wall-clock time."""
    raw = os.getenv(name, default)
    parts = [int(part) for part in raw.split(":")]
    if len(parts) not in {2, 3}:
        raise ValueError(f"{name} must use HH:MM or HH:MM:SS")
    hour, minute = parts[:2]
    second = parts[2] if len(parts) == 3 else 0
    return time(hour, minute, second, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable runtime configuration populated from environment variables."""

    app_env: str
    discord_token: str = field(repr=False)
    database_url: str
    token_encryption_key: str = field(repr=False)
    auto_sync_commands: bool
    shard_count: int | None
    log_channel_id: int | None
    guild_join_log_channel_id: int | None
    guild_leave_log_channel_id: int | None
    shard_status_channel_id: int | None
    support_url: str | None
    vote_url: str | None
    website_url: str | None
    log_urls: bool
    link_item_image: bool
    use_shop_cache: bool
    auto_refresh_tokens: bool
    max_accounts_per_user: int
    alerts_per_page: int
    alert_concurrency: int
    daily_alert_health_grace_seconds: int
    delay_between_alerts_seconds: int
    token_refresh_buffer_minutes: int
    rate_limit_backoff_seconds: int
    rate_limit_cap_seconds: int
    http_timeout_seconds: int
    alert_time_utc: time
    user_agent_interval_minutes: int
    log_flush_interval_seconds: int

    @classmethod
    def from_env(cls, *, require_secrets: bool = True) -> Settings:
        """Load settings, validate URLs and limits, and optionally require secrets.

        Args:
            require_secrets: Require the Discord token and Fernet encryption key.

        Returns:
            A validated settings instance for the current process.

        Raises:
            ValueError: If an environment value is malformed or required data is missing.
        """
        app_env = os.getenv("APP_ENV", "development").strip().lower()
        if app_env not in {"development", "production", "test"}:
            raise ValueError("APP_ENV must be development, production, or test")

        database_url = os.getenv("DATABASE_URL", "").strip()
        if app_env == "production" and not database_url:
            raise ValueError("DATABASE_URL is required in production")
        if not database_url:
            database_url = "sqlite://data/botfragg.sqlite3"

        token = os.getenv("DISCORD_TOKEN", "").strip()
        encryption_key = os.getenv("TOKEN_ENCRYPTION_KEY", "").strip()
        if require_secrets and not token:
            raise ValueError("DISCORD_TOKEN is required")
        if require_secrets and not encryption_key:
            raise ValueError("TOKEN_ENCRYPTION_KEY is required")
        if encryption_key:
            try:
                Fernet(encryption_key.encode("ascii"))
            except ValueError, UnicodeEncodeError:
                raise ValueError(
                    "TOKEN_ENCRYPTION_KEY must be a valid Fernet key"
                ) from None

        return cls(
            app_env=app_env,
            discord_token=token,
            database_url=database_url,
            token_encryption_key=encryption_key,
            auto_sync_commands=_bool("AUTO_SYNC_COMMANDS", True),
            shard_count=_optional_int("SHARD_COUNT", maximum=1000),
            log_channel_id=_optional_int("LOG_CHANNEL_ID"),
            guild_join_log_channel_id=_optional_int("GUILD_JOIN_LOG_CHANNEL_ID"),
            guild_leave_log_channel_id=_optional_int("GUILD_LEAVE_LOG_CHANNEL_ID"),
            shard_status_channel_id=_optional_int("SHARD_STATUS_CHANNEL_ID"),
            support_url=_optional_url("SUPPORT_URL"),
            vote_url=_optional_url("VOTE_URL"),
            website_url=_optional_url("WEBSITE_URL"),
            log_urls=_bool("LOG_URLS", False),
            link_item_image=_bool("LINK_ITEM_IMAGE", True),
            use_shop_cache=_bool("USE_SHOP_CACHE", True),
            auto_refresh_tokens=_bool("AUTO_REFRESH_TOKENS", True),
            max_accounts_per_user=_int("MAX_ACCOUNTS_PER_USER", 10, 1),
            alerts_per_page=_int("ALERTS_PER_PAGE", 10, 1),
            alert_concurrency=_int("ALERT_CONCURRENCY", 1, 1),
            daily_alert_health_grace_seconds=_int(
                "DAILY_ALERT_HEALTH_GRACE_SECONDS", 7200, 60
            ),
            delay_between_alerts_seconds=_int("DELAY_BETWEEN_ALERTS_SECONDS", 2, 0),
            token_refresh_buffer_minutes=_int("TOKEN_REFRESH_BUFFER_MINUTES", 5, 0),
            rate_limit_backoff_seconds=_int("RATE_LIMIT_BACKOFF_SECONDS", 60, 1),
            rate_limit_cap_seconds=_int("RATE_LIMIT_CAP_SECONDS", 3600, 1),
            http_timeout_seconds=_int("HTTP_TIMEOUT_SECONDS", 20, 1),
            alert_time_utc=_time("ALERT_TIME_UTC", "00:00:10"),
            user_agent_interval_minutes=_int("USER_AGENT_INTERVAL_MINUTES", 15, 1),
            log_flush_interval_seconds=_int("LOG_FLUSH_INTERVAL_SECONDS", 10, 1),
        )


settings = Settings.from_env(require_secrets=False)
