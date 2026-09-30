"""Database URL normalization, Tortoise setup, and shard-status persistence."""

from __future__ import annotations

from tortoise import Tortoise, connections

from .config import ROOT, Settings, settings
from .models import ShardStatusMessage


def _database_url(url: str) -> str:
    """Resolve relative SQLite paths against the repository root."""
    if url == "sqlite://:memory:":
        return url
    if url.startswith("sqlite://") and not url.startswith("sqlite:///"):
        relative = url.removeprefix("sqlite://")
        target = (ROOT / relative).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite://{target.as_posix()}"
    return url


def _tortoise_config(config: Settings) -> dict[str, object]:
    """Build the ORM configuration for the supplied application settings."""
    return {
        "connections": {"default": _database_url(config.database_url)},
        "apps": {
            "models": {
                "models": ["src.models.entities"],
                "default_connection": "default",
                "migrations": "src.migrations",
            }
        },
        "use_tz": True,
        "timezone": "UTC",
    }


TORTOISE_CONFIG = _tortoise_config(settings)


async def connect_database(config: Settings, *, generate_schemas: bool = False) -> None:
    """Initialize Tortoise and optionally create missing development schemas."""
    await Tortoise.init(config=_tortoise_config(config))
    if generate_schemas:
        await Tortoise.generate_schemas(safe=True)


async def ping_database() -> None:
    """Run a minimal query against the default database connection."""
    await connections.get("default").execute_query("SELECT 1")


async def close_database() -> None:
    """Close all Tortoise database connections."""
    await Tortoise.close_connections()


async def get_shard_status_message_id(channel_id: int) -> int | None:
    """Return the saved status-message ID for a channel, if one exists."""
    saved = await ShardStatusMessage.get_or_none(channel_id=channel_id)
    return saved.message_id if saved else None


async def save_shard_status_message(channel_id: int, message_id: int) -> None:
    """Create or update the status-message reference for a channel."""
    await ShardStatusMessage.update_or_create(
        channel_id=channel_id, defaults={"message_id": message_id}
    )
