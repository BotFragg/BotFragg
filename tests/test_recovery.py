"""Verify restored data and keys without modifying the restored database."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit, urlunsplit

import pytest
from cryptography.fernet import Fernet
from tortoise import Tortoise, connections
from tortoise.migrations.executor import MigrationExecutor

from src.database import TORTOISE_CONFIG
from src.models import Account, User
from src.services.crypto import AuthVault
from tools import verify_restore as recovery


async def test_restore_verifier_checks_key_and_migration_history(
    postgres_url, monkeypatch
):
    apps = TORTOISE_CONFIG["apps"]
    await Tortoise.init(config={"connections": {"default": postgres_url}, "apps": apps})
    await MigrationExecutor(connections.get("default"), apps).migrate()
    key = Fernet.generate_key().decode()
    user = await User.create(id=1001)
    blob = AuthVault(key).encrypt({"rso": "synthetic-recovery-token"})
    await Account.create(
        puuid="synthetic-recovery", user=user, username="Synthetic", auth_blob=blob
    )

    # The test fixture isolates schemas; real restoration uses a separate database.
    parsed = urlsplit(postgres_url)
    schema = parse_qs(parsed.query)["schema"][0]
    original_connect = recovery.asyncpg.connect

    async def connect(url):
        assert url == postgres_url
        return await original_connect(
            urlunsplit(parsed._replace(query="")),
            server_settings={"search_path": schema},
        )

    monkeypatch.setattr(recovery.asyncpg, "connect", connect)
    result = await recovery.verify_restore(postgres_url, key)
    assert result["migrations"] == 4 and result["encrypted_accounts_verified"] == 1
    assert result["tables"]["user"] == result["tables"]["account"] == 1
    with pytest.raises(ValueError, match="cannot be decrypted"):
        await recovery.verify_restore(postgres_url, Fernet.generate_key().decode())
    assert (await Account.get(puuid="synthetic-recovery")).auth_blob == blob
    await connections.get("default").execute_query(
        "DELETE FROM tortoise_migrations WHERE name = '0004_add_shard_status_message'"
    )
    with pytest.raises(ValueError, match="migration history"):
        await recovery.verify_restore(postgres_url, key)
