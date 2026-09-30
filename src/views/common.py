"""Shared Discord presentation helpers used across Botfragg cogs."""

from __future__ import annotations

from datetime import datetime


def timestamp(value: int | float | datetime, style: str = "R") -> str:
    """Format a timestamp as a Discord inline timestamp using the requested style."""
    seconds = int(value.timestamp()) if isinstance(value, datetime) else int(value)
    return f"<t:{seconds}:{style}>"
