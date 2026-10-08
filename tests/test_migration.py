"""Tests for schema migrations and database connection setup."""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from uuid import UUID

import pytest
from tortoise import Tortoise, connections
from tortoise.exceptions import IntegrityError
from tortoise.migrations.executor import MigrationExecutor, MigrationTarget

import src.database as database
from src.config import Settings
from src.database import TORTOISE_CONFIG
from src.models import (
    Account,
    Alert,
    CommandInvocation,
    ShardStatusMessage,
    Suggestion,
    SuggestionFollower,
    User,
)
from src.services.accounts import delete_user_data


async def test_migrations_apply_write_delete_and_rollback(migration_url):
    """Exercise the actual migration chain and model constraints on both backends."""
    url = migration_url
    apps = TORTOISE_CONFIG["apps"]
    await Tortoise.init(
        config={
            "connections": {"default": url},
            "apps": apps,
            "use_tz": True,
            "timezone": "UTC",
        }
    )
    try:
        executor = MigrationExecutor(connections.get("default"), apps)
        await executor.migrate()
        await executor.migrate()
        user = await User.create(id=101)
        account = await Account.create(
            puuid="synthetic", user=user, username="Synthetic"
        )
        skin = UUID("00000000-0000-0000-0000-000000000001")
        await Alert.create(account=account, skin_uuid=skin)
        with pytest.raises(IntegrityError):
            await Alert.create(account=account, skin_uuid=skin)
        await CommandInvocation.create(user_id=user.id, command="synthetic")
        suggestion = await Suggestion.create(author_id=user.id, content="Synthetic")
        await SuggestionFollower.create(suggestion=suggestion, user_id=user.id)
        await ShardStatusMessage.create(channel_id=101, message_id=201)
        assert await account.persisted_row().exists()
        assert await delete_user_data(user.id)
        for model in (
            User,
            Account,
            Alert,
            CommandInvocation,
            Suggestion,
            SuggestionFollower,
        ):
            assert not await model.exists()
        await executor.migrate([MigrationTarget("models", "0003_add_suggestions")])
        await executor.migrate()
        await ShardStatusMessage.create(channel_id=102, message_id=202)
        assert await ShardStatusMessage.exists(channel_id=102)
    finally:
        await Tortoise.close_connections()


def test_sqlite_in_memory_url_is_preserved() -> None:
    """Verify that the SQLite in-memory URL is preserved."""
    assert database._database_url("sqlite://:memory:") == "sqlite://:memory:"


def test_native_initial_migration_matches_current_models() -> None:
    """Verify that native initial migration matches current models."""
    module = importlib.import_module("src.migrations.0001_initial")

    assert TORTOISE_CONFIG["apps"]["models"]["migrations"] == "src.migrations"
    assert module.Migration.initial is True
    assert {operation.name for operation in module.Migration.operations} == {
        "User",
        "Account",
        "Alert",
    }

    analytics_module = importlib.import_module(
        "src.migrations.0002_add_command_analytics"
    )
    assert analytics_module.Migration.dependencies == [("models", "0001_initial")]
    assert [operation.name for operation in analytics_module.Migration.operations] == [
        "CommandInvocation"
    ]

    suggestions_module = importlib.import_module("src.migrations.0003_add_suggestions")
    assert suggestions_module.Migration.dependencies == [
        ("models", "0002_add_command_analytics")
    ]
    assert {
        operation.name for operation in suggestions_module.Migration.operations
    } == {
        "Suggestion",
        "SuggestionFollower",
    }

    status_module = importlib.import_module(
        "src.migrations.0004_add_shard_status_message"
    )
    assert status_module.Migration.dependencies == [("models", "0003_add_suggestions")]
    assert [operation.name for operation in status_module.Migration.operations] == [
        "ShardStatusMessage"
    ]


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
