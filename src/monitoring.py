"""Plain-text log formatting and privacy filters for console and Discord logs."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

_BEARER_TOKEN = re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9._~+/-]+=*")
_DISCORD_ID = re.compile(
    r"(?i)\b(?:discord[ _-]?)?(?:user|guild|channel|member|owner|author|"
    r"follower|interaction|message)(?:[ _-]?id)?(?:\s*[:=]\s*|\s+)\d{15,22}\b"
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
_LEVEL_NAMES = {"CRITICAL": "CRIT", "WARNING": "WARN"}
_CATEGORY_OVERRIDES = {
    "src.bot": "bot",
    "src.health": "jobs",
    "src.cogs.events": "command",
    "src.cogs.extra": "bot",
    "src.cogs.tasks": "jobs",
    "src.database": "database",
    "src.localization": "localization",
    "src.monitoring": "logging",
    "src.services.crosshair_render": "crosshair",
    "src.services.valorant_status": "status",
}
_CATEGORY_PREFIXES = (
    ("discord.", "discord"),
    ("tortoise", "database"),
    ("aiosqlite", "database"),
    ("asyncpg", "database"),
    ("aiohttp", "http"),
)


def _category(name: str) -> str:
    """Return a short operator-facing category for a logger name."""
    if name in _CATEGORY_OVERRIDES:
        return _CATEGORY_OVERRIDES[name]
    for prefix, category in _CATEGORY_PREFIXES:
        if name.startswith(prefix):
            return category
    parts = name.split(".")
    return parts[-1] if parts and parts[-1] else "app"


class PlainFormatter(logging.Formatter):
    """Render one scrubbed log record as a human-readable line."""

    def format(self, record: logging.LogRecord) -> str:
        """Render timestamp, level, category, scrubbed message, and traceback."""
        timestamp = datetime.fromtimestamp(record.created, UTC).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
        level = _LEVEL_NAMES.get(record.levelname, record.levelname)
        line = (
            f"{timestamp}  {level:<5}  [{_category(record.name)}] "
            f"{_scrub(record.getMessage())}"
        )
        if record.exc_info:
            line += "\n" + _scrub(self.formatException(record.exc_info))
        return line


def _scrub(value: str) -> str:
    """Filter credentials and personal identifiers from log text."""
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
