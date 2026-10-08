"""Read-only verification of a restored database and its original Fernet key."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.crypto import AuthVault

EXPECTED_MIGRATIONS = frozenset(
    path.stem
    for path in (Path(__file__).resolve().parents[1] / "src" / "migrations").glob(
        "[0-9]*.py"
    )
)

TABLES = (
    "user",
    "account",
    "alert",
    "commandinvocation",
    "suggestion",
    "suggestionfollower",
    "shardstatusmessage",
)


async def verify_restore(url: str, key: str) -> dict:
    """Check every encrypted account and the matching release's migration history."""
    vault = AuthVault(key)
    connection = await asyncpg.connect(url)
    try:
        async with connection.transaction(readonly=True, isolation="repeatable_read"):
            counts = {
                table: await connection.fetchval(
                    # Fixed application table names, never user input.
                    f'SELECT COUNT(*) FROM "{table}"'  # noqa: S608
                )
                for table in TABLES
            }
            applied = {
                row["name"]
                for row in await connection.fetch(
                    "SELECT name FROM tortoise_migrations WHERE app = 'models'"
                )
            }
            if applied != EXPECTED_MIGRATIONS:
                raise ValueError("Restore migration history differs from this release")
            encrypted_accounts = 0
            async for row in connection.cursor(
                "SELECT auth_blob FROM account WHERE auth_blob IS NOT NULL"
            ):
                vault.decrypt(row["auth_blob"])
                encrypted_accounts += 1
            return {
                "tables": counts,
                "migrations": len(applied),
                "encrypted_accounts_verified": encrypted_accounts,
            }
    finally:
        await connection.close()


if __name__ == "__main__":
    if not os.environ.get("BOTFRAGG_RESTORE_DATABASE_URL") or not os.environ.get(
        "TOKEN_ENCRYPTION_KEY"
    ):
        raise SystemExit(
            "Set BOTFRAGG_RESTORE_DATABASE_URL and the original TOKEN_ENCRYPTION_KEY"
        )
    try:
        result = asyncio.run(
            verify_restore(
                os.environ["BOTFRAGG_RESTORE_DATABASE_URL"],
                os.environ["TOKEN_ENCRYPTION_KEY"],
            )
        )
    except Exception as exc:
        # Do not expose connection strings, identifiers, or decrypted credentials.
        raise SystemExit(
            f"Restore verification failed ({type(exc).__name__})"
        ) from None
    print(json.dumps(result, indent=2))
