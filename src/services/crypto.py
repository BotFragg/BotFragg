"""Authenticated encryption for persisted Riot credential payloads."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


class AuthVault:
    """Encrypt and decrypt credential mappings with the configured Fernet key."""

    def __init__(self, key: str) -> None:
        """Validate the encryption key and prepare the Fernet cipher."""
        if not key:
            raise ValueError("TOKEN_ENCRYPTION_KEY is required")
        try:
            self._fernet = Fernet(key.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as exc:
            raise ValueError("TOKEN_ENCRYPTION_KEY must be a valid Fernet key") from exc

    def encrypt(self, auth: Mapping[str, Any]) -> str:
        """Serialize and authenticate a credential mapping as a Fernet token."""
        payload = json.dumps(dict(auth), separators=(",", ":"), sort_keys=True).encode()
        return self._fernet.encrypt(payload).decode("ascii")

    def decrypt(self, token: str | None) -> dict[str, Any]:
        """Decode a stored token, returning an empty mapping when it is absent."""
        if not token:
            return {}
        try:
            payload = self._fernet.decrypt(token.encode("ascii"))
            value = json.loads(payload)
        except (InvalidToken, UnicodeEncodeError, json.JSONDecodeError) as exc:
            raise ValueError("Stored Riot credentials cannot be decrypted") from exc
        if not isinstance(value, dict):
            raise ValueError("Stored Riot credentials have an invalid shape")
        return value
