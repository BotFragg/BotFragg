"""Plain-text log formatting and privacy filters for console and Discord logs."""

from __future__ import annotations

import copy
import logging
import re
from typing import Any

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
_STANDARD_LOG_FIELDS = frozenset(logging.makeLogRecord({}).__dict__)
LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s %(message)s"


class PlainFormatter(logging.Formatter):
    """Render a scrubbed log record as plain text for console output."""

    def format(self, record: logging.LogRecord) -> str:
        """Scrub the message, structured fields, and traceback, then render a line."""
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_LOG_FIELDS
        }
        rendered = _scrub(record.getMessage())
        if extras:
            rendered += "  " + " ".join(
                f"{key}={value}" for key, value in _scrub(extras).items()
            )
        if record.exc_info:
            rendered += "\n" + _scrub(self.formatException(record.exc_info))
        # Handlers share one record, so render a copy: stdlib formatting leaves
        # `message` and `asctime` behind, which would corrupt structured output.
        clone = copy.copy(record)
        clone.msg, clone.args, clone.exc_info = rendered, None, None
        return super().format(clone)


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
