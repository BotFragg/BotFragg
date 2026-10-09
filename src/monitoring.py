"""Structured logging and privacy filters for logs and GlitchTip events."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any

import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration

from .config import Settings

if TYPE_CHECKING:
    from sentry_sdk._types import Event, Log

_SENSITIVE_KEY_PARTS = (
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
    "discord_id",
    "user_id",
    "guild_id",
    "channel_id",
    "member_id",
    "owner_id",
    "author_id",
    "message_id",
    "interaction_id",
    "puuid",
)
_COMPACT_AUTH_KEYS = {"auth_blob", "rso", "idt", "ent"}
_BEARER_TOKEN = re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9._~+/-]+=*")
_DISCORD_ID = re.compile(
    r"(?i)\b(?:discord[ _-]?)?(?:user|guild|channel|member|owner|author|"
    r"interaction|message)(?:[ _-]?id)?(?:\s*[:=]\s*|\s+)\d{15,22}\b"
    r"|<[@#][!&]?\d{15,22}>"
)
_DISCORD_URL_ID = re.compile(
    r"(?i)(/(?:channels|guilds|users|members|messages|roles|webhooks|"
    r"interactions|applications)/)\d{15,22}\b"
)
_LABELED_SECRET = re.compile(
    r"(?i)\b(authorization|cookie|credential|password|secret|token|rso|idt|ent|"
    r"auth[_ -]?blob|access[_ -]?token|refresh[_ -]?token|id[_ -]?token)\b"
    r"([\"']?\s*[:=]\s*)([\"']?)([^\"'\s,;]+)\3"
)
_JWT = re.compile(
    r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"
    r"\.[A-Za-z0-9_-]{8,}(?![A-Za-z0-9_-])"
)
_UUID = re.compile(r"(?i)\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b")
_WEBHOOK_SECRET = re.compile(
    r"(?i)(/api/(?:v\d+/)?(?:webhooks|interactions)/\d+/)[A-Za-z0-9._-]+"
)
_OAUTH_SECRET = re.compile(
    r"(?i)([?&#](?:code|state|nonce|access_token|refresh_token|id_token)=)[^&#\s\"'\\]+"
)
_STANDARD_LOG_FIELDS = frozenset(logging.makeLogRecord({}).__dict__)


class StructuredFormatter(logging.Formatter):
    """Format log records as JSON after filtering sensitive values."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize a scrubbed log record and its safe structured fields."""
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_LOG_FIELDS
        }
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": _scrub(record.getMessage()),
            **_scrub(extras),
        }
        if record.exc_info:
            payload["exception"] = _scrub(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


def _scrub(value: Any) -> Any:
    """Filter credentials and personal identifiers from nested event data."""
    if isinstance(value, dict):
        return {
            key: "[Filtered]"
            if str(key).lower() in _COMPACT_AUTH_KEYS
            or any(part in str(key).lower() for part in _SENSITIVE_KEY_PARTS)
            else _scrub(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, str):
        value = _WEBHOOK_SECRET.sub(r"\1[Filtered]", value)
        value = _OAUTH_SECRET.sub(r"\1[Filtered]", value)
        value = _BEARER_TOKEN.sub(r"\1[Filtered]", value)
        value = _LABELED_SECRET.sub(
            lambda match: (
                f"{match.group(1)}{match.group(2)}"
                f"{match.group(3)}[Filtered]{match.group(3)}"
            ),
            value,
        )
        value = _JWT.sub("[Filtered]", value)
        value = _UUID.sub("[Filtered]", value)
        value = _DISCORD_URL_ID.sub(r"\1[Filtered]", value)
        return _DISCORD_ID.sub("[Filtered]", value)
    return value


def _breadcrumb(
    breadcrumb: dict[str, Any], hint: dict[str, Any]
) -> dict[str, Any] | None:
    """Drop network and unrelated log breadcrumbs, then scrub retained data."""
    category = str(breadcrumb.get("category") or "")
    if category.startswith(("http", "aiohttp")):
        return None
    if breadcrumb.get("type") == "log" and not category.startswith(
        ("src.", "discord.")
    ):
        return None
    return _scrub(breadcrumb)


def _scrub_event(event: Event) -> Event:
    """Remove request data and sensitive values from an error event."""
    event = _scrub(event)
    event.pop("request", None)
    return event


def _scrub_transaction(event: Event, hint: dict[str, Any]) -> Event:
    """Remove request payloads and HTTP span details from a transaction."""
    event = _scrub_event(event)
    spans = event.get("spans", [])
    for span in spans if isinstance(spans, list) else []:
        span.pop("data", None)
        if str(span.get("op") or "").startswith("http"):
            span["description"] = "HTTP request"
    return event


def _scrub_log(log: Log, hint: dict[str, Any]) -> Log | None:
    """Keep BotFragg logs and serious Discord errors after removing URL data."""
    attributes = log.get("attributes", {})
    logger_name = str(attributes.get("logger.name") or "")
    severity = str(log.get("severity_text") or "")
    if not logger_name.startswith("src.") and not (
        logger_name.startswith("discord.") and severity in {"warn", "error", "fatal"}
    ):
        return None
    if "://" in str(log.get("body") or ""):
        log["body"] = "HTTP request"
    return _scrub(log)


def _release() -> str:
    """Return the installed BotFragg release label or an unknown fallback."""
    try:
        return f"botfragg@{version('botfragg')}"
    except PackageNotFoundError:
        return "botfragg@unknown"


def configure_monitoring(config: Settings) -> None:
    """Enable privacy-filtered GlitchTip telemetry when a DSN is configured."""
    if not config.glitchtip_dsn:
        return
    sentry_sdk.init(
        dsn=config.glitchtip_dsn,
        environment=config.app_env,
        release=_release(),
        send_default_pii=False,
        include_local_variables=False,
        traces_sample_rate=config.glitchtip_traces_sample_rate,
        profiles_sample_rate=config.glitchtip_profiles_sample_rate,
        enable_logs=config.glitchtip_logs_enabled,
        auto_session_tracking=False,
        trace_propagation_targets=[],
        integrations=[
            LoggingIntegration(
                level=logging.WARNING,
                event_level=logging.ERROR,
                sentry_logs_level=logging.INFO,
            )
        ],
        before_send=lambda event, hint: _scrub_event(event),
        before_send_transaction=_scrub_transaction,
        before_send_log=_scrub_log,
        before_breadcrumb=_breadcrumb,
    )
    sentry_sdk.start_session()


def transaction(name: str, op: str):
    """Start a GlitchTip transaction with the supplied name and operation."""
    return sentry_sdk.start_transaction(name=name, op=op)


def flush_monitoring() -> None:
    """End the current monitoring session and flush queued telemetry."""
    sentry_sdk.end_session()
    sentry_sdk.flush(timeout=2.0)
