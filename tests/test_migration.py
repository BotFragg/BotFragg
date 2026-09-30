"""Tests for schema migrations and database connection setup."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.database as database
from src.config import Settings
from src.database import TORTOISE_CONFIG


def test_sqlite_in_memory_url_is_preserved() -> None:
    """Verify that the SQLite in-memory URL is preserved."""
    assert database._database_url("sqlite://:memory:") == "sqlite://:memory:"


def test_native_initial_migration_matches_current_models() -> None:
    """Verify that native initial migration matches current models."""
    path = Path(__file__).parents[1] / "src" / "migrations" / "0001_initial.py"
    spec = importlib.util.spec_from_file_location("initial_migration", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    assert TORTOISE_CONFIG["apps"]["models"]["migrations"] == "src.migrations"
    assert module.Migration.initial is True
    assert {operation.name for operation in module.Migration.operations} == {
        "User",
        "Account",
        "Alert",
    }

    analytics = (
        Path(__file__).parents[1]
        / "src"
        / "migrations"
        / "0002_add_command_analytics.py"
    )
    analytics_spec = importlib.util.spec_from_file_location(
        "analytics_migration", analytics
    )
    analytics_module = importlib.util.module_from_spec(analytics_spec)
    assert analytics_spec and analytics_spec.loader
    analytics_spec.loader.exec_module(analytics_module)
    assert analytics_module.Migration.dependencies == [("models", "0001_initial")]
    assert [operation.name for operation in analytics_module.Migration.operations] == [
        "CommandInvocation"
    ]

    suggestions = (
        Path(__file__).parents[1] / "src" / "migrations" / "0003_add_suggestions.py"
    )
    suggestions_spec = importlib.util.spec_from_file_location(
        "suggestions_migration", suggestions
    )
    suggestions_module = importlib.util.module_from_spec(suggestions_spec)
    assert suggestions_spec and suggestions_spec.loader
    suggestions_spec.loader.exec_module(suggestions_module)
    assert suggestions_module.Migration.dependencies == [
        ("models", "0002_add_command_analytics")
    ]
    assert {
        operation.name for operation in suggestions_module.Migration.operations
    } == {
        "Suggestion",
        "SuggestionFollower",
    }

    status = (
        Path(__file__).parents[1]
        / "src"
        / "migrations"
        / "0004_add_shard_status_message.py"
    )
    status_spec = importlib.util.spec_from_file_location("status_migration", status)
    status_module = importlib.util.module_from_spec(status_spec)
    assert status_spec and status_spec.loader
    status_spec.loader.exec_module(status_module)
    assert status_module.Migration.dependencies == [("models", "0003_add_suggestions")]
    assert [operation.name for operation in status_module.Migration.operations] == [
        "ShardStatusMessage"
    ]


@pytest.mark.asyncio
async def test_connect_database_uses_passed_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that connect database uses passed settings."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "postgres://runtime/database")
    settings = Settings.from_env(require_secrets=False)
    initialized: dict[str, object] = {}
    generated: dict[str, object] = {}

    class Runtime:
        """Stub Tortoise's model registry and schema-generation call during database setup."""

        @staticmethod
        async def init(*, config: dict[str, object]) -> None:
            """Record the ORM configuration passed to database initialization."""
            initialized.update(config)

        @staticmethod
        async def generate_schemas(*, safe: bool) -> None:
            """Record whether schema generation was requested."""
            generated["safe"] = safe

    monkeypatch.setattr(database, "Tortoise", Runtime)

    await database.connect_database(settings, generate_schemas=True)

    assert initialized["connections"] == {"default": "postgres://runtime/database"}
    assert initialized["apps"]["models"]["migrations"] == "src.migrations"
    assert generated == {"safe": True}


@pytest.mark.asyncio
async def test_ping_database_queries_the_default_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that ping database queries the default connection."""
    calls: list[str] = []

    class Connection:
        """Capture the health-check SQL sent to Tortoise's default database connection."""

        async def execute_query(self, query: str) -> None:
            """Record the query and return the configured fake database result."""
            calls.append(query)

    def get_connection(alias: str) -> Connection:
        """Return the fake default database connection."""
        calls.append(alias)
        return Connection()

    monkeypatch.setattr(database, "connections", SimpleNamespace(get=get_connection))

    await database.ping_database()

    assert calls == ["default", "SELECT 1"]
