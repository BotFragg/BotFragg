"""Tests for schema migrations and database connection setup."""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from tortoise import Tortoise, connections
from tortoise.exceptions import IntegrityError, OperationalError
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
        if url.startswith("postgres"):
            _, rows = await connections.get("default").execute_query(
                "SELECT data_type FROM information_schema.sequences "
                "WHERE sequence_name = 'commandinvocation_id_seq' "
                "AND sequence_schema = current_schema()"
            )
            assert rows[0]["data_type"] == "bigint"
        user = await User.create(id=101)
        account = await Account.create(
            puuid="synthetic", user=user, username="Synthetic"
        )
        skin = UUID("00000000-0000-0000-0000-000000000001")
        await Alert.create(account=account, skin_uuid=skin)
        with pytest.raises(IntegrityError):
            await Alert.create(account=account, skin_uuid=skin)
        await CommandInvocation.create(user_id=user.id, command="synthetic")
        large = await CommandInvocation.create(
            id=2**31, user_id=user.id, command="synthetic-large"
        )
        assert large.id == 2**31
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


async def test_shop_sharing_migration_backfills_existing_users(migration_url):
    """Verify that opting in survives a rollback and existing users start private."""
    apps = TORTOISE_CONFIG["apps"]
    await Tortoise.init(
        config={
            "connections": {"default": migration_url},
            "apps": apps,
            "use_tz": True,
            "timezone": "UTC",
        }
    )
    try:
        executor = MigrationExecutor(connections.get("default"), apps)
        await executor.migrate(
            [MigrationTarget("models", "0004_add_shard_status_message")]
        )
        await User.create(id=101, others_can_view_shop=True)
        await executor.migrate([MigrationTarget("models", "0005_shop_sharing_opt_in")])
        assert (await User.get(id=101)).others_can_view_shop is False
        await executor.migrate(
            [MigrationTarget("models", "0004_add_shard_status_message")]
        )
        # Rolling back must not publish shops the user chose to keep private.
        assert (await User.get(id=101)).others_can_view_shop is False
    finally:
        await Tortoise.close_connections()


@pytest.mark.parametrize(
    ("message", "raises"),
    [
        ("index idx_account_user_id_synthetic already exists", False),
        ("disk I/O error", True),
    ],
)
async def test_index_migration_tolerates_a_preexisting_index(message, raises) -> None:
    """A dev database may already have the index from schema generation."""
    module = importlib.import_module(
        "src.migrations.0006_index_owners_and_widen_analytics"
    )
    editor = SimpleNamespace(add_index=AsyncMock(side_effect=OperationalError(message)))
    apps = SimpleNamespace(get_model=lambda *_args: SimpleNamespace())

    if raises:
        with pytest.raises(OperationalError):
            await module._create_account_index(apps, editor)
    else:
        await module._create_account_index(apps, editor)


@pytest.mark.parametrize(
    ("max_id", "sequence_value", "refused"),
    [
        (2**31, 1, True),
        (1, 2**31, True),
        (None, 1, False),
        (2**31 - 1, 2**31 - 1, False),
    ],
)
async def test_rollback_guard_checks_ids_and_sequence(
    max_id, sequence_value, refused
) -> None:
    """Rolling back must not silently narrow a column that no longer fits."""
    module = importlib.import_module(
        "src.migrations.0006_index_owners_and_widen_analytics"
    )
    client = SimpleNamespace(
        execute_query=AsyncMock(
            return_value=(1, [{"max_id": max_id, "sequence_value": sequence_value}])
        )
    )
    editor = SimpleNamespace(DIALECT="postgres", client=client)

    if refused:
        with pytest.raises(RuntimeError):
            await module._guard_rollback(None, editor)
    else:
        await module._guard_rollback(None, editor)


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

    sharing_module = importlib.import_module("src.migrations.0005_shop_sharing_opt_in")
    assert sharing_module.Migration.dependencies == [
        ("models", "0004_add_shard_status_message")
    ]
    assert [
        type(operation).__name__ for operation in sharing_module.Migration.operations
    ] == ["AlterField", "RunPython"]

    index_module = importlib.import_module(
        "src.migrations.0006_index_owners_and_widen_analytics"
    )
    assert index_module.Migration.dependencies == [
        ("models", "0005_shop_sharing_opt_in")
    ]
    assert [
        type(operation).__name__ for operation in index_module.Migration.operations
    ] == ["RunPython", "AlterField", "RunPython"]

    options_module = importlib.import_module("src.migrations.0007_record_model_options")
    assert options_module.Migration.dependencies == [
        ("models", "0006_index_owners_and_widen_analytics")
    ]
    assert {
        type(operation).__name__ for operation in options_module.Migration.operations
    } == {"AlterModelOptions"}
    assert len(options_module.Migration.operations) == 7


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
