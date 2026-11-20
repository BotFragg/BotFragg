"""Pure payload builders for the public read-only HTTP API.

The builders convert in-memory Discord and catalog state into the JSON documents
served by :mod:`src.api`. They never touch the database and never read command
usage, so the public API cannot leak analytics or per-guild data.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class PublicParam:
    """Describe one application-command parameter for the public manifest."""

    name: str
    required: bool


@dataclass(frozen=True, slots=True)
class PublicCommand:
    """Describe one application command or command group for the manifest."""

    name: str
    qualified_name: str
    description: str
    guild_only: bool
    params: tuple[PublicParam, ...] = ()


def iso_timestamp(value: datetime | None = None) -> str:
    """Format a moment as an ISO-8601 UTC string with a trailing ``Z``."""
    moment = value or datetime.now(UTC)
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def installed_version() -> str:
    """Return the installed distribution version, or ``unknown`` when absent."""
    try:
        return package_version("botfragg")
    except PackageNotFoundError:
        return "unknown"


def discover_locales(root: Path) -> list[str]:
    """Return the sorted locale directory names shipped under ``root``."""
    try:
        entries = list(root.iterdir())
    except OSError:
        return []
    return sorted(entry.name for entry in entries if entry.is_dir())


def describe_commands(items: Iterable[Any]) -> list[PublicCommand]:
    """Flatten command-tree items into sorted public manifest entries.

    Commands marked ``extras["owner_only"]`` are excluded, matching the filter
    ``/help`` uses. Both a group and its subcommands appear as separate rows
    keyed by their qualified name.
    """
    described: list[PublicCommand] = []
    for item in items:
        extras = getattr(item, "extras", None) or {}
        if extras.get("owner_only"):
            continue
        parameters = getattr(item, "parameters", ())
        described.append(
            PublicCommand(
                name=item.name,
                qualified_name=item.qualified_name,
                description=getattr(item, "description", "") or "",
                guild_only=bool(getattr(item, "guild_only", False)),
                params=tuple(
                    PublicParam(name=parameter.name, required=parameter.required)
                    for parameter in parameters
                ),
            )
        )
    return sorted(described, key=lambda command: command.qualified_name)


def render_stats(
    *,
    servers: int,
    members: int,
    version: str,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the ``/v1/stats`` document from cached reach values only."""
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": iso_timestamp(generated_at),
        "bot": {"version": version},
        "reach": {"servers": servers, "members": members},
    }


def render_meta(
    *,
    version: str,
    locales: list[str],
    client_version: str | None,
    catalog_refreshed_at: datetime | None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the ``/v1/meta`` document describing build and catalog freshness."""
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": iso_timestamp(generated_at),
        "bot": {"version": version},
        "locales": sorted(locales),
        "riot": {
            "clientVersion": client_version or None,
            "catalogRefreshedAt": (
                iso_timestamp(catalog_refreshed_at)
                if catalog_refreshed_at is not None
                else None
            ),
        },
    }


def render_commands(
    commands: list[PublicCommand],
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the ``/v1/commands`` manifest from already-described commands."""
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": iso_timestamp(generated_at),
        "commands": [
            {
                "name": command.name,
                "qualifiedName": command.qualified_name,
                "description": command.description,
                "guildOnly": command.guild_only,
                "params": [
                    {"name": param.name, "required": param.required}
                    for param in command.params
                ],
            }
            for command in commands
        ],
    }
