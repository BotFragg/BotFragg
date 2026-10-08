"""Behavior checks for crypto."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from src.services.crypto import AuthVault

_OPTIONAL_URLS = (
    "SUPPORT_URL",
    "VOTE_URL",
    "WEBSITE_URL",
    "SHARD_LOG_WEBHOOK_URL",
)


def test_auth_vault_round_trip_and_wrong_key() -> None:
    """Verify that credential encryption round-trips and rejects the wrong key."""
    first = AuthVault(Fernet.generate_key().decode())
    second = AuthVault(Fernet.generate_key().decode())
    encrypted = first.encrypt({"rso": "secret", "refresh_token": "rotating"})
    assert "secret" not in encrypted
    assert first.decrypt(encrypted) == {"refresh_token": "rotating", "rso": "secret"}
    with pytest.raises(ValueError, match="cannot be decrypted"):
        second.decrypt(encrypted)
