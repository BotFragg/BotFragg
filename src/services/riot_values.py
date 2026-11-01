"""Shared parsing helpers for values returned by Riot and VALORANT-API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def nonnegative(value: Any) -> int | None:
    """Convert a non-Boolean value to a nonnegative integer when possible."""
    if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
        return None
    try:
        result = int(value)
    except TypeError, ValueError, OverflowError:
        return None
    return result if result >= 0 else None


def positive(value: Any) -> int | None:
    """Convert a value to a positive integer or return ``None``."""
    return nonnegative(value) or None


def identifier(value: Any) -> str | None:
    """Return a usable Riot identifier, ignoring the empty UUID placeholder."""
    if not isinstance(value, str) or not value.strip("0-"):
        return None
    return value


def parse_datetime(value: Any) -> datetime | None:
    """Parse an ISO timestamp, assuming UTC when it carries no offset."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
