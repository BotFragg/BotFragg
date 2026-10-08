"""Environment-backed settings, validation helpers, and repository paths."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
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


def _sample_rate(name: str, default: float) -> float:
    """Parse a telemetry sample rate constrained to the inclusive range 0 to 1."""
    value = float(os.getenv(name, str(default)))
    if not 0 <= value <= 1:
        raise ValueError(f"{name} must be between 0 and 1")
    return value


def _optional_int(name: str) -> int | None:
    """Return a positive optional integer setting, or ``None`` when it is blank."""
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive integer")
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


_DISCORD_WEBHOOK_HOSTS = {"discord.com", "discordapp.com"}
_DISCORD_WEBHOOK_PATH = re.compile(r"/api/webhooks/[0-9]{17,20}/[A-Za-z0-9._-]{60,}")


def _optional_webhook_url(name: str) -> str | None:
    """Validate an optional HTTPS Discord webhook URL and reject other hosts."""
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError(f"{name} must be a valid HTTPS Discord webhook URL") from None
    if (
        any(character.isspace() for character in value)
        or parsed.scheme != "https"
        or parsed.netloc not in _DISCORD_WEBHOOK_HOSTS
        or port is not None
        or _DISCORD_WEBHOOK_PATH.fullmatch(parsed.path) is None
    ):
        raise ValueError(f"{name} must be a valid HTTPS Discord webhook URL")
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
    discord_token: str
    database_url: str
    token_encryption_key: str
    auto_sync_commands: bool
    shard_count: int | None
    log_channel_id: int | None
    guild_join_log_channel_id: int | None
    guild_leave_log_channel_id: int | None
    shard_log_webhook_url: str | None
    shard_status_channel_id: int | None
    suggestion_log_channel_id: int | None
    support_url: str | None
    vote_url: str | None
    website_url: str | None
    glitchtip_dsn: str | None
    glitchtip_traces_sample_rate: float
    glitchtip_profiles_sample_rate: float
    glitchtip_logs_enabled: bool
    log_urls: bool
    verbose_logging: bool
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
    game_version_interval_minutes: int
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
            shard_count=_optional_int("SHARD_COUNT"),
            log_channel_id=_optional_int("LOG_CHANNEL_ID"),
            guild_join_log_channel_id=_optional_int("GUILD_JOIN_LOG_CHANNEL_ID"),
            guild_leave_log_channel_id=_optional_int("GUILD_LEAVE_LOG_CHANNEL_ID"),
            shard_log_webhook_url=_optional_webhook_url("SHARD_LOG_WEBHOOK_URL"),
            shard_status_channel_id=_optional_int("SHARD_STATUS_CHANNEL_ID"),
            suggestion_log_channel_id=_optional_int("SUGGESTION_LOG_CHANNEL_ID"),
            support_url=_optional_url("SUPPORT_URL"),
            vote_url=_optional_url("VOTE_URL"),
            website_url=_optional_url("WEBSITE_URL"),
            glitchtip_dsn=os.getenv("GLITCHTIP_DSN", "").strip() or None,
            glitchtip_traces_sample_rate=_sample_rate(
                "GLITCHTIP_TRACES_SAMPLE_RATE", 0.1
            ),
            glitchtip_profiles_sample_rate=_sample_rate(
                "GLITCHTIP_PROFILES_SAMPLE_RATE", 0.1
            ),
            glitchtip_logs_enabled=_bool("GLITCHTIP_LOGS_ENABLED", True),
            log_urls=_bool("LOG_URLS", False),
            verbose_logging=_bool("VERBOSE_LOGGING", False),
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
            game_version_interval_minutes=_int("GAME_VERSION_INTERVAL_MINUTES", 15, 1),
            user_agent_interval_minutes=_int("USER_AGENT_INTERVAL_MINUTES", 15, 1),
            log_flush_interval_seconds=_int("LOG_FLUSH_INTERVAL_SECONDS", 10, 1),
        )


settings = Settings.from_env(require_secrets=False)
